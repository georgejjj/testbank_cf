# Instructor Analytics Page Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a dedicated instructor "Analyze" page with filterable score distributions, summary statistics, student breakdowns, weakest sections, most-missed questions, and CSV exports.

**Architecture:** Single new view (`instructor_analyze`) handles both initial GET and HTMX POST for filter changes. Two additional GET views handle CSV exports. The template uses HTMX to swap the `#analytics-content` div when filters change. All data is derived from existing `StudentAssignment` and `StudentAnswer` models — no schema changes.

**Tech Stack:** Django views, Python `statistics` module, Chart.js 4 (existing CDN), HTMX 1.9 (existing), Bootstrap 5 collapse (existing)

---

### Task 1: URL Routes

**Files:**
- Modify: `apps/assignments/urls.py`

- [ ] **Step 1: Add the three new URL patterns**

In `apps/assignments/urls.py`, add these three paths in the `# Instructor` section (after the `export-grades/` line at line 11):

```python
path('analyze/', views.instructor_analyze, name='instructor_analyze'),
path('analyze/export-raw/', views.export_raw_scores, name='export_raw_scores'),
path('analyze/export-breakdown/', views.export_breakdown, name='export_breakdown'),
```

- [ ] **Step 2: Verify no import changes needed**

The file already imports `from . import views`, so no new imports are required.

- [ ] **Step 3: Commit**

```bash
git add apps/assignments/urls.py
git commit -m "feat(analytics): add URL routes for instructor analyze page and CSV exports"
```

---

### Task 2: Navbar Link

**Files:**
- Modify: `templates/base.html:75-80`

- [ ] **Step 1: Add Analyze nav item for instructors**

In `templates/base.html`, find the instructor Messages nav item (line 76-79). Add this new `<li>` immediately **before** it (between the Students `</li>` and the Messages `<li>`):

```html
          <li class="nav-item">
            <a class="nav-link" href="{% url 'instructor_analyze' %}">
              <i class="bi bi-bar-chart-line me-1"></i>Analyze
            </a>
          </li>
```

- [ ] **Step 2: Verify in browser**

Run: `python3 manage.py runserver 0.0.0.0:8000`

Log in as instructor. Confirm "Analyze" link appears in the navbar between "Students" and "Messages". Clicking it will 404 until the view exists — that's expected.

- [ ] **Step 3: Commit**

```bash
git add templates/base.html
git commit -m "feat(analytics): add Analyze link to instructor navbar"
```

---

### Task 3: Analytics Computation Service

**Files:**
- Create: `services/analytics.py`
- Create: `tests/test_analytics.py`

This service contains all the analytics computation logic, keeping the view thin. It takes filtered querysets and returns plain data structures.

- [ ] **Step 1: Write tests for the analytics service**

Create `tests/test_analytics.py`:

