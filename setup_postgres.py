#!/usr/bin/env python3
"""
Sincroniza usuarios y asignaturas de Moodle con Matrix y PostgreSQL.

- Crea usuarios en Matrix si no existen.
- Inserta usuarios en la tabla PostgreSQL `users` con su moodle_id y si son profesores.
- Crea una sala Matrix por cada asignatura Moodle.
- Invita a los usuarios del curso correspondiente.
"""

import asyncio
from pathlib import Path
import aiohttp
import asyncpg
import requests
import time
import string
import secrets
from config import (MOODLE_URL, MOODLE_TOKEN,
                    HOMESERVER, USERNAME, PASSWORD, ADMIN_TOKEN,
                    DB_USER, DB_PASSWORD, DB_NAME, DB_HOST, DB_PORT
                    )

# ==============================
# CONFIGURACIÓN
# ==============================
# --- PostgreSQL ---
PG_DSN = f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
DB_CONFIG = {
    "user": DB_USER,
    "password": DB_PASSWORD,
    "database": DB_NAME,
    "host": DB_HOST,
    "port": DB_PORT
}

# --- Parámetros generales ---
INVITE_DELAY = 0.5
ROOM_VISIBILITY = "private"
DRY_RUN = False  # True = modo simulación

# ==============================
# UTILIDADES
# ==============================

def gen_password(length: int = 12):
    alphabet = string.ascii_letters + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(length))

def safe_localpart(email: str, fallback: str):
    if not email:
        candidate = fallback
    else:
        candidate = email.split('@')[0]
    allowed = [ch for ch in candidate if ch.isalnum() or ch in "._-"]
    s = ''.join(allowed).lower().strip('._-')
    return s[:64] if s else fallback

def matrix_user_id_from_email(email: str, HOMESERVER: str):
    local = safe_localpart(email, "user")
    domain = HOMESERVER.split("://")[-1].split("/")[0]
    return f"@{local}:{domain}"

# ==============================
# FUNCIONES MOODLE
# ==============================

