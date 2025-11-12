# bot.py

import asyncio
from pathlib import Path
import importlib.util
import sys

# Load config.py directly (without mutating sys.path) and insert it into sys.modules
# so that other modules can do `from config import ...` normally.
REPO_ROOT = Path(__file__).resolve().parents[1]
_config_path = REPO_ROOT / "config.py"
_spec = importlib.util.spec_from_file_location("config", str(_config_path))
_config = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_config)
sys.modules["config"] = _config

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
