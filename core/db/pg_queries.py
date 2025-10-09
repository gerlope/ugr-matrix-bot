# core/db/pg_queries.py
"""
Consulta y manipulación de datos en PostgreSQL.
"""

from core.db.constants import *
from core.db.pg_conn import pool
from core.db.pg_utils import db_safe

# ────────────────────────────────
# Usuarios
# ────────────────────────────────
@db_safe(default=False)
async def add_usuario(mxid: str, nombre: str):
    """Inserta un usuario en la base de datos; ignora duplicados."""
    async with pool.acquire() as conn:
        await conn.execute(f"""
            INSERT INTO {TABLE_USUARIOS} ({COL_USUARIO_MXID})
            VALUES ($1, $2)
            ON CONFLICT ({COL_USUARIO_MXID}) DO NOTHING
        """, mxid, nombre)
    return True


@db_safe(default=None)
async def get_usuario_id(mxid: str) -> int | None:
    """Obtiene el ID de un usuario, o lo crea si no existe."""
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            f"SELECT {COL_USUARIO_ID} FROM {TABLE_USUARIOS} WHERE {COL_USUARIO_MXID} = $1",
            mxid
        )
        if row:
            return row[COL_USUARIO_ID]
        else:
            await add_usuario(mxid, mxid)
            return await get_usuario_id(mxid)
