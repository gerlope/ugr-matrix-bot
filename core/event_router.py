# core/event_router.py

from handlers import messages, members, reactions

def register_event_handlers(client):
    members.register(client)
    messages.register(client)
    reactions.register(client)
    print("[+] Handlers de eventos registrados")
