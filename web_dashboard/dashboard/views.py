import sys
from django.db import IntegrityError
from django.shortcuts import get_object_or_404, render
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
from .forms import ExternalLoginForm, CreateRoomForm, CreateQuestionForm
from django.db import connections, OperationalError
from .models import Question, QuestionOption
from django.utils import timezone


# add repo root (two levels above this views.py) to sys.path so "import config" works
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from config import HOMESERVER

@login_required(login_url='login')
def dashboard(request):
    teacher = request.session.get('teacher')

    if not teacher:
        return redirect('login')
    
    selected_room_id = request.GET.get('room_id', None)

    data = get_data_for_dashboard(teacher, selected_room_id)

    # Questions are loaded by get_data_for_dashboard into selected_questions
    questions_list = data.get('selected_questions', []) or []

    return render(request, 'dashboard/dashboard.html', {
        'teacher': teacher,
        'courses': data['courses'],
        'selected_room': data['selected_room'],
        'selected_course': data['selected_course'],
        'students': data['selected_students'],
        'questions_list': questions_list,
    })



def external_login(request):
    if request.method == "POST":
        form = ExternalLoginForm(request.POST)
        if form.is_valid():
            username = "@" + form.cleaned_data['username'] + ":" + HOMESERVER.split("//")[1].split("/")[0]

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
    
@require_POST
@login_required(login_url='login')
def deactivate_room(request, room_id):
    teacher = request.session.get('teacher')
    if not teacher:
        return redirect('login')

    room = get_object_or_404(Room.objects.using('postgresql'), id=room_id)

    # Only the owner teacher can deactivate it
    if room.teacher_id != teacher['id']:
        messages.error(request, "No tienes permiso para cerrar esta sala.")
        return redirect(f"{reverse('dashboard')}?room_id={room.id}")

    room.active = False
    room.save(using='postgresql')
    messages.success(request, f"La sala '{room.shortcode}' ha sido cerrada correctamente.")
    return redirect('dashboard')


@require_POST
@login_required(login_url='login')
def create_question(request):
    teacher = request.session.get('teacher')
    if not teacher:
        return redirect('login')

    form = CreateQuestionForm(request.POST)
    selected_room_id = request.POST.get('selected_room_id')

    if not form.is_valid():
        data = get_data_for_dashboard(teacher, selected_room_id)
        return render(request, 'dashboard/dashboard.html', {
            'teacher': teacher,
            'courses': data['courses'],
            'selected_room': data['selected_room'],
            'selected_course': data['selected_course'],
            'students': data['selected_students'],
            'create_question_form': form,
            'show_create_question_modal': 'true',
        })

    # permission: ensure teacher owns the room
    room = None
    if selected_room_id:
        room = Room.objects.using('postgresql').filter(id=selected_room_id).first()

    if not room or room.teacher_id != teacher['id']:
        messages.error(request, "No tienes permiso para añadir preguntas en esta sala.")
        return redirect(f"{reverse('dashboard')}?room_id={selected_room_id}")

    # create question
    try:
        q = Question.objects.using('postgresql').create(
            teacher_id=teacher['id'],
            room_id=room.id,
            title=form.cleaned_data.get('title') or None,
            body=form.cleaned_data['body'],
            qtype=form.cleaned_data['qtype'],
            start_at=form.cleaned_data.get('start_at'),
            end_at=form.cleaned_data.get('end_at'),
            manual_active=False,
            allow_multiple_submissions=form.cleaned_data.get('allow_multiple_submissions', False),
            allow_multiple_answers=form.cleaned_data.get('allow_multiple_answers', False)
        )

        # gather dynamic option_* fields
        options = []
        for key, val in request.POST.items():
            if key.startswith('option_') and val.strip():
                options.append(val.strip())

        # create options
        for idx, opt_text in enumerate(options):
            QuestionOption.objects.using('postgresql').create(
                question_id=q.id,
                option_key=chr(65 + (idx % 26)),
                text=opt_text,
                is_correct=False,
                position=idx
            )

        messages.success(request, "Pregunta creada correctamente.")
        return redirect(f"{reverse('dashboard')}?room_id={room.id}")
    except Exception as e:
        form.add_error(None, f"Error creando la pregunta: {e}")
        data = get_data_for_dashboard(teacher, selected_room_id)
        return render(request, 'dashboard/dashboard.html', {
            'teacher': teacher,
            'courses': data['courses'],
            'selected_room': data['selected_room'],
            'selected_course': data['selected_course'],
            'students': data['selected_students'],
            'create_question_form': form,
            'show_create_question_modal': 'true',
        })


