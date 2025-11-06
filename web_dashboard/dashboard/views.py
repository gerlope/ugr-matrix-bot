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

from .utils import get_data_for_dashboard, build_availability_display
from .models import Room, ExternalUser, TeacherAvailability
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
        'selected_page': 'dashboard',
    })


@login_required(login_url='login')
def tutoring_schedule(request):
    teacher = request.session.get('teacher')
    if not teacher:
        return redirect('login')

    # reuse get_data_for_dashboard to populate the sidebar courses
    data = get_data_for_dashboard(teacher, None)

    # Fetch availability rows for this teacher from external DB and build display data
    avail_rows = TeacherAvailability.objects.using('postgresql').filter(teacher_id=teacher['id']).order_by('day_of_week', 'start_time')
    avail_display = build_availability_display(avail_rows, timeline_start_hour=7, timeline_end_hour=21)
    days_with_slots = avail_display['days_with_slots']
    timeline_hours = avail_display['timeline_hours']
    availability = avail_display['availability']

    week_days = ['Lunes','Martes','Miércoles','Jueves','Viernes','Sábado','Domingo']

    return render(request, 'dashboard/schedule.html', {
        'teacher': teacher,
        'courses': data['courses'],
        'selected_room': data['selected_room'],
        'selected_course': data['selected_course'],
        'selected_page': 'schedule',
        'week_days': week_days,
        'availability': availability,
        'timeline_hours': timeline_hours,
        'days_with_slots': days_with_slots,
    })


@require_POST
@login_required(login_url='login')
def create_availability(request):
    teacher = request.session.get('teacher')
    if not teacher:
        return redirect('login')

    from .forms import CreateAvailabilityForm
    form = CreateAvailabilityForm(request.POST)

    if not form.is_valid():
        # re-render schedule with form errors and show modal
        data = get_data_for_dashboard(teacher, None)

        # recompute availability and days_with_slots using utility
        avail_rows = TeacherAvailability.objects.using('postgresql').filter(teacher_id=teacher['id']).order_by('day_of_week', 'start_time')
        avail_display = build_availability_display(avail_rows, timeline_start_hour=7, timeline_end_hour=21)
        days_with_slots = avail_display['days_with_slots']
        timeline_hours = avail_display['timeline_hours']

        week_days = ['Lunes','Martes','Miércoles','Jueves','Viernes','Sábado','Domingo']

        return render(request, 'dashboard/schedule.html', {
            'teacher': teacher,
            'courses': data['courses'],
            'selected_room': data['selected_room'],
            'selected_course': data['selected_course'],
            'selected_page': 'schedule',
            'week_days': week_days,
            'timeline_hours': timeline_hours,
            'days_with_slots': days_with_slots,
            'create_availability_form': form,
            'show_create_availability_modal': 'true',
        })

    # validate no overlap with existing availabilities
    day = form.cleaned_data['day_of_week']
    st = form.cleaned_data['start_time']
    et = form.cleaned_data['end_time']

    existing = TeacherAvailability.objects.using('postgresql').filter(teacher_id=teacher['id'], day_of_week=day)
    for a in existing:
        try:
            if (st < a.end_time and et > a.start_time):
                form.add_error(None, 'El intervalo se solapa con otro existente (%s - %s).' % (a.start_time.strftime('%H:%M'), a.end_time.strftime('%H:%M')))
                data = get_data_for_dashboard(teacher, None)

                # recompute availability/days_with_slots using utility
                avail_rows = TeacherAvailability.objects.using('postgresql').filter(teacher_id=teacher['id']).order_by('day_of_week', 'start_time')
                avail_display = build_availability_display(avail_rows, timeline_start_hour=7, timeline_end_hour=21)
                days_with_slots = avail_display['days_with_slots']
                timeline_hours = avail_display['timeline_hours']

                week_days = ['Lunes','Martes','Miércoles','Jueves','Viernes','Sábado','Domingo']

                return render(request, 'dashboard/schedule.html', {
                    'teacher': teacher,
                    'courses': data['courses'],
                    'selected_room': data['selected_room'],
                    'selected_course': data['selected_course'],
                    'selected_page': 'schedule',
                    'week_days': week_days,
                    'timeline_hours': timeline_hours,
                    'days_with_slots': days_with_slots,
                    'create_availability_form': form,
                    'show_create_availability_modal': 'true',
                })
        except Exception:
            continue

    # create availability
    try:
        TeacherAvailability.objects.using('postgresql').create(
            teacher_id=teacher['id'],
            day_of_week=day,
            start_time=st,
            end_time=et
        )
        messages.success(request, 'Intervalo creado correctamente.')
    except Exception as e:
        messages.error(request, f'Error al crear el intervalo: {e}')

    return redirect('tutoring_schedule')



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
@login_required(login_url='login')
def delete_availability(request):
    """Delete a teacher availability slot (POST: avail_id).

    Only the logged-in teacher may delete their own availability rows.
    """
    teacher = request.session.get('teacher')
    if not teacher:
        return redirect('login')

    try:
        avail_id = int(request.POST.get('avail_id'))
    except Exception:
        messages.error(request, "ID de disponibilidad inválido.")
        return redirect('tutoring_schedule')

    a = TeacherAvailability.objects.using('postgresql').filter(id=avail_id).first()
    if not a:
        messages.error(request, "Disponibilidad no encontrada.")
        return redirect('tutoring_schedule')

    if a.teacher_id != teacher['id']:
        messages.error(request, "No tienes permiso para eliminar esta disponibilidad.")
        return redirect('tutoring_schedule')

    try:
        # instance delete on external DB
        a.delete(using='postgresql')
        messages.success(request, "Intervalo eliminado correctamente.")
    except Exception as e:
        messages.error(request, f"Error al eliminar la disponibilidad: {e}")

    return redirect('tutoring_schedule')


