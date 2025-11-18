import datetime
from django.test import SimpleTestCase

from dashboard import utils
from dashboard.tests.helpers.mocks import (
    moodle_patches,
    model_queryset_patches,
    synchronous_executor,
    patch_questions,
    DummyAvail,
    DummyRoom,
    MOCK_COURSES,
    MOCK_GROUPS,
    MOCK_ENROLLED,
)


class HelpersUnitTests(SimpleTestCase):
    def test_moodle_patches_default_values(self):
        with moodle_patches():
            courses = utils.fetch_moodle_courses({'moodle_id': 123})
            groups = utils.fetch_moodle_groups(101)
            enrolled = utils.fetch_enrolled_students(101)
        self.assertEqual(courses, MOCK_COURSES)
        self.assertEqual(groups, MOCK_GROUPS)
        self.assertEqual(enrolled, MOCK_ENROLLED)

    def test_model_queryset_patches_return_empty_lists(self):
        with model_queryset_patches():
            rooms = utils.Room.objects.using('bot_db').filter(teacher_id=1)
            reactions = utils.Reaction.objects.using('bot_db').filter(room_id=1)
        self.assertEqual(rooms, [])
        self.assertEqual(reactions, [])

    def test_synchronous_executor_executes_immediately(self):
        with synchronous_executor():
            with utils.ThreadPoolExecutor() as ex:
                fut = ex.submit(lambda x, y: x + y, 2, 3)
                self.assertEqual(fut.result(), 5)

    def test_build_availability_display_clamping_and_invalid_times(self):
        # start before timeline -> should be clamped
        early = DummyAvail(1, 'Monday', datetime.time(5, 0), datetime.time(8, 0))
        # invalid times (strings) should go through exception path
        invalid = DummyAvail(2, teacher_id=42, day_of_week='Tuesday', start_time='bad', end_time='bad')
        res = utils.build_availability_display([early, invalid], timeline_start_hour=7, timeline_end_hour=21)
        # Monday (Lunes) should have one slot and left_pct computed (clamped)
        lunes = next(d for d in res['days_with_slots'] if d['day'] == 'Lunes')
        self.assertEqual(len(lunes['slots']), 1)
        slot = lunes['slots'][0]
        self.assertGreaterEqual(slot['left_pct'], 0)
        # invalid times should produce string start/end and zeroed percents
        martes = next(d for d in res['days_with_slots'] if d['day'] == 'Martes')
        self.assertEqual(len(martes['slots']), 1)
        inv_slot = martes['slots'][0]
        self.assertIsInstance(inv_slot['start'], str)
        self.assertEqual(inv_slot['width_pct'], 0.0)

    def test_patch_questions_empty_returns_empty(self):
        room = DummyRoom(5)
        with patch_questions({}):
            assembled = utils.assemble_questions_for_room(room, teacher_id=1)
        self.assertEqual(assembled, [])