@require_POST
@login_required(login_url='login')
def toggle_question_active(request, question_id):
    teacher = request.session.get('teacher')
    if not teacher:
        return redirect('login')

    q = Question.objects.using('postgresql').filter(id=question_id).first()
    if not q:
        messages.error(request, "Pregunta no encontrada.")
        return redirect('dashboard')

    if q.teacher_id != teacher['id']:
        messages.error(request, "No tienes permiso para modificar esta pregunta.")
        return redirect('dashboard')

    now = timezone.now()
    try:
        # If the question has no start_at and no end_at, the template shows manual-only buttons;
        # in that case we should only toggle the manual_active override.
        if q.start_at is None and q.end_at is None:
            q.manual_active = not bool(q.manual_active)
            q.save(using='postgresql')
            messages.success(request, f"Campo manual_active actualizado (ahora={'sí' if q.manual_active else 'no'}).")
            return redirect(f"{reverse('dashboard')}?room_id={q.room_id}")

        # If the question has already finished (end_at in the past), use manual_active toggle instead
        if q.end_at is not None and q.end_at < now:
            q.manual_active = not bool(q.manual_active)
            q.save(using='postgresql')
            messages.success(request, f"Campo manual_active actualizado (ahora={'sí' if q.manual_active else 'no'}).")
            return redirect(f"{reverse('dashboard')}?room_id={q.room_id}")

        # If currently within window (active now), then 'finalizar ahora' -> set end_at to now
        within_window = True
        try:
            within_window = ((q.start_at is None or now >= q.start_at) and (q.end_at is None or now <= q.end_at))
        except Exception:
            within_window = True

        if within_window:
            # finalize now
            q.end_at = now
            # ensure manual_active is False when using window-based control
            q.manual_active = False
            q.save(using='postgresql')
            messages.success(request, "Pregunta finalizada ahora (end_at actualizada).")
            return redirect(f"{reverse('dashboard')}?room_id={q.room_id}")

        # Otherwise (not within window and not finished), start now by setting start_at to now
        q.start_at = now
        # ensure manual_active is False when using window-based control
        q.manual_active = False
        q.save(using='postgresql')
        messages.success(request, "Pregunta iniciada ahora (start_at actualizada).")
    except Exception as e:
        messages.error(request, f"Error al actualizar la pregunta: {e}")

    return redirect(f"{reverse('dashboard')}?room_id={q.room_id}")



@require_POST
@login_required(login_url='login')
def delete_question(request, question_id):
    teacher = request.session.get('teacher')
    if not teacher:
        return redirect('login')

    q = Question.objects.using('postgresql').filter(id=question_id).first()
    if not q:
        messages.error(request, "Pregunta no encontrada.")
        return redirect('dashboard')

    if q.teacher_id != teacher['id']:
        messages.error(request, "No tienes permiso para eliminar esta pregunta.")
        return redirect('dashboard')

    try:
        # delete the question and cascade to options/responses
        q.delete(using='postgresql')
        messages.success(request, "Pregunta eliminada correctamente.")
    except Exception as e:
        messages.error(request, f"Error al eliminar la pregunta: {e}")

    return redirect(f"{reverse('dashboard')}?room_id={q.room_id}")