@require_POST
@login_required(login_url='login')
def edit_availability(request):
    """Edit an existing availability slot (POST: avail_id, start_time, end_time)."""
    teacher = request.session.get('teacher')
    if not teacher:
        return redirect('login')

    from .forms import EditAvailabilityForm
    form = EditAvailabilityForm(request.POST)

    try:
        avail_id = int(request.POST.get('avail_id'))
    except Exception:
        messages.error(request, "ID de disponibilidad inválido.")
        return redirect('tutoring_schedule')

    a = TeacherAvailability.objects.using('postgresql').filter(id=avail_id).first()
    if not a:
        messages.error(request, "Disponibilidad no encontrada.")
        return redirect('tutoring_schedule')

    if a.teacher_id != teacher['id']:
        messages.error(request, "No tienes permiso para editar esta disponibilidad.")
        return redirect('tutoring_schedule')

    # common helpers used when re-rendering the schedule (used below in overlap/error paths)
    en_to_es = {
        'Monday': 'Lunes', 'Tuesday': 'Martes', 'Wednesday': 'Miércoles',
        'Thursday': 'Jueves', 'Friday': 'Viernes', 'Saturday': 'Sábado', 'Sunday': 'Domingo'
    }
    timeline_start_hour = 7
    timeline_end_hour = 21
    timeline_span = timeline_end_hour - timeline_start_hour

    if not form.is_valid():
        # re-render schedule with form errors and show edit modal
        data = get_data_for_dashboard(teacher, None)

        # recompute availability/days_with_slots using helper
        avail_rows = TeacherAvailability.objects.using('postgresql').filter(teacher_id=teacher['id']).order_by('day_of_week', 'start_time')
        avail_display = build_availability_display(avail_rows, timeline_start_hour=timeline_start_hour, timeline_end_hour=timeline_end_hour)
        days_with_slots = avail_display['days_with_slots']
        timeline_hours = avail_display['timeline_hours']
        week_days = ['Lunes','Martes','Miércoles','Jueves','Viernes','Sábado','Domingo']

        return render(request, 'dashboard/schedule.html', {
            'teacher': teacher,
            'courses': data['courses'],
            'selected_room': data['selected_room'],
            'selected_course': data['selected_course'],
            'selected_page': 'schedule',
            'week_days': week_days,
            'timeline_hours': timeline_hours,
            'days_with_slots': days_with_slots,
            'edit_availability_form': form,
            'show_edit_availability_modal': 'true',
            'edit_availability_id': avail_id,
        })

    # validate no overlap with existing availabilities (exclude self)
    st = form.cleaned_data['start_time']
    et = form.cleaned_data['end_time']
    day = a.day_of_week

    existing = TeacherAvailability.objects.using('postgresql').filter(teacher_id=teacher['id'], day_of_week=day).exclude(id=avail_id)
    for ex in existing:
        try:
            if (st < ex.end_time and et > ex.start_time):
                form.add_error(None, 'El intervalo se solapa con otro existente (%s - %s).' % (ex.start_time.strftime('%H:%M'), ex.end_time.strftime('%H:%M')))
                data = get_data_for_dashboard(teacher, None)

                # recompute availability/days_with_slots using helper
                avail_rows = TeacherAvailability.objects.using('postgresql').filter(teacher_id=teacher['id']).order_by('day_of_week', 'start_time')
                avail_display = build_availability_display(avail_rows, timeline_start_hour=timeline_start_hour, timeline_end_hour=timeline_end_hour)
                days_with_slots = avail_display['days_with_slots']
                timeline_hours = avail_display['timeline_hours']
                week_days = ['Lunes','Martes','Miércoles','Jueves','Viernes','Sábado','Domingo']

                return render(request, 'dashboard/schedule.html', {
                    'teacher': teacher,
                    'courses': data['courses'],
                    'selected_room': data['selected_room'],
                    'selected_course': data['selected_course'],
                    'selected_page': 'schedule',
                    'week_days': week_days,
                    'timeline_hours': timeline_hours,
                    'days_with_slots': days_with_slots,
                    'edit_availability_form': form,
                    'show_edit_availability_modal': 'true',
                    'edit_availability_id': avail_id,
                })
        except Exception:
            continue

    # perform update
    try:
        a.start_time = st
        a.end_time = et
        a.save(using='postgresql')
        messages.success(request, 'Intervalo actualizado correctamente.')
    except Exception as e:
        messages.error(request, f'Error al actualizar el intervalo: {e}')

    return redirect('tutoring_schedule')

