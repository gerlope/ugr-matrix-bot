# commands/ayuda.py

from core.command_registry import COMMANDS

async def run(client, room_id, event):
    cmds = " | ".join(sorted(COMMANDS.keys()))
    await client.send_text(
        room_id,
        f"📘 Comandos disponibles:\n{cmds}\n\nUsa `!<comando>` para ejecutarlos."
    )
