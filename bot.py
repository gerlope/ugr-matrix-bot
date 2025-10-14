# bot.py

import asyncio
from core.client_manager import create_client
from core.command_registry import load_commands
from core.event_router import register_event_handlers
from core.db.constants import DB_MODULES
from config import DB_TYPE

async def main():
    db_conn = DB_MODULES[DB_TYPE]["conn"]
    await db_conn.connect()
    client = await create_client()
    load_commands()
    register_event_handlers(client)

    print("[*] Bot iniciado — escuchando mensajes...")
    try:
        await client.sync_forever(timeout=30000, full_state=True)
    except KeyboardInterrupt:
        print("[*] Bot detenido por usuario")
    finally:
        await client.close()
        await db_conn.close()


if __name__ == "__main__":
    asyncio.run(main())
