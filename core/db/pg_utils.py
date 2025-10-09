# core/db/pg_utils.py

import functools
import logging
import asyncpg

# Configurar logger para base de datos
logger = logging.getLogger("db")
logger.setLevel(logging.INFO)

# Si no hay un handler configurado, crear uno básico
if not logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter("[%(asctime)s] [%(levelname)s] %(message)s")
    handler.setFormatter(formatter)
    logger.addHandler(handler)

def db_safe(default=None):
    """
    Decorador para manejar errores de base de datos en funciones async.

    Uso:
        @db_safe(default=[])
        async def get_all_users(): ...
    """
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            try:
                return await func(*args, **kwargs)
            except asyncpg.PostgresError as e:
                logger.error(f"❌ Error en {func.__name__}: {e}")
            except Exception as e:
                logger.exception(f"⚠️ Excepción inesperada en {func.__name__}: {e}")
            return default
        return wrapper
    return decorator
