# commands/hola.py

async def run(client, room_id, event):
    sender = event.sender
    await client.send_text(room_id, f"👋 ¡Hola {sender}! Soy tu bot de ayuda docente 🤖")