```python
from django.test import TestCase
from accounts.models import User
from questions.models import Chapter, Section, Question, MCChoice
from assignments.models import Assignment, StudentAssignment, StudentAnswer, AssignedQuestion
from services.analytics import compute_analytics


class AnalyticsServiceTest(TestCase):
    def setUp(self):
        self.instructor = User.objects.create_user(
            username='prof', password='pass', role='INSTRUCTOR',
            first_name='Prof', last_name='Smith',
        )
        self.ch = Chapter.objects.create(number=4, title='Time Value of Money')
        self.sec1 = Section.objects.create(chapter=self.ch, number='4.1', title='The Timeline', sort_order=1)
        self.sec2 = Section.objects.create(chapter=self.ch, number='4.2', title='Three Rules', sort_order=2)

        # Create 4 MC questions: 2 in sec1, 2 in sec2
        self.questions = []
        for i, sec in enumerate([self.sec1, self.sec1, self.sec2, self.sec2], start=1):
            q = Question.objects.create(
                section=sec, question_type='MC', text=f'Question {i}',
                difficulty=1, skill='Conceptual', question_number=i, global_number=i,
            )
            MCChoice.objects.create(question=q, letter='A', text='Right', is_correct=True)
            MCChoice.objects.create(question=q, letter='B', text='Wrong', is_correct=False)
            self.questions.append(q)

        # Assignment with 4 questions
        self.a1 = Assignment.objects.create(
            title='HW1', created_by=self.instructor, num_questions=4, mode='ASSIGNMENT', is_published=True,
        )

        # Student A: scores 3/4 (75%)
        self.student_a = User.objects.create_user(
            username='alice', password='pass', role='STUDENT',
            first_name='Alice', last_name='Adams',
        )
        sa_a = StudentAssignment.objects.create(
            student=self.student_a, assignment=self.a1,
            status='COMPLETED', score=3, max_score=4, total_time_seconds=600,
        )
        for i, q in enumerate(self.questions):
            AssignedQuestion.objects.create(student_assignment=sa_a, question=q, position=i)
            StudentAnswer.objects.create(
                student_assignment=sa_a, question=q,
                is_correct=(i < 3),  # first 3 correct, last wrong
            )

        # Student B: scores 1/4 (25%)
        self.student_b = User.objects.create_user(
            username='bob', password='pass', role='STUDENT',
            first_name='Bob', last_name='Brown',
        )
        sa_b = StudentAssignment.objects.create(
            student=self.student_b, assignment=self.a1,
            status='COMPLETED', score=1, max_score=4, total_time_seconds=1200,
        )
        for i, q in enumerate(self.questions):
            AssignedQuestion.objects.create(student_assignment=sa_b, question=q, position=i)
            StudentAnswer.objects.create(
                student_assignment=sa_b, question=q,
                is_correct=(i == 0),  # only first correct
            )

    def test_summary_stats(self):
        assignment_ids = [self.a1.pk]
        student_ids = [self.student_a.pk, self.student_b.pk]
        result = compute_analytics(assignment_ids, student_ids)
        stats = result['summary']
        # Alice=75%, Bob=25% → mean=50, median=50
        self.assertAlmostEqual(stats['mean'], 50.0)
        self.assertAlmostEqual(stats['median'], 50.0)
        self.assertAlmostEqual(stats['stdev'], 35.36, places=1)
        self.assertAlmostEqual(stats['pass_rate'], 50.0)  # only Alice >= 70
        self.assertAlmostEqual(stats['avg_time_min'], 15.0)  # (600+1200)/2/60
        self.assertEqual(stats['highest']['name'], 'Alice Adams')
        self.assertAlmostEqual(stats['highest']['score'], 75.0)
        self.assertEqual(stats['lowest']['name'], 'Bob Brown')
        self.assertAlmostEqual(stats['lowest']['score'], 25.0)

    def test_score_distribution(self):
        assignment_ids = [self.a1.pk]
        student_ids = [self.student_a.pk, self.student_b.pk]
        result = compute_analytics(assignment_ids, student_ids)
        dist = result['distribution']
        # 11 buckets: indices 0-10. Alice=75%→bucket 7, Bob=25%→bucket 2
        self.assertEqual(len(dist), 11)
        self.assertEqual(dist[7], 1)  # Alice
        self.assertEqual(dist[2], 1)  # Bob

    def test_student_breakdown(self):
        assignment_ids = [self.a1.pk]
        student_ids = [self.student_a.pk, self.student_b.pk]
        result = compute_analytics(assignment_ids, student_ids)
        breakdown = result['student_breakdown']
        # Sorted by avg_score descending
        self.assertEqual(len(breakdown), 2)
        self.assertEqual(breakdown[0]['name'], 'Alice Adams')
        self.assertAlmostEqual(breakdown[0]['avg_score'], 75.0)
        self.assertEqual(breakdown[0]['completed'], 1)
        self.assertEqual(breakdown[0]['total_assignments'], 1)
        self.assertEqual(breakdown[1]['name'], 'Bob Brown')

    def test_weakest_sections(self):
        assignment_ids = [self.a1.pk]
        student_ids = [self.student_a.pk, self.student_b.pk]
        result = compute_analytics(assignment_ids, student_ids)
        sections = result['weakest_sections']
        # sec1: 4 correct out of 4 (Alice 2/2 + Bob 1/2) → wait, let me recount
        # sec1 has q0, q1. Alice: q0=correct, q1=correct. Bob: q0=correct, q1=wrong → 3/4 = 75%
        # sec2 has q2, q3. Alice: q2=correct, q3=wrong. Bob: q2=wrong, q3=wrong → 1/4 = 25%
        # Weakest first → sec2 at 25%, sec1 at 75%
        self.assertEqual(sections[0]['section_number'], '4.2')
        self.assertAlmostEqual(sections[0]['accuracy'], 25.0)
        self.assertEqual(sections[1]['section_number'], '4.1')
        self.assertAlmostEqual(sections[1]['accuracy'], 75.0)

    def test_most_missed_questions(self):
        assignment_ids = [self.a1.pk]
        student_ids = [self.student_a.pk, self.student_b.pk]
        result = compute_analytics(assignment_ids, student_ids)
        questions = result['most_missed']
        # q3 (idx 3): 0/2 correct → 100% error. q2 (idx 2): 1/2 → 50%. q1: 1/2 → 50%. q0: 2/2 → 0%
        self.assertEqual(questions[0]['uid'], 'CH4-004')
        self.assertAlmostEqual(questions[0]['error_rate'], 100.0)

    def test_filter_by_student(self):
        """Filtering to only Alice should produce 75% mean."""
        result = compute_analytics([self.a1.pk], [self.student_a.pk])
        self.assertAlmostEqual(result['summary']['mean'], 75.0)
        self.assertEqual(len(result['student_breakdown']), 1)

    def test_empty_selection(self):
        """No assignments selected returns empty/zero results."""
        result = compute_analytics([], [self.student_a.pk])
        self.assertAlmostEqual(result['summary']['mean'], 0)
        self.assertEqual(result['distribution'], [0] * 11)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 manage.py test tests.test_analytics -v2`

Expected: `ModuleNotFoundError: No module named 'services.analytics'`

- [ ] **Step 3: Implement the analytics service**

Create `services/analytics.py`:

