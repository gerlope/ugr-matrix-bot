"""Dashboard utility functions.

This module centralizes logic used by the dashboard views for:
 - Building availability timelines
 - Fetching & assembling Moodle + internal (bot_db) data for courses/rooms/questions
 - Overlap validation for teacher availability intervals
 - Preparing common schedule context

The original implementation mixed networking, aggregation and presentation logic
in large monolithic functions. The refactor below splits responsibilities into
small helpers while keeping public function names (``build_availability_display``
and ``get_data_for_dashboard``) stable to avoid widespread code changes.
"""

from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, Iterable, List, Optional, Tuple

import requests
from django.db.models import Max, Sum
from django.utils import timezone

from .models import (
    ExternalUser,
    Reaction,
    Room,
    Question,
    QuestionOption,
    ResponseOption,
    QuestionResponse,
    TeacherAvailability,
)
from config import MOODLE_TOKEN, MOODLE_URL

WEEK_DAYS_ES = ['Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado', 'Domingo']

# ---------------------------------------------------------------------------
# Availability helpers
# ---------------------------------------------------------------------------


def build_availability_display(avail_rows, timeline_start_hour: int = 7, timeline_end_hour: int = 21) -> Dict[str, Any]:
    """Builds availability dict, days_with_slots and timeline hours for templates.

    Returns a dict with keys: en_to_es, timeline_hours, availability, days_with_slots,
    timeline_start_hour, timeline_end_hour, timeline_span
    """
    en_to_es = {
        'Monday': 'Lunes', 'Tuesday': 'Martes', 'Wednesday': 'Miércoles',
        'Thursday': 'Jueves', 'Friday': 'Viernes', 'Saturday': 'Sábado', 'Sunday': 'Domingo'
    }
    timeline_span = timeline_end_hour - timeline_start_hour

    # Initialize availability dict
    availability = {v: [] for v in en_to_es.values()}

    for a in avail_rows:
        day_en = (a.day_of_week or '')
        day_es = en_to_es.get(day_en, day_en)
        # defaults
        left_pct = 0.0
        width_pct = 0.0
        top_pct = 0.0
        height_pct = 0.0
        try:
            sh = a.start_time.hour + a.start_time.minute / 60.0
            eh = a.end_time.hour + a.end_time.minute / 60.0
            # clamp to timeline window
            sh_clamped = max(timeline_start_hour, min(sh, timeline_end_hour))
            eh_clamped = max(timeline_start_hour, min(eh, timeline_end_hour))
            left_pct = ((sh_clamped - timeline_start_hour) / timeline_span) * 100
            width_pct = ((max(eh_clamped, sh_clamped) - sh_clamped) / timeline_span) * 100
            # For vertical rendering we map left->top and width->height
            top_pct = left_pct
            height_pct = width_pct
            start_s = a.start_time.strftime('%H:%M') if a.start_time else ''
            end_s = a.end_time.strftime('%H:%M') if a.end_time else ''
        except Exception:
            # fallback values if time parsing fails
            start_s = str(a.start_time)
            end_s = str(a.end_time)
            left_pct = 0.0
            width_pct = 0.0
            top_pct = 0.0
            height_pct = 0.0

        availability.setdefault(day_es, []).append({
            'id': getattr(a, 'id', None),
            'start': start_s,
            'end': end_s,
            'left_pct': left_pct,
            'width_pct': width_pct,
            'top_pct': top_pct,
            'height_pct': height_pct,
        })

    week_days = WEEK_DAYS_ES
    timeline_hours = list(range(timeline_start_hour, timeline_end_hour))
    days_with_slots = []
    for d in week_days:
        days_with_slots.append({'day': d, 'slots': availability.get(d, [])})

    return {
        'en_to_es': en_to_es,
        'timeline_hours': timeline_hours,
        'availability': availability,
        'days_with_slots': days_with_slots,
        'timeline_start_hour': timeline_start_hour,
        'timeline_end_hour': timeline_end_hour,
        'timeline_span': timeline_span,
    }


