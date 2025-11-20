import datetime
from unittest import mock
from django.test import TestCase
from django.contrib.auth.models import User
from django.urls import reverse

from dashboard.tests.helpers.mocks import dashboard_test_stack


class GradingIntegrationTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='grader', password='x')
        self.client.force_login(self.user)
        session = self.client.session
        session['teacher'] = {
            'id': 42,
            'matrix_id': '@grader:example.org',
            'moodle_id': 1000,
            'is_teacher': True,
            'registered_at': datetime.datetime.utcnow().isoformat(),
            'username': 'grader'
        }
        session.save()
        self._stack = dashboard_test_stack()
        self._stack.__enter__()

    def tearDown(self):
        if getattr(self, '_stack', None):
            self._stack.__exit__(None, None, None)

    def test_grade_response_not_found(self):
        with mock.patch('dashboard.views.QuestionResponse') as QR:
            QR.objects.using.return_value.filter.return_value.first.return_value = None
            resp = self.client.post(reverse('dashboard:grade_response', args=[123]), follow=True)
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(any('Respuesta no encontrada' in str(m) for m in resp.context['messages']))

    def test_grade_response_no_permission(self):
        # Response exists but question belongs to another teacher
        fake_resp = mock.MagicMock()
        fake_resp.id = 11
        fake_resp.question_id = 77
        with mock.patch('dashboard.views.QuestionResponse') as QR, \
             mock.patch('dashboard.views.Question') as Q:
            QR.objects.using.return_value.filter.return_value.first.return_value = fake_resp
            qobj = mock.MagicMock()
            qobj.teacher_id = 999
            Q.objects.using.return_value.filter.return_value.first.return_value = qobj
            resp = self.client.post(reverse('dashboard:grade_response', args=[11]), follow=True)
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(any('No tienes permiso' in str(m) for m in resp.context['messages']))

    def test_grade_response_success(self):
        fake_resp = mock.MagicMock()
        fake_resp.id = 21
        fake_resp.question_id = 88
        fake_resp.score = None
        fake_resp.feedback = None
        fake_resp.is_graded = False
        fake_resp.grader_id = None
        fake_resp.save = mock.MagicMock()

        with mock.patch('dashboard.views.QuestionResponse') as QR, \
             mock.patch('dashboard.views.Question') as Q:
            QR.objects.using.return_value.filter.return_value.first.return_value = fake_resp
            qobj = mock.MagicMock()
            qobj.teacher_id = 42
            qobj.room_id = 5
            Q.objects.using.return_value.filter.return_value.first.return_value = qobj

            resp = self.client.post(reverse('dashboard:grade_response', args=[21]), {
                'score': '85.5',
                'feedback': 'Good job'
            }, follow=True)

        self.assertEqual(resp.status_code, 200)
        # messages should contain success
        self.assertTrue(any('Respuesta corregida correctamente' in str(m) for m in resp.context['messages']))
        # check that response object was updated and saved
        self.assertEqual(float(fake_resp.score), 85.5)
        self.assertEqual(fake_resp.feedback, 'Good job')
        self.assertTrue(fake_resp.is_graded)
        self.assertEqual(fake_resp.grader_id, 42)
        fake_resp.save.assert_called_with(using='bot_db')

    def test_grade_response_non_numeric_score(self):
        fake_resp = mock.MagicMock()
        fake_resp.id = 31
        fake_resp.question_id = 99
        fake_resp.score = None
        fake_resp.feedback = None
        fake_resp.is_graded = False
        fake_resp.grader_id = None
        fake_resp.save = mock.MagicMock()

        with mock.patch('dashboard.views.QuestionResponse') as QR, \
             mock.patch('dashboard.views.Question') as Q:
            QR.objects.using.return_value.filter.return_value.first.return_value = fake_resp
            qobj = mock.MagicMock()
            qobj.teacher_id = 42
            qobj.room_id = 6
            Q.objects.using.return_value.filter.return_value.first.return_value = qobj

            resp = self.client.post(reverse('dashboard:grade_response', args=[31]), {
                'score': 'not-a-number',
                'feedback': 'Invalid score'
            }, follow=True)

        self.assertEqual(resp.status_code, 200)
        # form invalid -> re-render dashboard with modal and form in context
        self.assertIn('grade_response_form', resp.context)
        form = resp.context['grade_response_form']
        self.assertTrue(form.errors)
        self.assertIn('score', form.errors)
        # ensure save was NOT called
        fake_resp.save.assert_not_called()

    def test_grade_response_out_of_range_scores(self):
        # Negative score
        fake_resp = mock.MagicMock()
        fake_resp.id = 41
        fake_resp.question_id = 100
        fake_resp.score = None
        fake_resp.feedback = None
        fake_resp.is_graded = False
        fake_resp.grader_id = None
        fake_resp.save = mock.MagicMock()

        with mock.patch('dashboard.views.QuestionResponse') as QR, \
             mock.patch('dashboard.views.Question') as Q:
            QR.objects.using.return_value.filter.return_value.first.return_value = fake_resp
            qobj = mock.MagicMock()
            qobj.teacher_id = 42
            qobj.room_id = 7
            Q.objects.using.return_value.filter.return_value.first.return_value = qobj

            resp = self.client.post(reverse('dashboard:grade_response', args=[41]), {
                'score': '-5',
                'feedback': 'Negative'
            }, follow=True)

        self.assertEqual(resp.status_code, 200)
        self.assertIn('grade_response_form', resp.context)
        form = resp.context['grade_response_form']
        self.assertTrue(form.errors)
        self.assertIn('score', form.errors)
        fake_resp.save.assert_not_called()

        # Too large score (>100)
        fake_resp2 = mock.MagicMock()
        fake_resp2.id = 42
        fake_resp2.question_id = 101
        fake_resp2.score = None
        fake_resp2.feedback = None
        fake_resp2.is_graded = False
        fake_resp2.grader_id = None
        fake_resp2.save = mock.MagicMock()

        with mock.patch('dashboard.views.QuestionResponse') as QR2, \
             mock.patch('dashboard.views.Question') as Q2:
            QR2.objects.using.return_value.filter.return_value.first.return_value = fake_resp2
            qobj2 = mock.MagicMock()
            qobj2.teacher_id = 42
            qobj2.room_id = 8
            Q2.objects.using.return_value.filter.return_value.first.return_value = qobj2

            resp2 = self.client.post(reverse('dashboard:grade_response', args=[42]), {
                'score': '150',
                'feedback': 'Too big'
            }, follow=True)

        self.assertEqual(resp2.status_code, 200)
        self.assertIn('grade_response_form', resp2.context)
        form2 = resp2.context['grade_response_form']
        self.assertTrue(form2.errors)
        self.assertIn('score', form2.errors)
        fake_resp2.save.assert_not_called()