```python
import statistics

from django.db.models import Q, Sum, Count, Case, When, IntegerField

from accounts.models import User
from assignments.models import Assignment, StudentAssignment, StudentAnswer


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
    student_scores = _per_student_scores(completed_sas, assignment_ids, student_ids)

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
            'highest': {'name': '—', 'score': 0},
            'lowest': {'name': '—', 'score': 0},
        },
        'distribution': [0] * 11,
        'student_breakdown': [],
        'weakest_sections': [],
        'most_missed': [],
    }


def _per_student_scores(completed_sas, assignment_ids, student_ids):
    """Return list of {student_id, name, avg_score_pct, total_time} for students with completions."""
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
    """Build per-student breakdown with accuracy (correct/total answers)."""
    from collections import defaultdict

    # Compute per-student accuracy from answers
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 manage.py test tests.test_analytics -v2`

Expected: All 7 tests pass. Note: `test_weakest_sections` has a min-attempts threshold of 5 — our test data has only 4 answers per section (2 students × 2 questions), so it will return an empty list. Let's fix the test:

The `test_weakest_sections` test has 2 questions per section × 2 students = 4 attempts per section, which is below the threshold of 5. Update the threshold check: in the test, since we have 4 attempts per section (below 5), the sections list will be empty. We need to either lower the threshold or add more data. Let's adjust the test to account for this:

Replace the `test_weakest_sections` method in `tests/test_analytics.py`:

```python
    def test_weakest_sections(self):
        # Each section has 4 attempts (2 students × 2 questions), below the min=5 threshold
        # Add a third student to push over the threshold
        student_c = User.objects.create_user(
            username='carol', password='pass', role='STUDENT',
            first_name='Carol', last_name='Clark',
        )
        sa_c = StudentAssignment.objects.create(
            student=student_c, assignment=self.a1,
            status='COMPLETED', score=2, max_score=4, total_time_seconds=900,
        )
        for i, q in enumerate(self.questions):
            AssignedQuestion.objects.create(student_assignment=sa_c, question=q, position=i)
            StudentAnswer.objects.create(
                student_assignment=sa_c, question=q,
                is_correct=(i < 2),  # first 2 correct
            )

        assignment_ids = [self.a1.pk]
        student_ids = [self.student_a.pk, self.student_b.pk, student_c.pk]
        result = compute_analytics(assignment_ids, student_ids)
        sections = result['weakest_sections']
        # sec1 (q0,q1): Alice 2/2, Bob 1/2, Carol 2/2 → 5/6 ≈ 83.3%
        # sec2 (q2,q3): Alice 1/2, Bob 0/2, Carol 0/2 → 1/6 ≈ 16.7%
        # Weakest first → sec2
        self.assertGreaterEqual(len(sections), 2)
        self.assertEqual(sections[0]['section_number'], '4.2')
        self.assertAlmostEqual(sections[0]['accuracy'], 16.7, places=1)
```

- [ ] **Step 5: Run tests again**

Run: `python3 manage.py test tests.test_analytics -v2`

Expected: All 7 tests pass.

- [ ] **Step 6: Commit**

```bash
git add services/analytics.py tests/test_analytics.py
git commit -m "feat(analytics): add analytics computation service with tests"
```

---

### Task 4: View Functions

**Files:**
- Modify: `apps/assignments/views.py`

- [ ] **Step 1: Add the main analyze view**

At the top of `apps/assignments/views.py`, add to the existing imports (line 1):

```python
import csv
from datetime import date
from django.http import HttpResponse
```

Note: `csv` may already be imported locally in `export_grades` — adding it at the top is cleaner. `HttpResponse` is not yet imported at the top level. Check the existing imports: `HttpResponseForbidden` and `JsonResponse` are there but not `HttpResponse`. Add `HttpResponse` to the existing `django.http` import line.

Also add the service import below the existing service imports (around line 14):

```python
from services.analytics import compute_analytics
```

Then add this view function after the `export_grades` function (around line 1030):

```python
@login_required
def instructor_analyze(request):
    if not request.user.is_instructor:
        return redirect('student_dashboard')

    # All published non-practice assignments
    all_assignments = Assignment.objects.filter(
        is_published=True, mode='ASSIGNMENT',
    ).exclude(created_by__role='STUDENT').order_by('created_at')

    all_students = User.objects.filter(role='STUDENT').order_by('last_name', 'first_name')

    # Parse selected IDs from POST (HTMX) or default to all
    if request.method == 'POST':
        selected_assignment_ids = request.POST.getlist('assignment_ids')
        selected_student_ids = request.POST.getlist('student_ids')
        # Convert to ints, ignore invalid
        selected_assignment_ids = [int(x) for x in selected_assignment_ids if x.isdigit()]
        selected_student_ids = [int(x) for x in selected_student_ids if x.isdigit()]
    else:
        selected_assignment_ids = list(all_assignments.values_list('pk', flat=True))
        selected_student_ids = list(all_students.values_list('pk', flat=True))

    analytics = compute_analytics(selected_assignment_ids, selected_student_ids)

    context = {
        'all_assignments': all_assignments,
        'all_students': all_students,
        'selected_assignment_ids': selected_assignment_ids,
        'selected_student_ids': selected_student_ids,
        'analytics': analytics,
        'distribution_json': json.dumps(analytics['distribution']),
        'num_assignments': len(selected_assignment_ids),
        'num_students': len(selected_student_ids),
    }

    if request.headers.get('HX-Request'):
        return render(request, 'assignments/instructor/analyze_content.html', context)

    return render(request, 'assignments/instructor/analyze.html', context)
```

