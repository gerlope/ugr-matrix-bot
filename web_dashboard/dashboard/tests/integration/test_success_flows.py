import datetime
from unittest import mock
from django.test import TestCase
from django.contrib.auth.models import User
from django.urls import reverse

"""Integration tests for happy-path flows used by teachers.

Includes scenarios such as creating rooms, creating questions and
other end-to-end flows with mocked external services to avoid real
network/database side-effects.
"""

from dashboard.tests.helpers.mocks import dashboard_test_stack, DummyRoom, DummyQuestion


class SuccessFlowsTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='succtest', password='x')
        self.client.force_login(self.user)
        session = self.client.session
        session['teacher'] = {
            'id': 42,
            'matrix_id': '@test:example.org',
            'moodle_id': 999,
            'is_teacher': True,
            'registered_at': datetime.datetime.utcnow().isoformat(),
            'username': 'test'
        }
        session.save()
        self._stack = dashboard_test_stack()
        self._stack.__enter__()

    def tearDown(self):
        if getattr(self, '_stack', None):
            self._stack.__exit__(None, None, None)

    def test_create_room_success(self):
        # Mock Room.create to return a room owned by the teacher
        fake_room = DummyRoom(123)
        fake_room.id = 123
        fake_room.shortcode = 'NEW'
        fake_room.teacher_id = 42
        with mock.patch('dashboard.views.Room') as R:
            R.objects.using.return_value.create.return_value = fake_room
            resp = self.client.post(reverse('dashboard:create_room'), {
                'course_id': '10',
                'shortcode': 'NEW',
            }, follow=False)
        # Should redirect to dashboard with room_id param
        self.assertEqual(resp.status_code, 302)
        self.assertIn('room_id=123', resp['Location'])

    def test_create_question_success(self):
        # Patch Room to be teacher-owned and Question create to succeed
        fake_room = DummyRoom(77)
        fake_room.id = 77
        fake_room.teacher_id = 42
        fake_q = DummyQuestion(id=999, teacher_id=42, room_id=77)
        with mock.patch('dashboard.views.Room') as R, \
                mock.patch('dashboard.views.Question') as Q, \
                mock.patch('dashboard.views.QuestionOption') as QO:
            R.objects.using.return_value.filter.return_value.first.return_value = fake_room
            Q.objects.using.return_value.create.return_value = fake_q
            resp = self.client.post(reverse('dashboard:create_question'), {
                'selected_room_id': '77',
                'qtype': 'short_answer',
                'title': 'Simple Question',
                'body': 'What is 2+2?',
                'expected_answer': '4',
            }, follow=False)
            self.assertEqual(resp.status_code, 302)
            self.assertIn('room_id=77', resp['Location'])

    def test_deactivate_room_permission_and_success(self):
        # Permission denied when teacher_id mismatches
        fake_room = DummyRoom(200)
        fake_room.id = 200
        fake_room.teacher_id = 999
        with mock.patch('dashboard.views.Room') as R:
            R.objects.using.return_value.get.return_value = fake_room
            resp = self.client.post(reverse('dashboard:deactivate_room', args=[200]), follow=True)
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(any('No tienes permiso para cerrar esta sala' in str(m) for m in resp.context['messages']))

        # Now success path
        fake_room2 = DummyRoom(201)
        fake_room2.id = 201
        fake_room2.teacher_id = 42
        # ensure save() exists so view can call it without error
        fake_room2.save = mock.MagicMock()
        # Patch get_object_or_404 to return our fake object so the view operates on it
        with mock.patch('dashboard.views.Room') as R2, \
                mock.patch('dashboard.views.get_object_or_404', return_value=fake_room2):
            R2.objects.using.return_value.get.return_value = fake_room2
            resp2 = self.client.post(reverse('dashboard:deactivate_room', args=[201]), follow=False)
            # success should redirect to the dashboard
            self.assertEqual(resp2.status_code, 302)
            self.assertIn(reverse('dashboard:dashboard'), resp2['Location'])
            # ensure save() was called on the object with the expected DB alias
            fake_room2.save.assert_called_with(using='bot_db')
            # and the active flag was flipped
            self.assertFalse(getattr(fake_room2, 'active', True))