def check_availability_overlap(teacher_id: int, day: str, start_time, end_time, exclude_id: Optional[int] = None):
    """Return the conflicting availability instance if the interval overlaps, else None.

    Overlap rule: (new_start < existing_end) AND (new_end > existing_start)
    ``exclude_id`` allows ignoring self for edits.
    """
    qs = ExternalUser.objects.none()  # placeholder for type; real queryset below

    q = TeacherAvailability.objects.using('bot_db').filter(teacher_id=teacher_id, day_of_week=day)
    if exclude_id is not None:
        q = q.exclude(id=exclude_id)
    for existing in q:
        try:
            if start_time < existing.end_time and end_time > existing.start_time:
                return existing
        except Exception:
            # Ignore problematic rows (corrupted times)
            continue
    return None


# ---------------------------------------------------------------------------
# Moodle / external data fetch helpers
# ---------------------------------------------------------------------------
def _moodle_endpoint() -> str:
    return f"{MOODLE_URL}/webservice/rest/server.php"


def fetch_moodle_courses(teacher: Dict[str, Any]) -> List[Dict[str, Any]]:
    params = {
        'wstoken': MOODLE_TOKEN,
        'wsfunction': 'core_enrol_get_users_courses',
        'moodlewsrestformat': 'json',
        'userid': teacher["moodle_id"],
    }
    try:
        resp = requests.get(_moodle_endpoint(), params=params, timeout=20)
        resp.raise_for_status()
        return resp.json() or []
    except Exception as e:
        print(f"[Dashboard] Error fetching courses: {e}")
        return []


def fetch_moodle_groups(course_id: int) -> List[Dict[str, Any]]:
    params = {
        'wstoken': MOODLE_TOKEN,
        'wsfunction': 'core_group_get_course_groups',
        'moodlewsrestformat': 'json',
        'courseid': course_id,
    }
    try:
        resp = requests.get(_moodle_endpoint(), params=params, timeout=20)
        resp.raise_for_status()
        groups_data = resp.json() or []
    except Exception as e:
        print(f"[Dashboard] Error fetching groups for course {course_id}: {e}")
        return []
    return [{'id': g.get('id'), 'name': g.get('name')} for g in groups_data]


def fetch_enrolled_students(course_id: int) -> List[Dict[str, Any]]:
    params = {
        'wstoken': MOODLE_TOKEN,
        'wsfunction': 'core_enrol_get_enrolled_users',
        'moodlewsrestformat': 'json',
        'courseid': course_id,
    }
    try:
        resp = requests.get(_moodle_endpoint(), params=params, timeout=20)
        resp.raise_for_status()
        return resp.json() or []
    except Exception as e:
        print(f"[Dashboard] Error fetching enrolled users for course {course_id}: {e}")
        return []