- [ ] **Step 2: Add CSV export views**

Add these two views right after `instructor_analyze`:

```python
@login_required
def export_raw_scores(request):
    if not request.user.is_instructor:
        return redirect('student_dashboard')

    assignment_ids = request.GET.getlist('a')
    student_ids = request.GET.getlist('s')
    assignment_ids = [int(x) for x in assignment_ids if x.isdigit()]
    student_ids = [int(x) for x in student_ids if x.isdigit()]

    assignments = Assignment.objects.filter(pk__in=assignment_ids).order_by('created_at')
    students = User.objects.filter(pk__in=student_ids, role='STUDENT').order_by('last_name', 'first_name')

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="raw_scores_{date.today()}.csv"'
    writer = csv.writer(response)

    header = ['Student'] + [a.title for a in assignments]
    writer.writerow(header)

    for student in students:
        row = [student.get_full_name() or student.username]
        for a in assignments:
            sa = StudentAssignment.objects.filter(
                student=student, assignment=a, status='COMPLETED',
            ).first()
            if sa and sa.score is not None:
                row.append(f'{sa.score}/{sa.max_score}')
            else:
                row.append('—')
        writer.writerow(row)

    return response


@login_required
def export_breakdown(request):
    if not request.user.is_instructor:
        return redirect('student_dashboard')

    assignment_ids = request.GET.getlist('a')
    student_ids = request.GET.getlist('s')
    assignment_ids = [int(x) for x in assignment_ids if x.isdigit()]
    student_ids = [int(x) for x in student_ids if x.isdigit()]

    analytics = compute_analytics(assignment_ids, student_ids)

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="student_breakdown_{date.today()}.csv"'
    writer = csv.writer(response)

    writer.writerow(['Rank', 'Student', 'Completed', 'Avg Score %', 'Accuracy %', 'Avg Time (min)'])

    for i, s in enumerate(analytics['student_breakdown'], 1):
        writer.writerow([
            i,
            s['name'],
            f"{s['completed']}/{s['total_assignments']}",
            s['avg_score'],
            s['accuracy'],
            s['avg_time_min'],
        ])

    return response
```

- [ ] **Step 3: Commit**

```bash
git add apps/assignments/views.py
git commit -m "feat(analytics): add instructor_analyze view and CSV export views"
```

---

### Task 5: Main Template (Full Page)

**Files:**
- Create: `templates/assignments/instructor/analyze.html`

- [ ] **Step 1: Create the main analyze template**

Create `templates/assignments/instructor/analyze.html`:

