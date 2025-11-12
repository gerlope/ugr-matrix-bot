# commands/ping.py

USAGE = "!ping"
DESCRIPTION = "Comprueba si el bot está activo."

async def run(client, room_id, event, args):
    await client.send_text(room_id, "🏓 Pong!")
