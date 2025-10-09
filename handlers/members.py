# handlers/members.py

from mautrix.types import EventType, Membership

def register(client):
    @client.syncer.on(EventType.ROOM_MEMBER)
    async def on_member_event(room, event):
        content = event.content
        membership = content.get("membership")

        # Ignora si el evento es del propio bot
        if event.state_key == client.mxid:
            return

        # Detecta unirse a la sala
        if membership == Membership.JOIN:
            await client.send_text(
                room.room_id,
                f"🎓 ¡Bienvenido/a {event.state_key} a la sala {room.display_name}!"
            )

        # Detecta abandonar la sala
        elif membership == Membership.LEAVE:
            await client.send_text(
                room.room_id,
                f"👋 {event.state_key} ha salido de la sala."
            )

        # Detecta cambio de nombre
        elif membership == Membership.INVITE:
            await client.send_text(
                room.room_id,
                f"📩 {event.sender} ha invitado a {event.state_key}."
            )