```html
{% extends "base.html" %}
{% block title %}Analyze - TestBank{% endblock %}
{% block content %}
<div class="page-header">
    <h2><i class="bi bi-bar-chart-line me-2" style="color: var(--gold);"></i>Analyze</h2>
    <p class="page-subtitle">Score analysis across assignments and students</p>
</div>

{% csrf_token %}

<!-- Filters -->
<div class="row g-3 mb-4">
    <!-- Assignment Selector -->
    <div class="col-md-6">
        <div class="card fade-in">
            <div class="card-header d-flex justify-content-between align-items-center">
                <span><i class="bi bi-journal-check me-2"></i>Assignments</span>
                <div>
                    <button type="button" class="btn btn-sm btn-gold" onclick="toggleAll('assignment')">All</button>
                    <button type="button" class="btn btn-sm btn-outline-secondary" onclick="clearAll('assignment')">Clear</button>
                </div>
            </div>
            <div class="card-body">
                <div class="d-flex flex-wrap gap-2" id="assignment-pills">
                    {% for a in all_assignments %}
                    <button type="button"
                            class="btn btn-sm rounded-pill filter-pill {% if a.pk in selected_assignment_ids %}active{% endif %}"
                            data-filter="assignment" data-id="{{ a.pk }}">
                        {{ a.title }}
                    </button>
                    {% empty %}
                    <span class="text-muted">No published assignments yet.</span>
                    {% endfor %}
                </div>
            </div>
        </div>
    </div>

    <!-- Student Selector -->
    <div class="col-md-6">
        <div class="card fade-in">
            <div class="card-header d-flex justify-content-between align-items-center">
                <span><i class="bi bi-people me-2"></i>Students</span>
                <div>
                    <button type="button" class="btn btn-sm btn-gold" onclick="toggleAll('student')">All ({{ all_students|length }})</button>
                    <button type="button" class="btn btn-sm btn-outline-secondary" onclick="clearAll('student')">Clear</button>
                </div>
            </div>
            <div class="card-body">
                <input type="text" class="form-control form-control-sm mb-2" placeholder="Search students..."
                       id="student-search" oninput="filterStudents(this.value)">
                <div class="d-flex flex-wrap gap-2" id="student-pills" style="max-height: 120px; overflow-y: auto;">
                    {% for s in all_students %}
                    <button type="button"
                            class="btn btn-sm rounded-pill filter-pill {% if s.pk in selected_student_ids %}active{% endif %}"
                            data-filter="student" data-id="{{ s.pk }}"
                            data-name="{{ s.get_full_name|lower }}">
                        {{ s.get_full_name|default:s.username }}
                    </button>
                    {% endfor %}
                </div>
            </div>
        </div>
    </div>
</div>

<!-- Analytics Content (swapped by HTMX) -->
<div id="analytics-content">
    {% include "assignments/instructor/analyze_content.html" %}
</div>

{% endblock %}

{% block extra_css %}
<style>
    .filter-pill {
        background: var(--warm-bg);
        color: var(--text-muted);
        border: 1px solid #ddd;
        transition: all 0.15s;
    }
    .filter-pill.active {
        background: var(--navy);
        color: #fff;
        border-color: var(--navy);
    }
    .filter-pill:hover {
        opacity: 0.85;
    }
    .stat-card {
        text-align: center;
        padding: 1rem;
    }
    .stat-card .stat-label {
        font-size: 0.7rem;
        text-transform: uppercase;
        letter-spacing: 0.5px;
        color: var(--text-muted);
    }
    .stat-card .stat-value {
        font-size: 1.6rem;
        font-weight: 700;
        color: var(--navy);
    }
    .accuracy-bar {
        height: 8px;
        border-radius: 4px;
        background: var(--warm-bg);
    }
    .accuracy-bar-fill {
        height: 100%;
        border-radius: 4px;
    }
    .collapse-header {
        cursor: pointer;
        user-select: none;
    }
    .collapse-header .collapse-icon {
        transition: transform 0.2s;
    }
    .collapse-header.collapsed .collapse-icon {
        transform: rotate(-90deg);
    }
</style>
{% endblock %}

{% block extra_js %}
<script src="https://cdn.jsdelivr.net/npm/chart.js@4"></script>
<script>
// --- Filter pill toggle + HTMX trigger ---
document.querySelectorAll('.filter-pill').forEach(btn => {
    btn.addEventListener('click', () => {
        btn.classList.toggle('active');
        refreshAnalytics();
    });
});

function toggleAll(type) {
    document.querySelectorAll(`.filter-pill[data-filter="${type}"]`).forEach(b => b.classList.add('active'));
    refreshAnalytics();
}

function clearAll(type) {
    document.querySelectorAll(`.filter-pill[data-filter="${type}"]`).forEach(b => b.classList.remove('active'));
    refreshAnalytics();
}

function filterStudents(query) {
    query = query.toLowerCase();
    document.querySelectorAll('#student-pills .filter-pill').forEach(btn => {
        btn.style.display = btn.dataset.name.includes(query) ? '' : 'none';
    });
}

function getSelectedIds(type) {
    return Array.from(document.querySelectorAll(`.filter-pill[data-filter="${type}"].active`))
        .map(b => b.dataset.id);
}

function refreshAnalytics() {
    const assignmentIds = getSelectedIds('assignment');
    const studentIds = getSelectedIds('student');
    const params = new FormData();
    assignmentIds.forEach(id => params.append('assignment_ids', id));
    studentIds.forEach(id => params.append('student_ids', id));

    htmx.ajax('POST', '{% url "instructor_analyze" %}', {
        target: '#analytics-content',
        swap: 'innerHTML',
        values: Object.fromEntries([
            ...assignmentIds.map(id => ['assignment_ids', id]),
            ...studentIds.map(id => ['student_ids', id]),
        ]),
    });
}

// Fix: htmx.ajax doesn't handle duplicate keys well via values.
// Override with raw FormData approach:
function refreshAnalytics() {
    const assignmentIds = getSelectedIds('assignment');
    const studentIds = getSelectedIds('student');

    const form = document.createElement('form');
    assignmentIds.forEach(id => {
        const input = document.createElement('input');
        input.name = 'assignment_ids';
        input.value = id;
        form.appendChild(input);
    });
    studentIds.forEach(id => {
        const input = document.createElement('input');
        input.name = 'student_ids';
        input.value = id;
        form.appendChild(input);
    });

    // Add CSRF
    const csrf = document.querySelector('[name=csrfmiddlewaretoken]');
    if (csrf) {
        const ci = document.createElement('input');
        ci.name = 'csrfmiddlewaretoken';
        ci.value = csrf.value;
        form.appendChild(ci);
    }

    form.style.display = 'none';
    form.setAttribute('hx-post', '{% url "instructor_analyze" %}');
    form.setAttribute('hx-target', '#analytics-content');
    form.setAttribute('hx-swap', 'innerHTML');
    document.body.appendChild(form);
    htmx.trigger(form, 'submit');
    setTimeout(() => form.remove(), 100);
}

// Update export links when filters change
function updateExportLinks() {
    const assignmentIds = getSelectedIds('assignment');
    const studentIds = getSelectedIds('student');
    const params = new URLSearchParams();
    assignmentIds.forEach(id => params.append('a', id));
    studentIds.forEach(id => params.append('s', id));
    const qs = params.toString();
    const rawLink = document.getElementById('export-raw-link');
    const breakdownLink = document.getElementById('export-breakdown-link');
    if (rawLink) rawLink.href = '{% url "export_raw_scores" %}?' + qs;
    if (breakdownLink) breakdownLink.href = '{% url "export_breakdown" %}?' + qs;
}

// Patch refreshAnalytics to also update export links
const _origRefresh = refreshAnalytics;
refreshAnalytics = function() {
    _origRefresh();
    updateExportLinks();
};

// Init export links on page load
document.addEventListener('DOMContentLoaded', updateExportLinks);
</script>
{% endblock %}
```

