# core/db/pg_conn.py

import asyncpg
from config import DB_CONFIG
from pathlib import Path

pool: asyncpg.pool.Pool | None = None  # Pool global

# ────────────────────────────────
# Conexión y esquema
# ────────────────────────────────

async def connect():
    """Crea un pool de conexiones y carga el esquema desde schema.sql"""
    global pool
    pool = await asyncpg.create_pool(**DB_CONFIG)
    await init_tables()

async def init_tables():
    """Lee schema.sql y ejecuta todas las queries"""
    global pool
    if pool is None:
        raise RuntimeError("El pool de conexiones no está inicializado")

    schema_file = Path(__file__).parent / "pg_schema.sql"
    if not schema_file.exists():
        raise FileNotFoundError(f"No se encontró {schema_file}")

    sql = schema_file.read_text()

    async with pool.acquire() as conn:
        # asyncpg permite ejecutar varias queries separadas por ;
        await conn.execute(sql)

# ────────────────────────────────
# Cierre del pool
# ────────────────────────────────

async def close():
    """Cierra el pool de conexiones"""
    global pool
    if pool is not None:
        await pool.close()
        pool = None
