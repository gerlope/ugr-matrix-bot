import sys
from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.db import connections
from django.shortcuts import redirect
import requests
from .forms import ExternalLoginForm
from django.contrib.auth import login
from django.contrib.auth.models import User
from pathlib import Path

# add repo root (two levels above this views.py) to sys.path so "import config" works
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from config import MOODLE_URL, MOODLE_TOKEN

@login_required(login_url='login')
def dashboard(request):
    moodle_id = request.session.get('moodle_id')
    endpoint = f"{MOODLE_URL}/webservice/rest/server.php"
    params = {
        'wstoken': MOODLE_TOKEN,
        'wsfunction': 'core_enrol_get_users_courses',
        'moodlewsrestformat': 'json',
        'userid': moodle_id,
    }

    resp = requests.get(endpoint, params=params, timeout=20)
    resp.raise_for_status()
    courses_data = resp.json()
    
    return render(request, "dashboard/dashboard.html", {
        "courses": courses_data,
        "username": request.user.username,
        "moodle_id": moodle_id,
    })

def external_login(request):
    if request.method == "POST":
        form = ExternalLoginForm(request.POST)
        if form.is_valid():
            username = form.cleaned_data['username']
            username = "@" + username + ":matrix.example.org"

            try:
                with connections['postgresql'].cursor() as cursor:
                    # Consulta personalizada
                    cursor.execute(
                        "SELECT moodle_id, is_teacher FROM users WHERE matrix_id = %s",
                        [username]
                    )
                    row = cursor.fetchone()
                    if row:
                        moodle_id, is_teacher = row

                        if not is_teacher:
                            form.add_error(None, "Acceso denegado: no es profesor")
                            return render(request, "dashboard/login.html", {"form": form})

                        # Mapear a usuario Django
                        user, created = User.objects.get_or_create(
                            username=username,
                            defaults={
                                'first_name': '',  # si no hay nombre en esta tabla
                                'last_name': '',
                                'email': '',
                                'password': '!'  # no hay password Django
                            }
                        )

                        # Guardar datos en sesión
                        request.session['moodle_id'] = moodle_id

                        # Loguear en Django
                        login(request, user)

                        return redirect('dashboard')
                    else:
                        form.add_error(None, "Usuario no encontrado")
            except Exception as e:
                form.add_error(None, f"Error al conectar con la base externa: {e}")
    else:
        form = ExternalLoginForm()

    return render(request, "dashboard/login.html", {"form": form})