- [ ] **Step 2: Commit**

```bash
git add templates/assignments/instructor/analyze.html
git commit -m "feat(analytics): add main analyze page template with filters and JS"
```

---

### Task 6: Content Partial Template (HTMX Target)

**Files:**
- Create: `templates/assignments/instructor/analyze_content.html`

- [ ] **Step 1: Create the analytics content partial**

Create `templates/assignments/instructor/analyze_content.html`:

```html
{% load mathfilters %}
<!-- Summary Stats -->
<div class="row g-3 mb-3">
    <div class="col"><div class="card fade-in stat-card"><div class="stat-label">Mean</div><div class="stat-value">{{ analytics.summary.mean }}%</div></div></div>
    <div class="col"><div class="card fade-in stat-card"><div class="stat-label">Median</div><div class="stat-value">{{ analytics.summary.median }}%</div></div></div>
    <div class="col"><div class="card fade-in stat-card"><div class="stat-label">Std Dev</div><div class="stat-value">{{ analytics.summary.stdev }}</div></div></div>
    <div class="col"><div class="card fade-in stat-card"><div class="stat-label">Pass Rate</div><div class="stat-value" style="color: var(--success);">{{ analytics.summary.pass_rate }}%</div></div></div>
    <div class="col"><div class="card fade-in stat-card"><div class="stat-label">Avg Time</div><div class="stat-value">{{ analytics.summary.avg_time_min }}m</div></div></div>
</div>

<!-- Min/Max -->
<div class="row g-3 mb-3">
    <div class="col-md-6">
        <div class="card fade-in">
            <div class="card-body py-2 d-flex justify-content-between align-items-center">
                <span class="text-muted" style="font-size: 0.85rem;">Highest</span>
                <span class="fw-600" style="color: var(--success);">{{ analytics.summary.highest.score }}% — {{ analytics.summary.highest.name }}</span>
            </div>
        </div>
    </div>
    <div class="col-md-6">
        <div class="card fade-in">
            <div class="card-body py-2 d-flex justify-content-between align-items-center">
                <span class="text-muted" style="font-size: 0.85rem;">Lowest</span>
                <span class="fw-600" style="color: var(--danger, #c0392b);">{{ analytics.summary.lowest.score }}% — {{ analytics.summary.lowest.name }}</span>
            </div>
        </div>
    </div>
</div>

<!-- Score Distribution Chart -->
<div class="card fade-in mb-3">
    <div class="card-header">
        <i class="bi bi-bar-chart me-2" style="color: var(--gold);"></i>Score Distribution
        <small class="text-muted ms-2">{{ num_assignments }} assignment{{ num_assignments|pluralize }} · {{ num_students }} student{{ num_students|pluralize }}</small>
    </div>
    <div class="card-body">
        <canvas id="scoreDistChart" height="160"></canvas>
    </div>
</div>

<!-- Student Breakdown (collapsible) -->
<div class="card fade-in mb-3">
    <div class="card-header collapse-header d-flex justify-content-between align-items-center"
         data-bs-toggle="collapse" data-bs-target="#breakdownBody" aria-expanded="true">
        <div>
            <i class="bi bi-chevron-down collapse-icon me-1"></i>
            <span>Student Breakdown</span>
            <small class="text-muted ms-2">{{ analytics.student_breakdown|length }} student{{ analytics.student_breakdown|length|pluralize }}</small>
        </div>
        <div class="d-flex gap-2" onclick="event.stopPropagation();">
            <a id="export-raw-link" href="#" class="btn btn-sm btn-navy">
                <i class="bi bi-download me-1"></i>Export Raw Scores
            </a>
            <a id="export-breakdown-link" href="#" class="btn btn-sm btn-outline-secondary">
                <i class="bi bi-download me-1"></i>Export Breakdown
            </a>
        </div>
    </div>
    <div id="breakdownBody" class="collapse show">
        <div class="table-responsive">
            <table class="table table-hover mb-0">
                <thead>
                    <tr>
                        <th>#</th>
                        <th>Student</th>
                        <th class="text-center">Completed</th>
                        <th class="text-center">Avg Score</th>
                        <th class="text-center">Accuracy</th>
                        <th class="text-center">Avg Time</th>
                        <th style="width: 100px;"></th>
                    </tr>
                </thead>
                <tbody>
                {% for s in analytics.student_breakdown %}
                <tr>
                    <td class="text-muted">{{ forloop.counter }}</td>
                    <td class="fw-600">{{ s.name }}</td>
                    <td class="text-center">{{ s.completed }}/{{ s.total_assignments }}</td>
                    <td class="text-center fw-600 {% if s.avg_score >= 80 %}text-success{% elif s.avg_score >= 60 %}{% else %}text-danger{% endif %}">
                        {{ s.avg_score }}%
                    </td>
                    <td class="text-center">{{ s.accuracy }}%</td>
                    <td class="text-center">{{ s.avg_time_min }}m</td>
                    <td>
                        <div class="accuracy-bar">
                            <div class="accuracy-bar-fill {% if s.avg_score >= 80 %}bg-success{% elif s.avg_score >= 60 %}bg-warning{% else %}bg-danger{% endif %}"
                                 style="width: {{ s.avg_score }}%;"></div>
                        </div>
                    </td>
                </tr>
                {% empty %}
                <tr><td colspan="7" class="text-center text-muted py-3">No completed assignments for this selection.</td></tr>
                {% endfor %}
                </tbody>
            </table>
        </div>
    </div>
</div>

<!-- Weakest Sections -->
<div class="card fade-in mb-3">
    <div class="card-header"><i class="bi bi-exclamation-triangle me-2" style="color: var(--gold);"></i>Weakest Sections</div>
    <div class="table-responsive">
        <table class="table table-hover mb-0">
            <thead>
                <tr>
                    <th>Section</th>
                    <th>Topic</th>
                    <th class="text-center">Attempts</th>
                    <th class="text-center">Accuracy</th>
                    <th style="width: 100px;"></th>
                </tr>
            </thead>
            <tbody>
            {% for sec in analytics.weakest_sections %}
            <tr>
                <td class="fw-600">§ {{ sec.section_number }}</td>
                <td>{{ sec.title }}</td>
                <td class="text-center">{{ sec.attempts }}</td>
                <td class="text-center fw-600 {% if sec.accuracy < 50 %}text-danger{% elif sec.accuracy < 70 %}text-warning{% else %}text-success{% endif %}">
                    {{ sec.accuracy }}%
                </td>
                <td>
                    <div class="accuracy-bar">
                        <div class="accuracy-bar-fill {% if sec.accuracy < 50 %}bg-danger{% elif sec.accuracy < 70 %}bg-warning{% else %}bg-success{% endif %}"
                             style="width: {{ sec.accuracy }}%;"></div>
                    </div>
                </td>
            </tr>
            {% empty %}
            <tr><td colspan="5" class="text-center text-muted py-3">Not enough data yet (min. 5 attempts per section).</td></tr>
            {% endfor %}
            </tbody>
        </table>
    </div>
</div>

<!-- Most-Missed Questions -->
<div class="card fade-in mb-3">
    <div class="card-header"><i class="bi bi-question-circle me-2" style="color: var(--gold);"></i>Most-Missed Questions</div>
    <div class="table-responsive">
        <table class="table table-hover mb-0">
            <thead>
                <tr>
                    <th>UID</th>
                    <th>Question</th>
                    <th class="text-center">Times Asked</th>
                    <th class="text-center">Error Rate</th>
                    <th>Section</th>
                </tr>
            </thead>
            <tbody>
            {% for q in analytics.most_missed %}
            <tr>
                <td><code>{{ q.uid }}</code></td>
                <td>{{ q.text }}</td>
                <td class="text-center">{{ q.times_asked }}</td>
                <td class="text-center fw-600 {% if q.error_rate >= 70 %}text-danger{% elif q.error_rate >= 50 %}text-warning{% else %}{% endif %}">
                    {{ q.error_rate }}%
                </td>
                <td>§ {{ q.section }}</td>
            </tr>
            {% empty %}
            <tr><td colspan="5" class="text-center text-muted py-3">Not enough data yet (min. 3 attempts per question).</td></tr>
            {% endfor %}
            </tbody>
        </table>
    </div>
</div>

<!-- Chart.js for HTMX swaps: re-render chart each time content loads -->
<script>
(function() {
    const dist = {{ distribution_json|safe }};
    const canvas = document.getElementById('scoreDistChart');
    if (canvas && dist.length) {
        new Chart(canvas, {
            type: 'bar',
            data: {
                labels: ['0%','10%','20%','30%','40%','50%','60%','70%','80%','90%','100%'],
                datasets: [{
                    label: 'Students',
                    data: dist,
                    backgroundColor: dist.map((_, i) => i === 10 ? '#2d8a4e' : (dist[i] > 0 ? '#d4a843' : '#e9ecef')),
                    borderRadius: 4,
                }]
            },
            options: {
                scales: { y: { beginAtZero: true, ticks: { stepSize: 1 } } },
                plugins: { legend: { display: false } }
            }
        });
    }
    // Update export links after HTMX swap
    if (typeof updateExportLinks === 'function') updateExportLinks();
})();
</script>
```

