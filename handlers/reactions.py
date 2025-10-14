# handlers/reactions.py

from mautrix.types import EventType
from core.db.constants import COL_USER_IS_TEACHER, COL_ROOM_MOODLE_COURSE_ID
from core.db.constants import DB_MODULES
from config import DB_TYPE

def register(client):
    @client.syncer.on(EventType.REACTION)
    async def on_add_reaction(room, event):
        """Handler para agregar o incrementar reacciones."""
        relates_to = event.content.get("m.relates_to", {})
        emoji = relates_to.get("key", "❓")
        reacted_to_event_id = relates_to.get("event_id", "desconocido")
        sender_mxid = event.sender

        db = DB_MODULES[DB_TYPE]["queries"]

        if sender_mxid == client.mxid:
            return

        # Verificar profesor
        teacher = await db.get_user_by_matrix_id(sender_mxid)
        if not teacher or not teacher[COL_USER_IS_TEACHER]:
            return

        # Obtener estudiante
        reacted_event = await client.get_event(room.room_id, reacted_to_event_id)
        if not reacted_event:
            return
        student_mxid = reacted_event.sender
        student = await db.get_user_by_matrix_id(student_mxid)
        if not student:
            return

        # Obtener moodle_course_id
        room_data = await db.get_room_by_matrix_id(room.room_id)
        if not room_data:
            return
        moodle_course_id = room_data[COL_ROOM_MOODLE_COURSE_ID]

        # Agregar o incrementar reacción
        await db.add_or_increase_reaccion(
            teacher_id=teacher["id"],
            student_id=student["id"],
            moodle_course_id=moodle_course_id,
            reaction_type=emoji,
            increment=1
        )

    async def redact_reaction(room, event):
        """Handler para redactar reacciones."""
        relates_to = event.content.get("m.relates_to", {})
        emoji = relates_to.get("key", "❓")
        reacted_to_event_id = relates_to.get("event_id", "desconocido")
        sender_mxid = event.sender

        db = DB_MODULES[DB_TYPE]["queries"]

        if sender_mxid == client.mxid:
            return

        # Verificar profesor
        teacher = await db.get_user_by_matrix_id(sender_mxid)
        if not teacher or not teacher[COL_USER_IS_TEACHER]:
            return

        # Obtener estudiante
        reacted_event = await client.get_event(room.room_id, reacted_to_event_id)
        if not reacted_event:
            return
        student_mxid = reacted_event.sender
        student = await db.get_user_by_matrix_id(student_mxid)
        if not student:
            return

        # Obtener moodle_course_id
        room_data = await db.get_room_by_matrix_id(room.room_id)
        if not room_data:
            return
        moodle_course_id = room_data[COL_ROOM_MOODLE_COURSE_ID]

        # Disminuir o eliminar reacción
        await db.decrease_or_delete_reaccion(
            teacher_id=teacher["id"],
            student_id=student["id"],
            moodle_course_id=moodle_course_id,
            reaction_type=emoji,
            decrement=1
        )
