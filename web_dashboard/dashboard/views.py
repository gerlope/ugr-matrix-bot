import sys
import requests
from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect
from django.contrib import messages
from django.views.decorators.http import require_POST
from django.contrib.auth import login
from django.contrib.auth.models import User
from pathlib import Path
from .models import Room, ExternalUser
from .forms import ExternalLoginForm, CreateRoomForm

# add repo root (two levels above this views.py) to sys.path so "import config" works
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from config import MOODLE_URL, MOODLE_TOKEN

@login_required(login_url='login')
def dashboard(request):
    teacher = request.session.get('teacher')

    if not teacher:
        return redirect('login')
    selected_room_id = request.GET.get('room_id')
    selected_room = None
    selected_course = None

    # Fetch courses from Moodle API
    endpoint = f"{MOODLE_URL}/webservice/rest/server.php"
    params = {
        'wstoken': MOODLE_TOKEN,
        'wsfunction': 'core_enrol_get_users_courses',
        'moodlewsrestformat': 'json',
        'userid': teacher["moodle_id"],
    }

    try:
        resp = requests.get(endpoint, params=params, timeout=20)
        resp.raise_for_status()
        courses_data = resp.json()
    except Exception as e:
        courses_data = []
        print(f"[Dashboard] Error fetching courses: {e}")


    # Get all rooms belonging to this teacher from PostgreSQL
    teacher_rooms = Room.objects.using('postgresql').filter(teacher_id=teacher['id'])
    general_rooms = Room.objects.using('postgresql').filter(teacher_id=None)

    # Group rooms by course ID for easy rendering
    course_list = []
    for course in courses_data:
        is_open = "false"
        course_id = course.get('id')
        general_room = next((room for room in general_rooms if room.moodle_course_id == course_id), None)
        course_rooms = [room for room in teacher_rooms if room.moodle_course_id == course_id]
        if selected_room_id and selected_room_id in [str(r.id) for r in course_rooms + ([general_room] if general_room else [])]:
            is_open = "true"
            selected_room = next((r for r in course_rooms + ([general_room] if general_room else []) if str(r.id) == selected_room_id), None)
            selected_course = course

        course_list.append({
            'id': course_id,
            'shortname': course.get('shortname'),
            'fullname': course.get('fullname'),
            'displayname': course.get('displayname'),
            'general_room': general_room,
            'rooms': course_rooms,
            'is_open': is_open,
        })

    return render(request, 'dashboard/dashboard.html', {
        'teacher': teacher,
        'courses': course_list,
        'selected_room_id': int(selected_room_id) if selected_room_id else None,
        'selected_room': selected_room,
        'selected_course': selected_course,
    })



def external_login(request):
    if request.method == "POST":
        form = ExternalLoginForm(request.POST)
        if form.is_valid():
            username = "@" + form.cleaned_data['username'] + ":matrix.example.org"

            try:
                teacher = ExternalUser.objects.using('postgresql').filter(matrix_id=username).first()
                if teacher:
                    if not teacher.is_teacher:
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
                    request.session['teacher'] = teacher.__dict__()
                    
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

@require_POST
def create_room(request):
    teacher = request.session.get('teacher')
    form = CreateRoomForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Formulario inválido. Por favor, revise los datos.")
        return redirect('dashboard')
    
    course_id = form.cleaned_data['course_id']
    shortcode = form.cleaned_data['shortcode']

    if not (course_id and shortcode):
        messages.error(request, "Todos los campos son obligatorios.")
        return redirect('dashboard')

    # Crear la sala en la base de datos
    Room.objects.using('postgresql').create(
        moodle_course_id=course_id,
        teacher_id=teacher['id'],
        shortcode=shortcode,
        room_id="TEMPORAL"+str(shortcode)+str(teacher['id'])  # Puedes generar el room_id real más adelante
    )

    messages.success(request, f"Sala '{shortcode}' creada correctamente.")
    return redirect('dashboard')