- [ ] **Step 2: Check for `mathfilters` dependency**

The `{% load mathfilters %}` at the top requires `django-mathfilters`. Check if it's installed. If not, remove that line — we don't actually use any math template filters in this template (all computation is in the service). Remove the `{% load mathfilters %}` line from the template since it's not needed.

- [ ] **Step 3: Commit**

```bash
git add templates/assignments/instructor/analyze_content.html
git commit -m "feat(analytics): add HTMX content partial for analyze page"
```

---

### Task 7: CSS for btn-navy

**Files:**
- Modify: `static/css/style.css`

- [ ] **Step 1: Check if btn-navy already exists**

Run: `grep 'btn-navy' static/css/style.css`

If it doesn't exist, add this to `static/css/style.css` near the other button styles:

```css
.btn-navy {
    background: var(--navy);
    color: #fff;
    border: none;
}
.btn-navy:hover {
    background: #243044;
    color: #fff;
}
```

- [ ] **Step 2: Commit**

```bash
git add static/css/style.css
git commit -m "feat(analytics): add btn-navy CSS class for export buttons"
```

---

### Task 8: Integration Test

**Files:**
- Modify: `tests/test_analytics.py`

- [ ] **Step 1: Add view-level integration tests**

Append to `tests/test_analytics.py`:

