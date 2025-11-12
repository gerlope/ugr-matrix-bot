# core/db/postgres/utils.py

import functools
import logging
import asyncio
import asyncpg

logger = logging.getLogger("db")
logger.setLevel(logging.INFO)

if not logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter("[%(asctime)s] [%(levelname)s] %(message)s")
    handler.setFormatter(formatter)
    logger.addHandler(handler)


def db_safe(default=None, retries=3, delay=1.0):
    """
    Decorador para manejar errores de base de datos en funciones async y reintentar.

    Args:
        default: valor a devolver si falla definitivamente.
        retries: número de intentos antes de rendirse.
        delay: segundos a esperar entre reintentos.
    """
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            attempt = 0
            while attempt < retries:
                try:
                    return await func(*args, **kwargs)
                except (asyncpg.PostgresConnectionError,
                        asyncpg.CannotConnectNowError) as e:
                    attempt += 1
                    logger.warning(
                        f"⚠️ Intento {attempt}/{retries} fallido en {func.__name__}: {e}. "
                        f"Reintentando en {delay}s..."
                    )
                    await asyncio.sleep(delay)
                except Exception as e:
                    logger.exception(f"❌ Excepción inesperada en {func.__name__}: {e}")
                    break
            logger.error(f"❌ {func.__name__} falló después de {retries} intentos. Devolviendo valor por defecto.")
            return default
        return wrapper
    return decorator
