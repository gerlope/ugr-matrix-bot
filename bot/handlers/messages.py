# handlers/messages.py

from mautrix.types import EventType
from core.command_registry import execute_command

def register(client):
    @client.syncer.on(EventType.ROOM_MESSAGE)
    async def on_message(room, event):
        if not hasattr(event, "body") or event.sender == client.mxid:
            return
        body = event.body.strip()
        print(f"[Mensaje] {event.sender}: {body}")
        await execute_command(client, room.room_id, event, body)