@require_POST
def create_room(request):
    teacher = request.session.get('teacher')
    form = CreateRoomForm(request.POST)

    selected_room_id = request.POST.get('selected_room_id', None)
    print(f"[DEBUG] create_room called with selected_room_id={selected_room_id}")

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

        # gather dynamic option_* fields into an index-ordered list
        options_map = {}
        for key, val in request.POST.items():
            if key.startswith('option_') and val and val.strip():
                try:
                    idx = int(key.split('_', 1)[1])
                except Exception:
                    continue
                options_map[idx] = val.strip()
        options = [options_map[i] for i in sorted(options_map.keys())]

        qtype = form.cleaned_data.get('qtype')

        # create options and mark correct ones based on posted flags
        if qtype == 'short_answer' or qtype == 'numeric':
            # store expected answer as a single option (is_correct=True)
            expected = request.POST.get('expected_answer', '').strip()
            if expected:
                QuestionOption.objects.using('postgresql').create(
                    question_id=q.id,
                    option_key='ANSWER',
                    text=expected,
                    is_correct=True,
                    position=0
                )
        elif qtype == 'true_false':
            # options should be provided as option_0=Verdadero, option_1=Falso (hidden inputs)
            tf_correct = request.POST.get('tf_correct')  # '0' or '1'
            for idx, opt_text in enumerate(options):
                is_correct = (str(idx) == str(tf_correct)) if tf_correct is not None else False
                QuestionOption.objects.using('postgresql').create(
                    question_id=q.id,
                    option_key=chr(65 + (idx % 26)),
                    text=opt_text,
                    is_correct=is_correct,
                    position=idx
                )
        else:
            # multiple_choice (default): support single-selection (radio) or multi-selection (checkbox)
            single_choice = request.POST.get('option_correct_single')
            for idx, opt_text in enumerate(options):
                if single_choice is not None and single_choice != '':
                    is_correct = (str(idx) == str(single_choice))
                else:
                    correct_flag = request.POST.get(f'option_correct_{idx}')
                    is_correct = bool(correct_flag)

                QuestionOption.objects.using('postgresql').create(
                    question_id=q.id,
                    option_key=chr(65 + (idx % 26)),
                    text=opt_text,
                    is_correct=is_correct,
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