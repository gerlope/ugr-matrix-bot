import sys
from django.db import IntegrityError
from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect
from django.contrib import messages
from django.urls import reverse
from django.views.decorators.http import require_POST
from django.contrib.auth import login
from django.contrib.auth.models import User
from pathlib import Path

from .utils import get_data_for_dashboard
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
    
    selected_room_id = request.GET.get('room_id', None)

    data = get_data_for_dashboard(teacher, selected_room_id)


    return render(request, 'dashboard/dashboard.html', {
        'teacher': teacher,
        'courses': data['courses'],
        'selected_room': data['selected_room'],
        'selected_course': data['selected_course'],
        'students': data['selected_students'],
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
        data = get_data_for_dashboard(teacher, selected_room_id)
        return render(request, 'dashboard/dashboard.html', {
            'teacher': teacher,
            'courses': data['courses'],
            'selected_room': data['selected_room'],
            'selected_course': data['selected_course'],
            'students': data['selected_students'],
            'create_room_form': form,
            'show_create_modal': "true",
        })
    
    selected_room_id = request.POST.get('selected_room_id', None)
    print(f"[DEBUG] create_room called with selected_room_id={selected_room_id}")
    
    course_id = form.cleaned_data['course_id']
    shortcode = form.cleaned_data['shortcode']
    moodle_group = form.cleaned_data.get('moodle_group', None)
    auto_invite = form.cleaned_data.get('auto_invite', False)
    restrict_group = form.cleaned_data.get('restrict_group', False)

    try:
        room = Room.objects.using('postgresql').create(
            moodle_course_id=course_id,
            teacher_id=teacher['id'],
            shortcode=shortcode,
            room_id=f"TEMP_{shortcode}_{teacher['id']}",
            moodle_group=moodle_group if moodle_group and restrict_group else None,
        )

        if moodle_group is not None and auto_invite:
            print(f"[INFO] Invitando miembros del grupo {moodle_group} a la sala {room.shortcode}")

        messages.success(request, f"Sala '{shortcode}' creada correctamente.")
        
        # Redirect to dashboard with room_id as GET parameter
        dashboard_url = f"{reverse('dashboard')}?room_id={room.id}"
        return redirect(dashboard_url)
    
    except IntegrityError as e:
        if "unique" in str(e).lower():
            form.add_error('shortcode', "Ya existe una sala con este nombre.")
        else:
            form.add_error(None, f"Error al crear la sala: {e}")

        data = get_data_for_dashboard(teacher, selected_room_id)
        return render(request, 'dashboard/dashboard.html', {
            'teacher': teacher,
            'courses': data['courses'],
            'selected_room': data['selected_room'],
            'selected_course': data['selected_course'],
            'students': data['selected_students'],
            'create_room_form': form,
            'show_create_modal': "true",
        })
    except Exception as e:
        form.add_error(None, f"Error al crear la sala: {e}")
        data = get_data_for_dashboard(teacher, selected_room_id)
        return render(request, 'dashboard/dashboard.html', {
            'teacher': teacher,
            'courses': data['courses'],
            'selected_room': data['selected_room'],
            'selected_course': data['selected_course'],
            'students': data['selected_students'],
            'create_room_form': form,
            'show_create_modal': "true",
        })