```python
from django.test import Client


class AnalyzeViewTest(TestCase):
    def setUp(self):
        self.instructor = User.objects.create_user(
            username='prof', password='pass', role='INSTRUCTOR',
        )
        self.student = User.objects.create_user(
            username='alice', password='pass', role='STUDENT',
            first_name='Alice', last_name='Adams',
        )
        self.ch = Chapter.objects.create(number=4, title='TVM')
        self.sec = Section.objects.create(chapter=self.ch, number='4.1', title='Timeline', sort_order=1)
        self.q = Question.objects.create(
            section=self.sec, question_type='MC', text='Test Q',
            difficulty=1, skill='Conceptual', question_number=1, global_number=1,
        )
        MCChoice.objects.create(question=self.q, letter='A', text='Right', is_correct=True)
        self.a1 = Assignment.objects.create(
            title='HW1', created_by=self.instructor, num_questions=1,
            mode='ASSIGNMENT', is_published=True,
        )
        self.sa = StudentAssignment.objects.create(
            student=self.student, assignment=self.a1,
            status='COMPLETED', score=1, max_score=1, total_time_seconds=120,
        )
        AssignedQuestion.objects.create(student_assignment=self.sa, question=self.q, position=0)
        StudentAnswer.objects.create(
            student_assignment=self.sa, question=self.q, is_correct=True,
        )
        self.client = Client()

    def test_analyze_page_loads(self):
        self.client.login(username='prof', password='pass')
        resp = self.client.get('/assignments/analyze/')
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Analyze')
        self.assertContains(resp, 'HW1')

    def test_analyze_htmx_post(self):
        self.client.login(username='prof', password='pass')
        resp = self.client.post(
            '/assignments/analyze/',
            {'assignment_ids': [self.a1.pk], 'student_ids': [self.student.pk]},
            HTTP_HX_REQUEST='true',
        )
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, '100')  # 1/1 = 100%

    def test_analyze_student_forbidden(self):
        self.client.login(username='alice', password='pass')
        resp = self.client.get('/assignments/analyze/')
        self.assertEqual(resp.status_code, 302)

    def test_export_raw_csv(self):
        self.client.login(username='prof', password='pass')
        resp = self.client.get(f'/assignments/analyze/export-raw/?a={self.a1.pk}&s={self.student.pk}')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp['Content-Type'], 'text/csv')
        content = resp.content.decode()
        self.assertIn('Alice Adams', content)
        self.assertIn('1/1', content)

    def test_export_breakdown_csv(self):
        self.client.login(username='prof', password='pass')
        resp = self.client.get(f'/assignments/analyze/export-breakdown/?a={self.a1.pk}&s={self.student.pk}')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp['Content-Type'], 'text/csv')
        content = resp.content.decode()
        self.assertIn('Alice Adams', content)
```

- [ ] **Step 2: Run all tests**

Run: `python3 manage.py test -v2`

Expected: All tests pass (existing 32 + new 12 = 44 total).

- [ ] **Step 3: Commit**

```bash
git add tests/test_analytics.py
git commit -m "test(analytics): add integration tests for analyze views and CSV exports"
```

---

### Task 9: Manual Smoke Test

- [ ] **Step 1: Start the dev server and verify full page**

Run: `python3 manage.py runserver 0.0.0.0:8000`

Log in as instructor. Navigate to Analyze. Verify:
- All published assignments appear as pills (all selected by default)
- All students appear as pills (all selected by default)
- Summary stat cards show computed values
- Score distribution chart renders
- Student breakdown table is populated and collapsible
- Weakest sections and most-missed questions tables render
- Clicking a pill to deselect it triggers HTMX reload of the content area
- Student search box filters the student pills
- "Export Raw Scores" downloads a CSV
- "Export Breakdown" downloads a CSV

- [ ] **Step 2: Fix any issues found during smoke test**

Address any rendering or data issues found.

- [ ] **Step 3: Final commit if any fixes**

```bash
git add -A
git commit -m "fix(analytics): smoke test fixes"
```
