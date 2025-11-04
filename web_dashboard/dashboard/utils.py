import sys
import requests
from concurrent.futures import ThreadPoolExecutor
from django.db.models import Sum, Max
from pathlib import Path
from .models import ExternalUser, Reaction, Room, Question, QuestionOption, ResponseOption, QuestionResponse
from django.utils import timezone


# add repo root (two levels above this views.py) to sys.path so "import config" works
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from config import MOODLE_URL, MOODLE_TOKEN

def get_data_for_dashboard(teacher, selected_room_id = None):
    selected_room = None
    selected_course = None
    selected_students = None
    selected_questions = None

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
    teacher_rooms = Room.objects.using('postgresql').filter(teacher_id=teacher['id'], active=True)
    general_rooms = Room.objects.using('postgresql').filter(teacher_id=None)

    course_list = []
    thread_results = [None] * len(courses_data)

    # Run tasks in parallel threads
    with ThreadPoolExecutor() as executor:
        futures = [
            executor.submit(
                process_course_data,
                course, general_rooms, teacher_rooms,
                teacher, selected_room_id, thread_results, i
            )
            for i, course in enumerate(courses_data)
        ]
    
        # Wait for all to finish
        for f in futures:
            f.result()
    
    for data in thread_results:
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

    endpoint = f"{MOODLE_URL}/webservice/rest/server.php"

    params = {
        'wstoken': MOODLE_TOKEN,
        'wsfunction': 'core_group_get_course_groups',
        'moodlewsrestformat': 'json',
        'courseid': course_id,
    }
    try:
        resp = requests.get(endpoint, params=params, timeout=20)
        resp.raise_for_status()
        groups_data = resp.json()
    except Exception as e:
        groups_data = []
        print(f"[Dashboard] Error fetching groups for course {course.get('shortname')}: {e}")

    for group in groups_data:
        groups.append({
            'id': group.get('id'),
            'name': group.get('name'),
        })
    
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

        params = {
            'wstoken': MOODLE_TOKEN,
            'wsfunction': 'core_enrol_get_enrolled_users',
            'moodlewsrestformat': 'json',
            'courseid': course_id,
        }

        try:
            resp = requests.get(endpoint, params=params, timeout=20)
            resp.raise_for_status()
            enrolled_data = resp.json()
        except Exception as e:
            enrolled_data = []
            print(f"[Dashboard] Error fetching students: {e}")

        if selected_room.teacher_id is None and selected_room.shortcode == course.get('shortname'):
            selected_reactions = (Reaction.objects.using('postgresql').filter(teacher_id=teacher['id'],
                                                                              room_id__in=[room.id for room in course_rooms + ([general_room] if general_room else [])])
                                                                      .values('student_id', 'emoji')
                                                                      .annotate(total_count=Sum('count'), 
                                                                                latest_update=Max('last_updated')))                

            selected_students = []
            student_moodle_ids = [s['id'] for s in enrolled_data if s.get('roles') and any(r['shortname'] == 'student' for r in s['roles'])]
            student_db_data = ExternalUser.objects.using('postgresql').filter(moodle_id__in=student_moodle_ids)
            
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
            selected_reactions = (Reaction.objects.using('postgresql').filter(teacher_id=teacher['id'], 
                                                                              room_id=selected_room_id)
                                                                      .values('student_id', 'emoji')
                                                                      .annotate(total_count=Sum('count'), 
                                                                                latest_update=Max('last_updated')))
            
            selected_students = []
            participants_matrix_ids = [] #GET FROM MATRIX API
            student_db_data = ExternalUser.objects.using('postgresql').filter(matrix_id__in=participants_matrix_ids)

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
        try:
            room_db_id = selected_room.id if selected_room is not None else None
            if room_db_id is not None:
                qs = list(Question.objects.using('postgresql').filter(room_id=room_db_id).order_by('-created_at'))
                qids = [q.id for q in qs]
                question_options = {}
                if qids:
                    opts = QuestionOption.objects.using('postgresql').filter(question_id__in=qids).order_by('question_id', 'position')
                    for opt in opts:
                        question_options.setdefault(opt.question_id, []).append(opt)
                now = timezone.now()
                selected_questions = []
                for q in qs:
                    # If both start_at and end_at are missing, treat as NOT within window by default
                    if q.start_at is None and q.end_at is None:
                        within_window = False
                    else:
                        within_window = True
                        try:
                            within_window = ((q.start_at is None or now >= q.start_at) and (q.end_at is None or now <= q.end_at))
                        except Exception:
                            within_window = True

                    # Determine whether now is before start or after end (for labeling)
                    before_start = False
                    after_end = False
                    try:
                        if q.start_at is not None and now < q.start_at:
                            before_start = True
                        if q.end_at is not None and now > q.end_at:
                            after_end = True
                    except Exception:
                        pass

                    # Active only if manual_active OR within the time window
                    is_currently_active = bool(q.manual_active) or within_window
                    selected_questions.append({
                        'question': q,
                        'options': question_options.get(q.id, []),
                        'is_currently_active': is_currently_active,
                        'within_window': within_window,
                        'before_start': before_start,
                        'after_end': after_end,
                        'responses': []  # will be filled below if any
                    })

                # Attach responses for these questions (if any)
                try:
                    if qids:
                        # Fetch responses and response_options
                        resp_qs = list(QuestionResponse.objects.using('postgresql').filter(question_id__in=qids).order_by('-submitted_at'))
                        resp_ids = [r.id for r in resp_qs]
                        resp_opts_map = {}
                        if resp_ids:
                            resp_opts = ResponseOption.objects.using('postgresql').filter(response_id__in=resp_ids)
                            for ro in resp_opts:
                                resp_opts_map.setdefault(ro.response_id, []).append(ro.option_id)

                        # Map student DB ids to matrix ids (for display)
                        student_ids = list({r.student_id for r in resp_qs})
                        students_map = {}
                        if student_ids:
                            users = ExternalUser.objects.using('postgresql').filter(id__in=student_ids)
                            for u in users:
                                students_map[u.id] = u

                        # Build a map of question_id -> list of response dicts
                        q_responses = {}
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

                        # Attach to selected_questions entries
                        for entry in selected_questions:
                            qobj = entry['question']
                            entry['responses'] = q_responses.get(qobj.id, [])
                except Exception as e:
                    print(f"[WARN] Could not fetch question responses: {e}")
        except Exception as e:
            print(f"[WARN] Could not fetch questions for room {course.get('shortname')}: {e}")
    
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