def assemble_questions_for_room(selected_room, teacher_id: int) -> List[Dict[str, Any]]:
    """Collect questions/options/responses for a given room.

    Keeps logic mostly identical to prior implementation while improving readability.
    """
    if selected_room is None:
        return []
    try:
        qs = list(Question.objects.using('bot_db').filter(room_id=selected_room.id).order_by('-created_at'))
        qids = [q.id for q in qs]
        question_options: Dict[int, List[QuestionOption]] = {}
        if qids:
            opts = QuestionOption.objects.using('bot_db').filter(question_id__in=qids).order_by('question_id', 'position')
            for opt in opts:
                question_options.setdefault(opt.question_id, []).append(opt)
        now = timezone.now()
        selected_questions: List[Dict[str, Any]] = []
        for q in qs:
            if q.start_at is None and q.end_at is None:
                within_window = False
            else:
                try:
                    within_window = ((q.start_at is None or now >= q.start_at) and (q.end_at is None or now <= q.end_at))
                except Exception:
                    within_window = True

            before_start = False
            after_end = False
            try:
                if q.start_at is not None and now < q.start_at:
                    before_start = True
                if q.end_at is not None and now > q.end_at:
                    after_end = True
            except Exception:
                pass

            is_currently_active = bool(q.manual_active) or within_window
            selected_questions.append({
                'question': q,
                'options': question_options.get(q.id, []),
                'is_currently_active': is_currently_active,
                'within_window': within_window,
                'before_start': before_start,
                'after_end': after_end,
                'responses': [],
            })

        # Attach responses
        if qids:
            try:
                resp_qs = list(QuestionResponse.objects.using('bot_db').filter(question_id__in=qids).order_by('-submitted_at'))
                resp_ids = [r.id for r in resp_qs]
                resp_opts_map: Dict[int, List[int]] = {}
                if resp_ids:
                    resp_opts = ResponseOption.objects.using('bot_db').filter(response_id__in=resp_ids)
                    for ro in resp_opts:
                        resp_opts_map.setdefault(ro.response_id, []).append(ro.option_id)

                student_ids = list({r.student_id for r in resp_qs})
                students_map: Dict[int, ExternalUser] = {}
                if student_ids:
                    users = ExternalUser.objects.using('bot_db').filter(id__in=student_ids)
                    for u in users:
                        students_map[u.id] = u

                q_responses: Dict[int, List[Dict[str, Any]]] = {}
                for r in resp_qs:
                    q_responses.setdefault(r.question_id, []).append({
                        'id': r.id,
                        'student_id': r.student_id,
                        'student': students_map.get(r.student_id),
                        'option_id': r.option_id,
                        'option_ids': resp_opts_map.get(r.id, []),
                        'answer_text': r.answer_text,
                        'submitted_at': r.submitted_at,
                        'score': getattr(r, 'score', None),
                    })

                for entry in selected_questions:
                    qobj = entry['question']
                    entry['responses'] = q_responses.get(qobj.id, [])
            except Exception as e:
                print(f"[WARN] Could not fetch question responses: {e}")
        return selected_questions
    except Exception as e:
        print(f"[WARN] Could not fetch questions for room {getattr(selected_room, 'shortcode', 'UNKNOWN')}: {e}")
        return []


# ---------------------------------------------------------------------------
# Original high-level dashboard data assembly (still exported)
# ---------------------------------------------------------------------------

def get_data_for_dashboard(teacher: Dict[str, Any], selected_room_id: Optional[str] = None) -> Dict[str, Any]:
    """Aggregate courses + room/question/student data for dashboard rendering.

    Returns keys: courses, selected_room, selected_course, selected_students, selected_questions.
    Maintains original semantics for consumers.
    """
    selected_room = None
    selected_course = None
    selected_students = None
    selected_questions = None

    courses_data = fetch_moodle_courses(teacher)
    teacher_rooms = Room.objects.using('bot_db').filter(teacher_id=teacher['id'], active=True)
    general_rooms = Room.objects.using('bot_db').filter(teacher_id=None)

    course_list: List[Dict[str, Any]] = []
    thread_results: List[Optional[Dict[str, Any]]] = [None] * len(courses_data)

    # Run tasks concurrently for per-course assembly
    with ThreadPoolExecutor() as executor:
        futures = [
            executor.submit(
                process_course_data,
                course,
                general_rooms,
                teacher_rooms,
                teacher,
                selected_room_id,
                thread_results,
                i,
            )
            for i, course in enumerate(courses_data)
        ]
        for f in futures:
            f.result()  # propagate exceptions early

    for data in thread_results:
        if not data:
            continue
        if data['selected_course'] is not None:
            selected_course = data['selected_course']
            selected_room = data['selected_room']
            selected_students = data['selected_students']
            selected_questions = data['selected_questions']
        course_list.append({
            'id': data.get('id'),
            'shortname': data.get('shortname'),
            'fullname': data.get('fullname'),
            'displayname': data.get('displayname'),
            'general_room': data['general_room'],
            'teachers_room': data['teachers_room'],
            'rooms': data['rooms'],
            'groups': data['groups'],
            'is_open': data['is_open'],
        })

    return {
        'courses': course_list,
        'selected_room': selected_room,
        'selected_course': selected_course,
        'selected_students': selected_students,
        'selected_questions': selected_questions,
    }


