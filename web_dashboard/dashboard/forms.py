# menu/forms.py
from django import forms

class ExternalLoginForm(forms.Form):
    username = forms.CharField(max_length=255)
    #password = forms.CharField(widget=forms.PasswordInput)

class CreateRoomForm(forms.Form):
    course_id = forms.IntegerField()
    shortcode = forms.CharField(max_length=100)
    moodle_group = forms.CharField(max_length=100, required=False)
    auto_invite = forms.BooleanField(required=False, initial=False)
    restrict_group = forms.BooleanField(required=False, initial=False)


class CreateQuestionForm(forms.Form):
    title = forms.CharField(max_length=255, required=False)
    body = forms.CharField(widget=forms.Textarea, required=True)
    QTYPE_CHOICES = [
        ('multiple_choice', 'Opción múltiple'),
        ('true_false', 'Verdadero/Falso'),
        ('short_answer', 'Respuesta corta'),
        ('numeric', 'Numérica'),
        ('essay', 'Desarrollo'),
    ]
    qtype = forms.ChoiceField(choices=QTYPE_CHOICES)
    start_at = forms.DateTimeField(required=False, input_formats=['%Y-%m-%dT%H:%M'])
    end_at = forms.DateTimeField(required=False, input_formats=['%Y-%m-%dT%H:%M'])
    allow_multiple_answers = forms.BooleanField(required=False, initial=False)
    allow_multiple_submissions = forms.BooleanField(required=False, initial=False)