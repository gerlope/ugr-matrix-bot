# handlers/redactions.py

from mautrix.types import EventType
from handlers.reactions import redact_reaction

def register(client):
    @client.syncer.on(EventType.ROOM_REDACTION)
    async def handle_redaction(room, event):
        """
        Handles a redaction event.
        If the redacted event was a reaction, calls redact_reaction.
        """
        redacted_event_id = event.redacts  # The event being redacted
        sender_mxid = event.sender

        # You may want to ignore bot's own redactions
        if sender_mxid == client.mxid:
            return

        # Fetch the redacted event to check its type
        try:
            redacted_event = await client.get_event(room.room_id, redacted_event_id)
        except Exception:
            return  # Event might not exist anymore

        if redacted_event and redacted_event.type == EventType.REACTION:
            await redact_reaction(room, redacted_event)
