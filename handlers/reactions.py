# handlers/reactions.py

from mautrix.types import EventType

def register(client):
    @client.syncer.on(EventType.REACTION)
    async def on_reaction(room, event):
        relates_to = event.content.get("m.relates_to", {})
        emoji = relates_to.get("key", "❓")
        reacted_to = relates_to.get("event_id", "desconocido")

        if event.sender == client.mxid:
            return  # Ignora reacciones del propio bot

        print(f"[Reacción] {event.sender} reaccionó con {emoji} al evento {reacted_to}")

        # Ejemplo: el bot responde ante ciertos emojis
        if emoji == "👍":
            await client.send_text(room.room_id, "¡Gracias por el apoyo! 🙌")
        elif emoji == "👎":
            await client.send_text(room.room_id, "😢 Espero poder mejorar mi respuesta.")
