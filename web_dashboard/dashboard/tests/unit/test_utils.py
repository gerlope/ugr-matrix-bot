import datetime
from unittest import mock
from dashboard.tests.helpers.mocks import patch_teacher_availability, DummyAvail
from django.test import SimpleTestCase

from dashboard import utils

class UtilsTests(SimpleTestCase):
    def test_build_availability_display_basic(self):
        rows = [
            DummyAvail(1, 'Monday', datetime.time(8, 0), datetime.time(9, 0)),
            DummyAvail(2, 'Monday', datetime.time(10, 30), datetime.time(11, 0)),
            DummyAvail(3, 'Wednesday', datetime.time(7, 0), datetime.time(7, 30)),
        ]
        result = utils.build_availability_display(rows, timeline_start_hour=7, timeline_end_hour=21)
        self.assertIn('days_with_slots', result)
        monday_slots = [d for d in result['days_with_slots'] if d['day'] == 'Lunes'][0]['slots']
        self.assertEqual(len(monday_slots), 2)
        # Percentages within bounds
        for slot in monday_slots:
            self.assertGreaterEqual(slot['left_pct'], 0)
            self.assertLessEqual(slot['left_pct'], 100)
            self.assertGreaterEqual(slot['width_pct'], 0)
            self.assertLessEqual(slot['width_pct'], 100)

    def test_assemble_questions_for_room_none(self):
        self.assertEqual(utils.assemble_questions_for_room(None, teacher_id=1), [])

    def test_check_availability_overlap_detects(self):
        """Ensure overlapping interval is detected.

        We patch the real model path ``dashboard.models.TeacherAvailability`` because
        ``check_availability_overlap`` does a late import inside the function.
        """
        existing = [
            DummyAvail(1, 'Monday', datetime.time(8, 0), datetime.time(9, 0)),
            DummyAvail(2, 'Monday', datetime.time(10, 0), datetime.time(11, 0)),
        ]
        with patch_teacher_availability(existing):
            conflict = utils.check_availability_overlap(
                teacher_id=5,
                day='Monday',
                start_time=datetime.time(8, 30),
                end_time=datetime.time(9, 30)
            )
        self.assertIsNotNone(conflict)
        self.assertEqual(conflict.id, 1)

    def test_check_availability_overlap_none(self):
        existing = [
            DummyAvail(1, 'Monday', datetime.time(8, 0), datetime.time(9, 0)),
        ]
        with patch_teacher_availability(existing):
            conflict = utils.check_availability_overlap(
                teacher_id=5,
                day='Monday',
                start_time=datetime.time(9, 0),
                end_time=datetime.time(10, 0)
            )
        self.assertIsNone(conflict)

    def test_check_availability_overlap_cases(self):
        """Parameterized edge cases using subTests for overlap logic.

        Cases:
          - partial overlap at start
          - partial overlap at end
          - exact match (overlap)
          - touching end (no overlap)
          - touching start (no overlap)
          - enclosure (new interval fully inside existing)
        """
        base = DummyAvail(1, 'Monday', datetime.time(8, 0), datetime.time(10, 0))
        cases = [
            # (start, end, expect_conflict)
            (datetime.time(7, 30), datetime.time(8, 30), True),  # partial at start
            (datetime.time(9, 30), datetime.time(10, 30), True),  # partial at end
            (datetime.time(8, 0), datetime.time(10, 0), True),   # exact match
            (datetime.time(10, 0), datetime.time(11, 0), False), # touching end
            (datetime.time(7, 0), datetime.time(8, 0), False),   # touching start
            (datetime.time(8, 30), datetime.time(9, 30), True),  # inside existing
        ]
        for st, et, expected in cases:
            with self.subTest(start=st, end=et):
                with patch_teacher_availability([base]):
                    conflict = utils.check_availability_overlap(
                        teacher_id=99,
                        day='Monday',
                        start_time=st,
                        end_time=et,
                    )
                if expected:
                    self.assertIsNotNone(conflict)
                else:
                    self.assertIsNone(conflict)