def process_course_data(course, general_rooms, teacher_rooms, teacher, selected_room_id, thread_results, index):
    selected_room = None
    selected_course = None
    selected_reactions = None
    selected_students = None
    selected_questions = None
    is_open = "false"
    course_id = course.get('id')
    general_room = next((room for room in general_rooms if room.shortcode == course.get('shortname')), None)
    teachers_room = next((room for room in general_rooms if room.shortcode == course.get('shortname')+"_teachers"), None)
    course_rooms = [room for room in teacher_rooms if room.moodle_course_id == course_id]
    all_rooms = course_rooms + ([general_room] if general_room else []) + ([teachers_room] if teachers_room else [])
    groups = []

    groups = fetch_moodle_groups(course_id)
    
    if selected_room_id and selected_room_id in [str(r.id) for r in all_rooms]:
        is_open = "true"
        selected_room = next((r for r in all_rooms if str(r.id) == selected_room_id), None)
        selected_course = {
            'id': course_id,
            'shortname': course.get('shortname'),
            'fullname': course.get('fullname'),
            'displayname': course.get('displayname'),
            'general_room': general_room,
            'teachers_room': teachers_room,
            'rooms': course_rooms,
            'groups': groups,
            'is_open': is_open,
        }

        enrolled_data = fetch_enrolled_students(course_id)

        if selected_room.teacher_id is None and selected_room.shortcode == course.get('shortname'):
            selected_reactions = (Reaction.objects.using('bot_db').filter(teacher_id=teacher['id'],
                                                                              room_id__in=[room.id for room in course_rooms + ([general_room] if general_room else [])])
                                                                      .values('student_id', 'emoji')
                                                                      .annotate(total_count=Sum('count'), 
                                                                                latest_update=Max('last_updated')))                

            selected_students = []
            student_moodle_ids = [s['id'] for s in enrolled_data if s.get('roles') and any(r['shortname'] == 'student' for r in s['roles'])]
            student_db_data = ExternalUser.objects.using('bot_db').filter(moodle_id__in=student_moodle_ids)
            
            for student in student_db_data:
                moodle_user = next((s for s in enrolled_data if s['id'] == student.moodle_id), None)
                selected_students.append({
                    'moodle_id': student.moodle_id,
                    'matrix_id': student.matrix_id,
                    'full_name': moodle_user.get('fullname', None) if moodle_user else 'Desconocido',
                    'reactions': [r for r in selected_reactions if r['student_id'] == student.id],
                    'groups': moodle_user.get('groups', None) if moodle_user else []
                })   
        elif selected_room.teacher_id == teacher['id']:
            selected_reactions = (Reaction.objects.using('bot_db').filter(teacher_id=teacher['id'], 
                                                                              room_id=selected_room_id)
                                                                      .values('student_id', 'emoji')
                                                                      .annotate(total_count=Sum('count'), 
                                                                                latest_update=Max('last_updated')))
            
            selected_students = []
            participants_matrix_ids = [] #GET FROM MATRIX API
            student_db_data = ExternalUser.objects.using('bot_db').filter(matrix_id__in=participants_matrix_ids)

            for student in student_db_data:
                moodle_user = next((s for s in enrolled_data if s['id'] == student.moodle_id), None)
                selected_students.append({
                    'moodle_id': student.moodle_id,
                    'matrix_id': student.matrix_id,
                    'full_name': moodle_user.get('fullname', None) if moodle_user else 'Desconocido',
                    'reactions': [r for r in selected_reactions if r['student_id'] == student.id],
                    'groups': moodle_user.get('groups', None) if moodle_user else []
                })
        # Fetch all questions for this selected room (including inactive / manual flags)
        selected_questions = assemble_questions_for_room(selected_room, teacher['id'])
    
    thread_results[index] = {
        'id': course_id,
        'shortname': course.get('shortname'),
        'fullname': course.get('fullname'),
        'displayname': course.get('displayname'),
        'general_room': general_room,
        'teachers_room': teachers_room,
        'rooms': course_rooms,
        'groups': groups,
        'is_open': is_open,
        'selected_room': selected_room,
        'selected_course': selected_course,
        'selected_reactions': selected_reactions,
        'selected_students': selected_students,
        'selected_questions': selected_questions,
    }