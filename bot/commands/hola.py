# commands/hola.py

USAGE = "!hola <nombre>"
DESCRIPTION = "Comprueba si el bot está activo."

async def run(client, room_id, event, args):
    if len(args) != 1:
        await client.send_text(room_id, "⚠️ Uso correcto: !hola <nombre>")
        return
    
    sender = event.sender
    name = args[0]
    await client.send_text(room_id, f"👋 ¡Hola {sender}! Soy tu bot de ayuda docente {args[0]}🤖")
