"""Unit tests validating assembly and grouping of questions and related data.

These tests exercise `assemble_questions_for_room` behaviour using
lightweight mock objects provided by `dashboard.tests.helpers.mocks`.
"""

import datetime
from django.test import SimpleTestCase

from dashboard import utils
from dashboard.tests.helpers.mocks import patch_questions, DummyRoom

class Obj:
    def __init__(self, **kwargs):
        for k,v in kwargs.items():
            setattr(self, k, v)


class AssembleQuestionsTests(SimpleTestCase):
    def test_assemble_questions_for_room_populated(self):
        now = datetime.datetime.utcnow()
        room = DummyRoom(10)
        # Use timezone-aware datetimes aligned with utils (which uses timezone.now()).
        from django.utils import timezone
        now_aw = timezone.now()
        questions = [
            Obj(id=1, room_id=room.id, manual_active=True, start_at=None, end_at=None, created_at=now_aw),  # manual active
            Obj(id=2, room_id=room.id, manual_active=False, start_at=now_aw + datetime.timedelta(hours=1), end_at=None, created_at=now_aw),  # future
            Obj(id=3, room_id=room.id, manual_active=False, start_at=now_aw - datetime.timedelta(hours=2), end_at=now_aw - datetime.timedelta(hours=1), created_at=now_aw),  # past
        ]
        options = [
            Obj(id=11, question_id=1, position=0),
            Obj(id=12, question_id=1, position=1),
            Obj(id=21, question_id=2, position=0),
        ]
        responses = [
            Obj(id=101, question_id=1, student_id=501, option_id=11, answer_text=None, submitted_at=now_aw, score=None),
            Obj(id=102, question_id=1, student_id=502, option_id=None, answer_text="Free", submitted_at=now_aw, score=1.0),
        ]
        response_options = [
            Obj(response_id=102, option_id=12),  # multi-answer for second response
        ]
        students = [
            Obj(id=501, moodle_id=9001, matrix_id='@s1:test'),
            Obj(id=502, moodle_id=9002, matrix_id='@s2:test'),
        ]
        data = {
            'questions': questions,
            'options': options,
            'responses': responses,
            'response_options': response_options,
            'students': students,
        }
        with patch_questions(data):
            assembled = utils.assemble_questions_for_room(room, teacher_id=42)
        # Basic counts
        self.assertEqual(len(assembled), 3)
        qmap = {e['question'].id: e for e in assembled}
        # Question 1 manual active
        self.assertTrue(qmap[1]['is_currently_active'])
        # Future question not active yet
        self.assertFalse(qmap[2]['is_currently_active'])
        self.assertTrue(qmap[2]['before_start'])
        # Past question ended
        self.assertTrue(qmap[3]['after_end'])
        # Options grouped
        self.assertEqual(len(qmap[1]['options']), 2)
        # Responses aggregated
        self.assertEqual(len(qmap[1]['responses']), 2)
        # Multi option response includes option_ids list
        r2 = next(r for r in qmap[1]['responses'] if r['id'] == 102)
        self.assertIn(12, r2['option_ids'])
