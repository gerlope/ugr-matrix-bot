# core/state_keys.py
"""
Constantes para las claves internas usadas en StateManager.
Evita el uso de 'strings mágicas' y facilita cambios futuros.
"""

# Claves de nivel sala
ROOM_STATE = "_state"
ROOM_DATA = "_data"

# Clave para el mapa de usuarios dentro de una sala
USERS = "users"

# Claves de nivel usuario
USER_STATE = "state"
USER_DATA = "data"
