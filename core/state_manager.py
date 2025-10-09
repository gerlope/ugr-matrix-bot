# core/state_manager.py
"""
Gestor de estados para salas y usuarios en el bot de Matrix.
Permite que cada sala y usuario mantengan un estado y datos asociados.
Usa constantes definidas en core/state_keys.py para evitar strings mágicas.
"""

from enum import Enum, auto
from core.state_keys import ROOM_STATE, ROOM_DATA, USERS, USER_STATE, USER_DATA


class RoomState(Enum):
    """Posibles estados de una sala."""
    IDLE = auto()
    QUESTION_ACTIVE = auto()
    SESSION_ACTIVE = auto()
    LOCKED = auto()


class UserState(Enum):
    """Posibles estados de un usuario dentro de una sala."""
    IDLE = auto()
    ANSWERING = auto()
    REGISTERING = auto()
    MUTED = auto()


class StateManager:
    """Gestor central de estados de salas y usuarios."""

    def __init__(self):
        # Estructura:
        # rooms = {
        #   room_id: {
        #       "_state": RoomState,
        #       "_data": {...},
        #       "users": {
        #           "@user:server": {
        #               "state": UserState,
        #               "data": {...}
        #           }
        #       }
        #   }
        # }
        self.rooms = {}

    # ──────────────────────────────────────────────
    # Métodos para SALAS
    # ──────────────────────────────────────────────

    def get_room_state(self, room_id):
        """Devuelve el estado actual de una sala."""
        return self.rooms.get(room_id, {}).get(ROOM_STATE, RoomState.IDLE)

    def set_room_state(self, room_id, state: RoomState, data=None):
        """Establece el estado y los datos de una sala."""
        if room_id not in self.rooms:
            self.rooms[room_id] = {USERS: {}}

        self.rooms[room_id][ROOM_STATE] = state
        self.rooms[room_id][ROOM_DATA] = data or {}

        print(f"[ROOM STATE] {room_id} -> {state.name}")

    def get_room_data(self, room_id):
        """Devuelve los datos asociados a la sala."""
        return self.rooms.get(room_id, {}).get(ROOM_DATA, {})

    def set_room_data(self, room_id, data: dict):
        """Reemplaza los datos asociados a la sala."""
        if room_id not in self.rooms:
            self.rooms[room_id] = {USERS: {}}
        self.rooms[room_id][ROOM_DATA] = data or {}

    # ──────────────────────────────────────────────
    # Métodos para USUARIOS
    # ──────────────────────────────────────────────

    def get_user_state(self, room_id, user_id):
        """Obtiene el estado actual de un usuario dentro de una sala."""
        return (
            self.rooms.get(room_id, {})
            .get(USERS, {})
            .get(user_id, {})
            .get(USER_STATE, UserState.IDLE)
        )

    def set_user_state(self, room_id, user_id, state: UserState, data=None):
        """Establece el estado y los datos de un usuario dentro de una sala."""
        if room_id not in self.rooms:
            self.rooms[room_id] = {USERS: {}}
        if USERS not in self.rooms[room_id]:
            self.rooms[room_id][USERS] = {}

        self.rooms[room_id][USERS][user_id] = {
            USER_STATE: state,
            USER_DATA: data or {}
        }

        print(f"[USER STATE] {user_id} @ {room_id} -> {state.name}")

    def get_user_data(self, room_id, user_id):
        """Devuelve los datos asociados a un usuario en una sala."""
        return (
            self.rooms.get(room_id, {})
            .get(USERS, {})
            .get(user_id, {})
            .get(USER_DATA, {})
        )

    def set_user_data(self, room_id, user_id, data: dict):
        """Reemplaza los datos asociados a un usuario dentro de una sala."""
        if room_id not in self.rooms:
            self.rooms[room_id] = {USERS: {}}
        if USERS not in self.rooms[room_id]:
            self.rooms[room_id][USERS] = {}
        if user_id not in self.rooms[room_id][USERS]:
            self.rooms[room_id][USERS][user_id] = {}

        self.rooms[room_id][USERS][user_id][USER_DATA] = data or {}

    # ──────────────────────────────────────────────
    # Métodos de depuración
    # ──────────────────────────────────────────────

    def debug_dump(self):
        """Imprime el estado completo actual (solo para depuración)."""
        import json
        print("[STATE DUMP]")
        print(json.dumps(self.rooms, indent=4, default=str))