def get_courses():
    endpoint = f"{MOODLE_URL}/webservice/rest/server.php"
    params = {
        'wstoken': MOODLE_TOKEN,
        'wsfunction': 'core_course_get_courses',
        'moodlewsrestformat': 'json'
    }
    resp = requests.get(endpoint, params=params, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    return data if isinstance(data, list) else []

def get_course_users(course_id):
    endpoint = f"{MOODLE_URL}/webservice/rest/server.php"
    params = {
        'wstoken': MOODLE_TOKEN,
        'wsfunction': 'core_enrol_get_enrolled_users',
        'moodlewsrestformat': 'json',
        'courseid': course_id
    }
    resp = requests.get(endpoint, params=params, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    return data if isinstance(data, list) else []

# ==============================
# FUNCIONES MATRIX (ASÍNCRONAS)
# ==============================

async def create_matrix_user(session, localpart, password, displayname=None):
    url = f"{HOMESERVER}/_synapse/admin/v2/users"
    headers = {'Authorization': f'Bearer {ADMIN_TOKEN}', 'Content-Type': 'application/json'}
    body = {"localpart": localpart, "password": password}
    if displayname:
        body["displayname"] = displayname

    async with session.post(url, headers=headers, json=body, timeout=20) as resp:
        if resp.status in (200, 201):
            return await resp.json()
        elif resp.status == 409:
            return None  # ya existe
        else:
            text = await resp.text()
            raise RuntimeError(f"Error creando usuario {localpart}: {resp.status} {text}")

async def login_matrix_bot(session):
    url = f"{HOMESERVER}/_matrix/client/v3/login"
    body = {
        "type": "m.login.password",
        "identifier": {"type": "m.id.user", "user": USERNAME},
        "password": PASSWORD
    }
    async with session.post(url, json=body, timeout=20) as resp:
        if resp.status != 200:
            raise RuntimeError(f"Error login bot: {resp.status} {await resp.text()}")
        data = await resp.json()
        return data["access_token"]

async def create_room(session, token, name, topic=None):
    url = f"{HOMESERVER}/_matrix/client/v3/createRoom"
    headers = {"Authorization": f"Bearer {token}"}
    body = {
        "name": name,
        "preset": "private_chat" if ROOM_VISIBILITY == "private" else "public_chat",
        "visibility": ROOM_VISIBILITY
    }
    if topic:
        body["topic"] = topic

    async with session.post(url, headers=headers, json=body, timeout=20) as resp:
        if resp.status == 200:
            data = await resp.json()
            return data["room_id"]
        else:
            raise RuntimeError(f"Error creando sala {name}: {resp.status} {await resp.text()}")

async def invite_user(session, token, room_id, user_id):
    url = f"{HOMESERVER}/_matrix/client/v3/rooms/{room_id}/invite"
    headers = {"Authorization": f"Bearer {token}"}
    body = {"user_id": user_id}
    async with session.post(url, headers=headers, json=body, timeout=15) as resp:
        if resp.status not in (200, 202):
            text = await resp.text()
            raise RuntimeError(f"Error invitando {user_id}: {resp.status} {text}")

# ==============================
# PRINCIPAL
# ==============================

async def main():
    print("=== Sincronizando usuarios y cursos ===")
    courses = get_courses()
    print(f"Asignaturas obtenidas: {len(courses)}\n")

    async with aiohttp.ClientSession() as session:
        if DRY_RUN:
            token = ""
        #else:
        #    token = await login_matrix_bot(session)

        conn = None
        if not DRY_RUN:
            # Conectar y crear esquema en la base de datos
            conn = await asyncpg.connect(PG_DSN)

            schema_file = Path(__file__).parent / "core/db/postgres/schema.sql"
            if not schema_file.exists():
                raise FileNotFoundError(f"No se encontró {schema_file}")
        
            sql = schema_file.read_text()
            await conn.execute(sql)

        for course in courses:
            cid = course["id"]
            cname = course["fullname"]
            cshortname = course["shortname"]
            if cid == 1:
                continue

            print(f"\n=== Procesando curso: {cname} (ID={cid}) ===")

            users = get_course_users(cid)
            print(f"Usuarios inscritos: {len(users)}")

            room_id = None
            if not DRY_RUN:
                topic = f"Grupo de la asignatura {cname}"
                #room_id = await create_room(session, token, cname, topic)
                room_id = f"test_room_{cshortname}"
                room_id_teachers = f"{room_id}_teachers"
                await conn.execute("""
                    INSERT INTO rooms (room_id, moodle_course_id, teacher_id, shortcode)
                    VALUES ($1, $2, $3 , $4)
                    ON CONFLICT (room_id) DO NOTHING
                """, room_id, cid, None, cshortname)
                await conn.execute("""
                    INSERT INTO rooms (room_id, moodle_course_id, teacher_id, shortcode)
                    VALUES ($1, $2, $3 , $4)
                    ON CONFLICT (room_id) DO NOTHING
                """, room_id_teachers, cid, None, cshortname+"_teachers")

                print(f"[CREADA] Salas '{cname}' ({room_id} y {room_id_teachers})")

            for u in users:
                email = u.get("email")
                if not email:
                    continue

                localpart = safe_localpart(email, f"user{u['id']}")
                displayname = f"{u.get('firstname', '')} {u.get('lastname', '')}".strip() or localpart
                matrix_id = matrix_user_id_from_email(email, HOMESERVER)
                moodle_id = u.get("id")

                # Determinar si es profesor
                roles = [r.get("shortname", "") for r in u.get("roles", [])]
                is_teacher = any(r in ("editingteacher", "teacher") for r in roles)

                if DRY_RUN:
                    print(f"[DRY-RUN] {matrix_id} ({displayname}) -> moodle_id={moodle_id} teacher={is_teacher}")
                    continue

                try:
                    # Crear usuario si no existe
                    #await create_matrix_user(session, localpart, gen_password(), displayname)
                    # Insertar en base de datos
                    await conn.execute("""
                        INSERT INTO users (matrix_id, moodle_id, is_teacher)
                        VALUES ($1, $2, $3)
                        ON CONFLICT (matrix_id) DO UPDATE
                        SET
                            moodle_id = EXCLUDED.moodle_id,
                            is_teacher = CASE
                                WHEN users.is_teacher = FALSE AND EXCLUDED.is_teacher = TRUE THEN TRUE
                                ELSE users.is_teacher
                            END
                    """, matrix_id, moodle_id, is_teacher)

                    # Invitar a la sala
                    if room_id:
                        #await invite_user(session, token, room_id, matrix_id)
                        if is_teacher:
                            time.sleep(INVITE_DELAY)
                            #await invite_user(session, token, room_id_teachers, matrix_id)
                        print(f"   → Invitado {matrix_id} ({'profesor' if is_teacher else 'alumno'})")
                        time.sleep(INVITE_DELAY)

                except Exception as e:
                    print(f"[ERROR] {matrix_id}: {e}")

        if conn:
            await conn.close()

    print("\n=== Sincronización completa ===")


if __name__ == "__main__":
    asyncio.run(main())
