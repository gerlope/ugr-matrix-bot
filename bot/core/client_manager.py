# core/client_manager.py

from mautrix.client import Client
from config import HOMESERVER, USERNAME, PASSWORD

async def create_client() -> Client:
    client = Client(HOMESERVER)
    await client.login(USERNAME, PASSWORD)
    print(f"[+] Conectado como {USERNAME}")
    return client