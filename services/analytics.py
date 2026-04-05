import statistics

from accounts.models import User
from assignments.models import StudentAssignment, StudentAnswer


def compute_analytics(assignment_ids, student_ids):
    """
    Compute all analytics data for the given assignment and student filters.
    Returns a dict with: summary, distribution, student_breakdown, weakest_sections, most_missed.
    """
    if not assignment_ids or not student_ids:
        return _empty_result()

    completed_sas = StudentAssignment.objects.filter(
        assignment_id__in=assignment_ids,
        student_id__in=student_ids,
        status='COMPLETED',
    ).select_related('student', 'assignment')

    # Per-student averages
    student_scores = _per_student_scores(completed_sas)

    summary = _compute_summary(student_scores, completed_sas)
    distribution = _compute_distribution(student_scores)
    student_breakdown = _compute_breakdown(student_scores, completed_sas, len(assignment_ids))

    # Answer-level analysis
    answers = StudentAnswer.objects.filter(
        student_assignment__in=completed_sas,
    ).select_related('question__section__chapter')

    weakest_sections = _compute_weakest_sections(answers)
    most_missed = _compute_most_missed(answers)

    return {
        'summary': summary,
        'distribution': distribution,
        'student_breakdown': student_breakdown,
        'weakest_sections': weakest_sections,
        'most_missed': most_missed,
    }


def _empty_result():
    return {
        'summary': {
            'mean': 0, 'median': 0, 'stdev': 0, 'pass_rate': 0,
            'avg_time_min': 0,
            'highest': {'name': '\u2014', 'score': 0},
            'lowest': {'name': '\u2014', 'score': 0},
        },
        'distribution': [0] * 11,
        'student_breakdown': [],
        'weakest_sections': [],
        'most_missed': [],
    }


def _per_student_scores(completed_sas):
    from collections import defaultdict
    student_data = defaultdict(lambda: {'scores': [], 'times': [], 'name': '', 'student_id': None})

    for sa in completed_sas:
        if sa.max_score and sa.score is not None:
            pct = sa.score / sa.max_score * 100
            sid = sa.student_id
            student_data[sid]['scores'].append(pct)
            student_data[sid]['times'].append(sa.total_time_seconds)
            student_data[sid]['name'] = sa.student.get_full_name() or sa.student.username
            student_data[sid]['student_id'] = sid

    result = []
    for sid, data in student_data.items():
        avg_score = sum(data['scores']) / len(data['scores']) if data['scores'] else 0
        avg_time = sum(data['times']) / len(data['times']) if data['times'] else 0
        result.append({
            'student_id': sid,
            'name': data['name'],
            'avg_score': round(avg_score, 2),
            'avg_time': avg_time,
            'completed': len(data['scores']),
        })
    return result


def _compute_summary(student_scores, completed_sas):
    if not student_scores:
        return _empty_result()['summary']

    scores = [s['avg_score'] for s in student_scores]
    times = [sa.total_time_seconds for sa in completed_sas]

    mean_val = statistics.mean(scores)
    median_val = statistics.median(scores)
    stdev_val = statistics.stdev(scores) if len(scores) > 1 else 0
    pass_rate = sum(1 for s in scores if s >= 70) / len(scores) * 100

    avg_time_sec = statistics.mean(times) if times else 0
    avg_time_min = round(avg_time_sec / 60, 1)

    sorted_scores = sorted(student_scores, key=lambda x: x['avg_score'], reverse=True)

    return {
        'mean': round(mean_val, 1),
        'median': round(median_val, 1),
        'stdev': round(stdev_val, 2),
        'pass_rate': round(pass_rate, 1),
        'avg_time_min': avg_time_min,
        'highest': {'name': sorted_scores[0]['name'], 'score': sorted_scores[0]['avg_score']},
        'lowest': {'name': sorted_scores[-1]['name'], 'score': sorted_scores[-1]['avg_score']},
    }


def _compute_distribution(student_scores):
    buckets = [0] * 11
    for s in student_scores:
        idx = int(s['avg_score'] / 10)
        buckets[min(idx, 10)] += 1
    return buckets


def _compute_breakdown(student_scores, completed_sas, num_assignments):
    from collections import defaultdict
    accuracy_map = defaultdict(lambda: {'correct': 0, 'total': 0})
    for sa in completed_sas:
        answers = sa.answers.all()
        for ans in answers:
            sid = sa.student_id
            accuracy_map[sid]['total'] += 1
            if ans.is_correct:
                accuracy_map[sid]['correct'] += 1

    breakdown = []
    for s in student_scores:
        sid = s['student_id']
        acc = accuracy_map[sid]
        accuracy = round(acc['correct'] / acc['total'] * 100, 1) if acc['total'] > 0 else 0
        breakdown.append({
            'name': s['name'],
            'student_id': sid,
            'completed': s['completed'],
            'total_assignments': num_assignments,
            'avg_score': s['avg_score'],
            'accuracy': accuracy,
            'avg_time_min': round(s['avg_time'] / 60, 1),
        })

    breakdown.sort(key=lambda x: x['avg_score'], reverse=True)
    return breakdown


def _compute_weakest_sections(answers):
    from collections import defaultdict
    section_data = defaultdict(lambda: {'correct': 0, 'total': 0, 'number': '', 'title': ''})

    for ans in answers:
        sec = ans.question.section
        key = sec.pk
        section_data[key]['total'] += 1
        if ans.is_correct:
            section_data[key]['correct'] += 1
        section_data[key]['number'] = sec.number
        section_data[key]['title'] = sec.title

    result = []
    for key, data in section_data.items():
        if data['total'] >= 5:
            accuracy = round(data['correct'] / data['total'] * 100, 1)
            result.append({
                'section_number': data['number'],
                'title': data['title'],
                'attempts': data['total'],
                'accuracy': accuracy,
            })

    result.sort(key=lambda x: x['accuracy'])
    return result[:10]


def _compute_most_missed(answers):
    from collections import defaultdict
    q_data = defaultdict(lambda: {'correct': 0, 'total': 0, 'uid': '', 'text': '', 'section': ''})

    for ans in answers:
        q = ans.question
        key = q.pk
        q_data[key]['total'] += 1
        if ans.is_correct:
            q_data[key]['correct'] += 1
        q_data[key]['uid'] = q.uid
        q_data[key]['text'] = q.text[:60]
        q_data[key]['section'] = q.section.number

    result = []
    for key, data in q_data.items():
        if data['total'] >= 3:
            error_rate = round((data['total'] - data['correct']) / data['total'] * 100, 1)
            result.append({
                'uid': data['uid'],
                'text': data['text'],
                'times_asked': data['total'],
                'error_rate': error_rate,
                'section': data['section'],
            })

    result.sort(key=lambda x: x['error_rate'], reverse=True)
    return result
