# menu/forms.py
from django import forms

class ExternalLoginForm(forms.Form):
    username = forms.CharField(max_length=255)
    #password = forms.CharField(widget=forms.PasswordInput)
