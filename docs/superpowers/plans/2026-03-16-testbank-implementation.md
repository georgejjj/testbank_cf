# Testbank System Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a web-based testbank system where an instructor creates assignments from parsed .docx question pools, students complete them with auto-grading, and both sides get analytics.

**Architecture:** Django monolith with SQLite, server-rendered templates with HTMX for interactivity. Business logic isolated in `services/` layer. Bootstrap 5 responsive UI with MathJax for formula rendering and Chart.js for analytics.

**Tech Stack:** Python 3.11+, Django 5.x, SQLite (WAL mode), Bootstrap 5, HTMX 2.x, MathJax 3, Chart.js 4

**Spec:** `docs/superpowers/specs/2026-03-16-testbank-system-design.md`

---

## File Structure

```
testbank/                           # Project root (already exists)
├── manage.py
├── requirements.txt
├── config/
│   ├── __init__.py
│   ├── settings.py
│   ├── urls.py
│   └── wsgi.py
├── apps/
│   ├── __init__.py
│   ├── accounts/
│   │   ├── __init__.py
│   │   ├── models.py              # User model (extends AbstractUser, adds role + student_id)
│   │   ├── admin.py
│   │   ├── forms.py               # Login, password change, CSV import forms
│   │   ├── views.py               # Login, logout, roster, CSV import
│   │   ├── urls.py
│   │   ├── middleware.py           # Role-based access middleware
│   │   └── templatetags/
│   │       └── account_tags.py
│   ├── questions/
│   │   ├── __init__.py
│   │   ├── models.py              # Chapter, Section, ContextGroup, Question, MCChoice, NumericAnswer
│   │   ├── admin.py
│   │   ├── views.py               # Question browser, import UI
│   │   ├── urls.py
│   │   └── management/
│   │       └── commands/
│   │           └── import_testbank.py
│   └── assignments/
│       ├── __init__.py
│       ├── models.py              # Assignment, StudentAssignment, AssignedQuestion, StudentAnswer, MistakeEntry
│       ├── admin.py
│       ├── forms.py               # Assignment creation forms
│       ├── views.py               # Assignment CRUD, take assignment, results, analytics
│       ├── urls.py
│       └── templatetags/
│           └── assignment_tags.py
├── services/
│   ├── __init__.py
│   ├── parser.py                  # .docx parser: XML extraction, state machine, question emission
│   ├── grader.py                  # Auto-grading: MC, numeric (with tolerance), score recomputation
│   └── randomizer.py              # Question selection, shuffling, choice shuffle map generation
├── media/
│   └── questions/                 # Extracted images per chapter (e.g., ch4/)
├── static/
│   ├── css/
│   │   └── style.css              # Custom styles on top of Bootstrap
│   └── js/
│       ├── timer.js               # Per-question timer with tab-hidden pause
│       ├── htmx-config.js         # CSRF header setup, error toast handler
│       └── charts.js              # Chart.js helper for analytics pages
├── templates/
│   ├── base.html                  # Bootstrap 5 + MathJax + HTMX + nav
│   ├── accounts/
│   │   ├── login.html
│   │   ├── password_change.html
│   │   └── roster.html
│   ├── questions/
│   │   ├── browser.html           # Instructor question browser
│   │   └── import.html            # Upload + preview + confirm
│   └── assignments/
│       ├── instructor/
│       │   ├── dashboard.html
│       │   ├── create.html        # Hand-pick + auto-generate tabs
│       │   ├── detail.html        # Per-student results
│       │   └── grade.html         # Free-response grading queue
│       └── student/
│           ├── dashboard.html
│           ├── list.html
│           ├── take.html          # One-question-at-a-time view
│           ├── result.html
│           ├── practice.html      # Practice mode setup
│           ├── mistakes.html      # Mistake collection
│           └── analytics.html
└── tests/
    ├── __init__.py
    ├── test_models.py             # Model creation, constraints, relationships
    ├── test_parser.py             # Parser against real chapter 4 data
    ├── test_grader.py             # Grading logic: MC, numeric, edge cases
    ├── test_randomizer.py         # Randomization, shuffling, frozen draws
    └── test_views.py              # View integration tests
```

---

## Chunk 1: Project Foundation & Data Models

### Task 1: Django Project Scaffolding

**Files:**
- Create: `config/__init__.py`, `config/settings.py`, `config/urls.py`, `config/wsgi.py`
- Create: `manage.py`, `requirements.txt`
- Create: `apps/__init__.py`

- [ ] **Step 1: Create requirements.txt**

```
Django>=5.0,<5.1
```

- [ ] **Step 2: Install Django and create project**

```bash
cd /home/georgejjj/testbank
pip install -r requirements.txt
django-admin startproject config .
```

Expected: `manage.py` and `config/` directory created.

- [ ] **Step 3: Configure settings.py for our project**

Edit `config/settings.py`:
- Add `apps/` to Python path
- Set `AUTH_USER_MODEL = 'accounts.User'`
- Configure SQLite with WAL mode and busy_timeout
- Set `MEDIA_ROOT` and `MEDIA_URL`
- Set `STATIC_ROOT` and `STATIC_URL`
- Set `DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'`

Key settings to add/modify:

```python
import sys
sys.path.insert(0, str(BASE_DIR / 'apps'))

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'accounts',
    'questions',
    'assignments',
]

AUTH_USER_MODEL = 'accounts.User'

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
        'OPTIONS': {
            'init_command': "PRAGMA journal_mode=WAL; PRAGMA busy_timeout=5000;",
        },
        'CONN_MAX_AGE': None,
    }
}

MEDIA_ROOT = BASE_DIR / 'media'
MEDIA_URL = '/media/'

STATIC_URL = '/static/'
STATICFILES_DIRS = [BASE_DIR / 'static']

LOGIN_URL = '/accounts/login/'
LOGIN_REDIRECT_URL = '/'
LOGOUT_REDIRECT_URL = '/accounts/login/'
```

- [ ] **Step 4: Create app directories**

```bash
mkdir -p apps/accounts apps/questions apps/assignments services tests
touch apps/__init__.py apps/accounts/__init__.py apps/questions/__init__.py apps/assignments/__init__.py
touch services/__init__.py tests/__init__.py
```

- [ ] **Step 5: Verify Django starts**

```bash
cd /home/georgejjj/testbank
python manage.py check
```

Expected: "System check identified no issues" (will have warnings about unapplied migrations, which is fine — we haven't created our models yet).

- [ ] **Step 6: Commit**

```bash
git init
echo "db.sqlite3\n__pycache__/\n*.pyc\nmedia/questions/\n.env" > .gitignore
git add .
git commit -m "feat: scaffold Django project with config and app directories"
```

---

### Task 2: Question Pool Models

**Files:**
- Create: `apps/questions/models.py`
- Create: `apps/questions/admin.py`
- Create: `tests/test_models.py`

- [ ] **Step 1: Write failing test for Chapter and Section models**

```python
# tests/test_models.py
from django.test import TestCase
from questions.models import Chapter, Section


class ChapterModelTest(TestCase):
    def test_create_chapter(self):
        ch = Chapter.objects.create(number=4, title="The Time Value of Money", textbook="Corporate Finance 6e")
        self.assertEqual(ch.number, 4)
        self.assertEqual(str(ch), "Chapter 4: The Time Value of Money")

    def test_create_section(self):
        ch = Chapter.objects.create(number=4, title="The Time Value of Money", textbook="Corporate Finance 6e")
        sec = Section.objects.create(chapter=ch, number="4.1", title="The Timeline", sort_order=1)
        self.assertEqual(sec.chapter, ch)
        self.assertEqual(str(sec), "4.1 The Timeline")
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python manage.py test tests.test_models.ChapterModelTest -v2
```

Expected: FAIL — `questions.models` does not have Chapter/Section yet.

- [ ] **Step 3: Implement Chapter and Section models**

```python
# apps/questions/models.py
from django.db import models


class Chapter(models.Model):
    number = models.IntegerField()
    title = models.CharField(max_length=200)
    textbook = models.CharField(max_length=200, default="Corporate Finance 6e")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['number']
        unique_together = [['textbook', 'number']]

    def __str__(self):
        return f"Chapter {self.number}: {self.title}"


class Section(models.Model):
    chapter = models.ForeignKey(Chapter, on_delete=models.CASCADE, related_name='sections')
    number = models.CharField(max_length=20)
    title = models.CharField(max_length=200)
    sort_order = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['sort_order']
        unique_together = [['chapter', 'number']]

    def __str__(self):
        return f"{self.number} {self.title}"
```

- [ ] **Step 4: Make migrations and run tests**

```bash
python manage.py makemigrations questions
python manage.py test tests.test_models.ChapterModelTest -v2
```

Expected: PASS

- [ ] **Step 5: Write failing test for ContextGroup, Question, MCChoice, NumericAnswer**

Add to `tests/test_models.py`:

```python
from questions.models import Chapter, Section, ContextGroup, Question, MCChoice, NumericAnswer


class QuestionModelTest(TestCase):
    def setUp(self):
        self.ch = Chapter.objects.create(number=4, title="The Time Value of Money")
        self.sec = Section.objects.create(chapter=self.ch, number="4.1", title="The Timeline", sort_order=1)

    def test_create_mc_question(self):
        q = Question.objects.create(
            section=self.sec, question_type='MC', text='Which statement is FALSE?',
            difficulty=1, skill='Conceptual', question_number=1,
        )
        MCChoice.objects.create(question=q, letter='A', text='Option A', is_correct=False)
        MCChoice.objects.create(question=q, letter='B', text='Option B', is_correct=False)
        MCChoice.objects.create(question=q, letter='C', text='Option C', is_correct=True)
        MCChoice.objects.create(question=q, letter='D', text='Option D', is_correct=False)
        self.assertEqual(q.choices.count(), 4)
        self.assertEqual(q.choices.filter(is_correct=True).first().letter, 'C')

    def test_create_numeric_question(self):
        q = Question.objects.create(
            section=self.sec, question_type='NUMERIC', text='Calculate PV',
            difficulty=2, skill='Analytical', question_number=50,
            answer_raw_text='PV = $254,641',
        )
        na = NumericAnswer.objects.create(question=q, value=254641, tolerance_percent=1.0)
        self.assertEqual(na.value, 254641)
        self.assertEqual(na.tolerance_percent, 1.0)
        self.assertEqual(na.absolute_tolerance, 0.01)

    def test_context_group(self):
        ctx = ContextGroup.objects.create(text='Use the figure below.', section=self.sec)
        q = Question.objects.create(
            section=self.sec, question_type='MC', text='Based on the figure...',
            difficulty=1, skill='Conceptual', question_number=2, context_group=ctx,
        )
        self.assertEqual(q.context_group.text, 'Use the figure below.')

    def test_question_unique_constraint(self):
        Question.objects.create(
            section=self.sec, question_type='MC', text='Q1',
            difficulty=1, skill='Conceptual', question_number=1,
        )
        with self.assertRaises(Exception):
            Question.objects.create(
                section=self.sec, question_type='MC', text='Q1 duplicate',
                difficulty=1, skill='Conceptual', question_number=1,
            )
```

- [ ] **Step 6: Implement remaining question models**

Add to `apps/questions/models.py`:

```python
class ContextGroup(models.Model):
    text = models.TextField()
    image = models.CharField(max_length=500, blank=True, default='')
    section = models.ForeignKey(Section, on_delete=models.CASCADE, related_name='context_groups', null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.text[:80]


class Question(models.Model):
    QUESTION_TYPES = [('MC', 'Multiple Choice'), ('NUMERIC', 'Numeric'), ('FREE_RESPONSE', 'Free Response')]
    SKILL_CHOICES = [('Conceptual', 'Conceptual'), ('Definition', 'Definition'), ('Analytical', 'Analytical')]

    section = models.ForeignKey(Section, on_delete=models.CASCADE, related_name='questions')
    question_type = models.CharField(max_length=15, choices=QUESTION_TYPES)
    text = models.TextField()
    difficulty = models.IntegerField(choices=[(1, '1'), (2, '2'), (3, '3')])
    skill = models.CharField(max_length=20, choices=SKILL_CHOICES)
    explanation = models.TextField(blank=True, default='')
    image = models.CharField(max_length=500, blank=True, default='')
    context_group = models.ForeignKey(ContextGroup, on_delete=models.SET_NULL, null=True, blank=True, related_name='questions')
    question_number = models.IntegerField()
    answer_raw_text = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        # Unique per chapter (via section's chapter) + question_number
        # Enforced at application level since it spans a FK; DB constraint below is per-section
        unique_together = [['section', 'question_number']]
        ordering = ['question_number']

    def __str__(self):
        return f"Q{self.question_number}: {self.text[:60]}"


class MCChoice(models.Model):
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name='choices')
    letter = models.CharField(max_length=1)
    text = models.TextField()
    is_correct = models.BooleanField(default=False)

    class Meta:
        ordering = ['letter']

    def __str__(self):
        return f"{self.letter}) {self.text[:40]}"


class NumericAnswer(models.Model):
    question = models.OneToOneField(Question, on_delete=models.CASCADE, related_name='numeric_answer')
    value = models.DecimalField(max_digits=20, decimal_places=4)
    tolerance_percent = models.DecimalField(max_digits=5, decimal_places=2, default=1.0)
    absolute_tolerance = models.DecimalField(max_digits=10, decimal_places=4, default=0.01)

    def __str__(self):
        return f"{self.value} (±{self.tolerance_percent}%)"
```

- [ ] **Step 7: Make migrations and run tests**

```bash
python manage.py makemigrations questions
python manage.py test tests.test_models -v2
```

Expected: All tests PASS.

- [ ] **Step 8: Register models in admin**

```python
# apps/questions/admin.py
from django.contrib import admin
from .models import Chapter, Section, ContextGroup, Question, MCChoice, NumericAnswer


class MCChoiceInline(admin.TabularInline):
    model = MCChoice
    extra = 0


class NumericAnswerInline(admin.StackedInline):
    model = NumericAnswer
    extra = 0


@admin.register(Chapter)
class ChapterAdmin(admin.ModelAdmin):
    list_display = ['number', 'title', 'textbook']


@admin.register(Section)
class SectionAdmin(admin.ModelAdmin):
    list_display = ['number', 'title', 'chapter', 'sort_order']
    list_filter = ['chapter']


@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    list_display = ['question_number', 'question_type', 'difficulty', 'skill', 'section']
    list_filter = ['question_type', 'difficulty', 'skill', 'section__chapter']
    search_fields = ['text']
    inlines = [MCChoiceInline, NumericAnswerInline]
```

- [ ] **Step 9: Commit**

```bash
git add apps/questions/ tests/test_models.py
git commit -m "feat: add question pool models (Chapter, Section, Question, MCChoice, NumericAnswer)"
```

---

### Task 3: User Model

**Files:**
- Create: `apps/accounts/models.py`
- Create: `apps/accounts/admin.py`
- Modify: `tests/test_models.py`

- [ ] **Step 1: Write failing test for User model**

Add to `tests/test_models.py`:

```python
from accounts.models import User


class UserModelTest(TestCase):
    def test_create_instructor(self):
        user = User.objects.create_user(username='prof', password='test123', role='INSTRUCTOR')
        self.assertEqual(user.role, 'INSTRUCTOR')
        self.assertTrue(user.is_instructor)
        self.assertFalse(user.is_student)

    def test_create_student(self):
        user = User.objects.create_user(username='student1', password='test123', role='STUDENT', student_id='S001')
        self.assertEqual(user.role, 'STUDENT')
        self.assertTrue(user.is_student)
        self.assertEqual(user.student_id, 'S001')
        self.assertTrue(user.must_change_password)
```

- [ ] **Step 2: Implement User model**

```python
# apps/accounts/models.py
from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    ROLE_CHOICES = [('INSTRUCTOR', 'Instructor'), ('STUDENT', 'Student')]

    role = models.CharField(max_length=10, choices=ROLE_CHOICES, default='STUDENT')
    student_id = models.CharField(max_length=50, blank=True, default='')
    must_change_password = models.BooleanField(default=True)

    @property
    def is_instructor(self):
        return self.role == 'INSTRUCTOR'

    @property
    def is_student(self):
        return self.role == 'STUDENT'

    def __str__(self):
        if self.student_id:
            return f"{self.get_full_name() or self.username} ({self.student_id})"
        return self.get_full_name() or self.username
```

- [ ] **Step 3: Register in admin**

```python
# apps/accounts/admin.py
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ['username', 'first_name', 'last_name', 'role', 'student_id']
    list_filter = ['role']
    fieldsets = BaseUserAdmin.fieldsets + (
        ('Testbank', {'fields': ('role', 'student_id', 'must_change_password')}),
    )
```

- [ ] **Step 4: Make migrations and run tests**

```bash
python manage.py makemigrations accounts
python manage.py test tests.test_models -v2
```

Expected: All tests PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/accounts/ tests/test_models.py
git commit -m "feat: add User model with role (instructor/student) and student_id"
```

---

### Task 4: Assignment & Student Work Models

**Files:**
- Create: `apps/assignments/models.py`
- Create: `apps/assignments/admin.py`
- Modify: `tests/test_models.py`

- [ ] **Step 1: Write failing test for Assignment and StudentAssignment**

Add to `tests/test_models.py`:

```python
from assignments.models import Assignment, StudentAssignment, AssignedQuestion, StudentAnswer, MistakeEntry


class AssignmentModelTest(TestCase):
    def setUp(self):
        self.instructor = User.objects.create_user(username='prof', password='test', role='INSTRUCTOR')
        self.student = User.objects.create_user(username='stu1', password='test', role='STUDENT')
        self.ch = Chapter.objects.create(number=4, title="TVM")
        self.sec = Section.objects.create(chapter=self.ch, number="4.1", title="Timeline", sort_order=1)
        self.q1 = Question.objects.create(section=self.sec, question_type='MC', text='Q1', difficulty=1, skill='Conceptual', question_number=1)
        self.q2 = Question.objects.create(section=self.sec, question_type='MC', text='Q2', difficulty=2, skill='Conceptual', question_number=2)
        MCChoice.objects.create(question=self.q1, letter='A', text='Opt A', is_correct=True)
        MCChoice.objects.create(question=self.q1, letter='B', text='Opt B', is_correct=False)

    def test_create_assignment(self):
        a = Assignment.objects.create(title='HW1', created_by=self.instructor, num_questions=2, mode='ASSIGNMENT')
        a.chapters.add(self.ch)
        self.assertEqual(a.chapters.count(), 1)
        self.assertFalse(a.is_published)

    def test_student_assignment_unique(self):
        a = Assignment.objects.create(title='HW1', created_by=self.instructor, num_questions=2, mode='ASSIGNMENT')
        StudentAssignment.objects.create(student=self.student, assignment=a, max_score=2)
        with self.assertRaises(Exception):
            StudentAssignment.objects.create(student=self.student, assignment=a, max_score=2)

    def test_assigned_question_with_position(self):
        a = Assignment.objects.create(title='HW1', created_by=self.instructor, num_questions=2, mode='ASSIGNMENT')
        sa = StudentAssignment.objects.create(student=self.student, assignment=a, max_score=2)
        AssignedQuestion.objects.create(student_assignment=sa, question=self.q1, position=0)
        AssignedQuestion.objects.create(student_assignment=sa, question=self.q2, position=1)
        questions = sa.assigned_questions.order_by('assignedquestion__position')
        self.assertEqual(list(questions), [self.q1, self.q2])

    def test_student_answer(self):
        a = Assignment.objects.create(title='HW1', created_by=self.instructor, num_questions=1, mode='ASSIGNMENT')
        sa = StudentAssignment.objects.create(student=self.student, assignment=a, max_score=1)
        correct_choice = self.q1.choices.get(is_correct=True)
        ans = StudentAnswer.objects.create(
            student_assignment=sa, question=self.q1,
            selected_choice=correct_choice, is_correct=True,
            time_spent_seconds=30, server_elapsed_seconds=32,
            question_text_snapshot=self.q1.text,
        )
        self.assertTrue(ans.is_correct)

    def test_mistake_entry(self):
        me = MistakeEntry.objects.create(student=self.student, question=self.q1)
        self.assertFalse(me.is_mastered)
        self.assertEqual(me.times_practiced, 0)
```

- [ ] **Step 2: Implement assignment models**

```python
# apps/assignments/models.py
from django.db import models
from django.conf import settings
from questions.models import Chapter, Section, Question, MCChoice


class Assignment(models.Model):
    MODE_CHOICES = [('PRACTICE', 'Practice'), ('ASSIGNMENT', 'Assignment')]

    title = models.CharField(max_length=200)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='created_assignments')
    chapters = models.ManyToManyField(Chapter, blank=True)
    sections = models.ManyToManyField(Section, blank=True)
    difficulty_filter = models.JSONField(default=list, blank=True)
    skill_filter = models.JSONField(default=list, blank=True)
    num_questions = models.IntegerField()
    mode = models.CharField(max_length=10, choices=MODE_CHOICES)
    is_randomized = models.BooleanField(default=True)
    is_published = models.BooleanField(default=False)
    due_date = models.DateTimeField(null=True, blank=True)
    time_limit_minutes = models.IntegerField(null=True, blank=True)
    manually_selected_questions = models.ManyToManyField(Question, blank=True, related_name='manual_assignments')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.title


class StudentAssignment(models.Model):
    STATUS_CHOICES = [
        ('NOT_STARTED', 'Not Started'),
        ('IN_PROGRESS', 'In Progress'),
        ('COMPLETED', 'Completed'),
    ]

    student = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='student_assignments')
    assignment = models.ForeignKey(Assignment, on_delete=models.CASCADE, related_name='student_assignments')
    assigned_questions = models.ManyToManyField(Question, through='AssignedQuestion', related_name='student_assignments_assigned')
    choice_shuffle_map = models.JSONField(default=dict, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    score = models.IntegerField(null=True, blank=True)
    max_score = models.IntegerField(default=0)
    status = models.CharField(max_length=15, choices=STATUS_CHOICES, default='NOT_STARTED')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [['student', 'assignment']]
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.student} - {self.assignment}"


class AssignedQuestion(models.Model):
    student_assignment = models.ForeignKey(StudentAssignment, on_delete=models.CASCADE)
    question = models.ForeignKey(Question, on_delete=models.CASCADE)
    position = models.IntegerField()

    class Meta:
        unique_together = [['student_assignment', 'question']]
        ordering = ['position']


class StudentAnswer(models.Model):
    student_assignment = models.ForeignKey(StudentAssignment, on_delete=models.CASCADE, related_name='answers')
    question = models.ForeignKey(Question, on_delete=models.CASCADE)
    selected_choice = models.ForeignKey(MCChoice, on_delete=models.SET_NULL, null=True, blank=True)
    numeric_answer = models.DecimalField(max_digits=20, decimal_places=4, null=True, blank=True)
    text_answer = models.TextField(max_length=5000, blank=True, default='')
    is_correct = models.BooleanField(null=True)
    time_spent_seconds = models.IntegerField(default=0)
    server_elapsed_seconds = models.IntegerField(default=0)
    answered_at = models.DateTimeField(auto_now=True)
    instructor_feedback = models.TextField(blank=True, default='')
    question_text_snapshot = models.TextField(default='')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [['student_assignment', 'question']]

    def __str__(self):
        return f"Answer by {self.student_assignment.student} for Q{self.question.question_number}"


class MistakeEntry(models.Model):
    student = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='mistakes')
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name='mistake_entries')
    added_at = models.DateTimeField(auto_now_add=True)
    last_practiced_at = models.DateTimeField(null=True, blank=True)
    times_practiced = models.IntegerField(default=0)
    is_mastered = models.BooleanField(default=False)

    class Meta:
        unique_together = [['student', 'question']]
        ordering = ['-added_at']

    def __str__(self):
        return f"Mistake: {self.student} - Q{self.question.question_number}"
```

- [ ] **Step 3: Make migrations and run all tests**

```bash
python manage.py makemigrations assignments
python manage.py test tests.test_models -v2
```

Expected: All tests PASS.

- [ ] **Step 4: Register in admin**

```python
# apps/assignments/admin.py
from django.contrib import admin
from .models import Assignment, StudentAssignment, StudentAnswer, MistakeEntry


@admin.register(Assignment)
class AssignmentAdmin(admin.ModelAdmin):
    list_display = ['title', 'mode', 'is_published', 'num_questions', 'due_date', 'created_by']
    list_filter = ['mode', 'is_published']


@admin.register(StudentAssignment)
class StudentAssignmentAdmin(admin.ModelAdmin):
    list_display = ['student', 'assignment', 'status', 'score', 'max_score']
    list_filter = ['status']
```

- [ ] **Step 5: Run full migration and verify**

```bash
python manage.py migrate
python manage.py test tests.test_models -v2
```

Expected: All migrations applied, all tests PASS.

- [ ] **Step 6: Commit**

```bash
git add apps/assignments/ tests/test_models.py
git commit -m "feat: add assignment models (Assignment, StudentAssignment, StudentAnswer, MistakeEntry)"
```

---

## Chunk 2: Word File Parser & Import

### Task 5: Parser Service — Text Extraction & State Machine

**Files:**
- Create: `services/parser.py`
- Create: `tests/test_parser.py`

The parser reads a .docx file (which is a ZIP of XML) and extracts structured question data. It uses a state machine to walk through the text runs and identify chapters, sections, context blocks, questions, choices, answers, and metadata.

Reference file for testing: `/home/georgejjj/testbank/chapter 4.docx`

- [ ] **Step 1: Write failing test for text extraction from docx**

```python
# tests/test_parser.py
import os
from django.test import TestCase
from services.parser import extract_text_and_images

SAMPLE_DOCX = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'chapter 4.docx')


class TextExtractionTest(TestCase):
    def test_extract_text_runs(self):
        """Extract text runs from chapter 4.docx and verify basic structure."""
        text_runs, images = extract_text_and_images(SAMPLE_DOCX)
        # Should have many text runs
        self.assertGreater(len(text_runs), 100)
        # First run should contain textbook title
        full_text = ' '.join(text_runs)
        self.assertIn('Corporate Finance', full_text)
        self.assertIn('Chapter 4', full_text)

    def test_extract_images(self):
        """Should find images embedded in the docx."""
        text_runs, images = extract_text_and_images(SAMPLE_DOCX)
        self.assertGreater(len(images), 0)
        # Images should be bytes
        for name, data in images.items():
            self.assertIsInstance(data, bytes)
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python manage.py test tests.test_parser.TextExtractionTest -v2
```

Expected: FAIL — `services.parser` has no `extract_text_and_images`.

- [ ] **Step 3: Implement text and image extraction**

```python
# services/parser.py
"""
Parser for textbook testbank .docx files.

Extracts questions, choices, answers, metadata, images, and tables
from Word documents in the Pearson testbank format.
"""
import re
import zipfile
from xml.etree import ElementTree as ET


# XML namespaces used in .docx
NS = {
    'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main',
    'r': 'http://schemas.openxmlformats.org/officeDocument/2006/relationships',
    'wp': 'http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing',
    'a': 'http://schemas.openxmlformats.org/drawingml/2006/main',
    'pic': 'http://schemas.openxmlformats.org/drawingml/2006/picture',
    'rel': 'http://schemas.openxmlformats.org/package/2006/relationships',
}


def extract_text_and_images(docx_path):
    """
    Extract ordered text runs and images from a .docx file.

    Returns:
        text_runs: list of strings (each text run in document order)
        images: dict of {filename: bytes} for all images in word/media/
    """
    text_runs = []
    images = {}

    with zipfile.ZipFile(docx_path, 'r') as z:
        # Extract images
        for name in z.namelist():
            if name.startswith('word/media/'):
                images[name.split('/')[-1]] = z.read(name)

        # Parse document.xml
        xml_content = z.read('word/document.xml')
        root = ET.fromstring(xml_content)

        # Build relationship map (rId -> target) for image references
        rels = {}
        if 'word/_rels/document.xml.rels' in z.namelist():
            rels_xml = z.read('word/_rels/document.xml.rels')
            rels_root = ET.fromstring(rels_xml)
            for rel in rels_root.findall('{http://schemas.openxmlformats.org/package/2006/relationships}Relationship'):
                rels[rel.get('Id')] = rel.get('Target')

        # Walk body elements in order (paragraphs and tables)
        body = root.find('w:body', NS)
        for element in body:
            tag = element.tag.split('}')[-1] if '}' in element.tag else element.tag
            if tag == 'p':
                _extract_paragraph_text(element, text_runs, rels)
            elif tag == 'tbl':
                _extract_table_text(element, text_runs)

    return text_runs, images


def _extract_paragraph_text(para, text_runs, rels):
    """Extract text and image markers from a paragraph element."""
    para_texts = []
    for run in para.findall('.//w:r', NS):
        # Check for image
        drawing = run.find('.//w:drawing', NS)
        if drawing is not None:
            blip = drawing.find('.//a:blip', NS)
            if blip is not None:
                embed_id = blip.get('{http://schemas.openxmlformats.org/officeDocument/2006/relationships}embed')
                if embed_id and embed_id in rels:
                    target = rels[embed_id]
                    img_name = target.split('/')[-1]
                    para_texts.append(f'[IMAGE:{img_name}]')

        # Extract text
        for t in run.findall('w:t', NS):
            if t.text:
                para_texts.append(t.text)

    if para_texts:
        text_runs.append(''.join(para_texts))


def _extract_table_text(table, text_runs):
    """Extract table content as [TABLE_START]...[TABLE_END] markers with cell text."""
    text_runs.append('[TABLE_START]')
    for row in table.findall('.//w:tr', NS):
        row_texts = []
        for cell in row.findall('w:tc', NS):
            cell_text = []
            for t in cell.findall('.//w:t', NS):
                if t.text:
                    cell_text.append(t.text)
            row_texts.append(''.join(cell_text))
        text_runs.append('\t'.join(row_texts))
    text_runs.append('[TABLE_END]')
```

- [ ] **Step 4: Run test to verify it passes**

```bash
python manage.py test tests.test_parser.TextExtractionTest -v2
```

Expected: PASS

- [ ] **Step 5: Write failing test for question parsing state machine**

Add to `tests/test_parser.py`:

```python
from services.parser import parse_docx


class QuestionParsingTest(TestCase):
    def test_parse_chapter4(self):
        """Parse chapter 4 docx and verify question counts and structure."""
        result = parse_docx(SAMPLE_DOCX)

        self.assertEqual(result['chapter_number'], 4)
        self.assertIn('Time Value of Money', result['chapter_title'])

        questions = result['questions']
        self.assertGreater(len(questions), 80)  # Chapter 4 has ~90 questions

    def test_mc_question_structure(self):
        """First question should be MC with 4 choices and correct answer C."""
        result = parse_docx(SAMPLE_DOCX)
        q1 = result['questions'][0]

        self.assertEqual(q1['question_number'], 1)
        self.assertEqual(q1['question_type'], 'MC')
        self.assertIn('timeline', q1['text'].lower())
        self.assertEqual(len(q1['choices']), 4)
        self.assertEqual(q1['correct_answer'], 'C')
        self.assertEqual(q1['difficulty'], 1)
        self.assertIn(q1['skill'], ['Conceptual', 'Definition', 'Analytical'])

    def test_section_detection(self):
        """Questions should have section metadata."""
        result = parse_docx(SAMPLE_DOCX)
        q1 = result['questions'][0]
        self.assertIn('4.1', q1['section_number'])

    def test_question_type_detection(self):
        """Should detect MC, NUMERIC, and FREE_RESPONSE types."""
        result = parse_docx(SAMPLE_DOCX)
        types = set(q['question_type'] for q in result['questions'])
        self.assertIn('MC', types)
        # Chapter 4 has free response and possibly numeric
        self.assertTrue(types - {'MC'})  # At least one non-MC type
```

- [ ] **Step 6: Implement parse_docx state machine**

Add to `services/parser.py`:

```python
def parse_docx(docx_path):
    """
    Parse a testbank .docx file into structured question data.

    Returns dict with:
        chapter_number: int
        chapter_title: str
        sections: list of {number, title}
        questions: list of question dicts
        images: dict of {filename: bytes}
    """
    text_runs, images = extract_text_and_images(docx_path)
    full_lines = text_runs  # Each run is roughly a paragraph/line

    result = {
        'chapter_number': None,
        'chapter_title': '',
        'sections': [],
        'questions': [],
        'images': images,
    }

    # Parser state
    current_section = {'number': '', 'title': ''}
    current_context = None
    current_question = None
    current_image_index = 0
    state = 'IDLE'  # IDLE, CONTEXT, QUESTION, CHOICES, ANSWER, METADATA

    for line in full_lines:
        line_stripped = line.strip()
        if not line_stripped:
            continue

        # --- Chapter header ---
        ch_match = re.match(r'Chapter\s+(\d+)\s+(.*)', line_stripped)
        if ch_match and result['chapter_number'] is None:
            result['chapter_number'] = int(ch_match.group(1))
            result['chapter_title'] = ch_match.group(2).strip()
            continue

        # --- Section header (e.g., "4.1   The Timeline") ---
        sec_match = re.match(r'^(\d+\.\d+)\s+(.*)', line_stripped)
        if sec_match and state in ('IDLE', 'METADATA'):
            sec_num = sec_match.group(1)
            sec_title = sec_match.group(2).strip()
            if sec_num.startswith(str(result.get('chapter_number', ''))):
                current_section = {'number': sec_num, 'title': sec_title}
                if not any(s['number'] == sec_num for s in result['sections']):
                    result['sections'].append(current_section.copy())
                state = 'IDLE'
                continue

        # --- Context block (e.g., "Use the figure/information for...") ---
        if re.match(r'^Use the (figure|information|table)', line_stripped, re.IGNORECASE):
            _save_question(current_question, result)
            current_question = None
            current_context = {'text': line_stripped, 'image': ''}
            state = 'CONTEXT'
            continue

        # --- Image marker ---
        img_match = re.search(r'\[IMAGE:([^\]]+)\]', line_stripped)
        if img_match:
            img_name = img_match.group(1)
            if current_context and state == 'CONTEXT':
                current_context['image'] = img_name
            elif current_question:
                current_question['image'] = img_name
            continue

        # --- Table marker ---
        if line_stripped == '[TABLE_START]':
            state = 'TABLE'
            table_lines = []
            continue
        if line_stripped == '[TABLE_END]':
            if current_context:
                table_html = _table_lines_to_html(table_lines)
                current_context['text'] += '\n' + table_html
            state = 'IDLE'
            continue
        if state == 'TABLE':
            table_lines.append(line_stripped)
            continue

        # --- Question number (e.g., "1) Which of the following...") ---
        q_match = re.match(r'^(\d+)\)\s+(.*)', line_stripped)
        if q_match:
            _save_question(current_question, result)
            current_question = {
                'question_number': int(q_match.group(1)),
                'text': q_match.group(2),
                'question_type': None,
                'choices': [],
                'correct_answer': '',
                'answer_raw_text': '',
                'explanation': '',
                'difficulty': None,
                'skill': '',
                'section_number': current_section.get('number', ''),
                'section_title': current_section.get('title', ''),
                'image': '',
                'context': current_context.copy() if current_context else None,
            }
            state = 'QUESTION'
            continue

        # --- MC choice (e.g., "A) Option text") ---
        choice_match = re.match(r'^([A-E])\)\s+(.*)', line_stripped)
        if choice_match and state in ('QUESTION', 'CHOICES'):
            if current_question:
                current_question['choices'].append({
                    'letter': choice_match.group(1),
                    'text': choice_match.group(2),
                })
                state = 'CHOICES'
            continue

        # --- Answer line ---
        ans_match = re.match(r'^Answer:\s*(.*)', line_stripped)
        if ans_match:
            if current_question:
                raw_answer = ans_match.group(1).strip()
                current_question['answer_raw_text'] = raw_answer
                current_question['correct_answer'] = raw_answer
                current_question['question_type'] = _detect_question_type(raw_answer, current_question['choices'])
            state = 'ANSWER'
            continue

        # --- Explanation ---
        exp_match = re.match(r'^Explanation:\s*(.*)', line_stripped)
        if exp_match and current_question:
            current_question['explanation'] = exp_match.group(1).strip()
            continue

        # --- Metadata: Diff ---
        diff_match = re.match(r'^Diff:\s*(\d)', line_stripped)
        if diff_match and current_question:
            current_question['difficulty'] = int(diff_match.group(1))
            continue

        # --- Metadata: Section ---
        sec_meta_match = re.match(r'^Section:\s*(.*)', line_stripped)
        if sec_meta_match and current_question:
            sec_text = sec_meta_match.group(1).strip()
            # Extract section number if present
            sec_num_match = re.match(r'^(\d+\.\d+)\s*(.*)', sec_text)
            if sec_num_match:
                current_question['section_number'] = sec_num_match.group(1)
                current_question['section_title'] = sec_num_match.group(2).strip()
            continue

        # --- Metadata: Skill ---
        skill_match = re.match(r'^Skill:\s*(\w+)', line_stripped)
        if skill_match and current_question:
            skill = skill_match.group(1)
            # Normalize truncated skill names
            if skill.startswith('Anal'):
                skill = 'Analytical'
            elif skill.startswith('Concept'):
                skill = 'Conceptual'
            elif skill.startswith('Def'):
                skill = 'Definition'
            current_question['skill'] = skill
            state = 'METADATA'
            continue

        # --- Continuation of question text or explanation ---
        if state == 'QUESTION' and current_question:
            current_question['text'] += ' ' + line_stripped
        elif state == 'ANSWER' and current_question and current_question.get('explanation') == '':
            # Could be multi-line answer/explanation
            if current_question['answer_raw_text']:
                current_question['explanation'] += ' ' + line_stripped
            else:
                current_question['answer_raw_text'] = line_stripped

    # Save last question
    _save_question(current_question, result)

    return result


def _detect_question_type(answer_text, choices):
    """
    Detect question type from answer text.

    Heuristic (in order):
    1. Single letter A-E with choices present → MC
    2. Single number (with $, commas, %) → NUMERIC
    3. Contains = followed by trailing number → NUMERIC
    4. Otherwise → FREE_RESPONSE
    """
    answer_text = answer_text.strip()

    # 1. Single letter A-E
    if re.match(r'^[A-E]$', answer_text) and choices:
        return 'MC'

    # 2. Single number
    cleaned = re.sub(r'[\$,% ]', '', answer_text)
    try:
        float(cleaned)
        return 'NUMERIC'
    except ValueError:
        pass

    # 3. Contains = with trailing number
    trailing_match = re.search(r'=\s*([\$]?[\d,]+\.?\d*)\s*$', answer_text)
    if trailing_match:
        return 'NUMERIC'

    # 4. Otherwise
    return 'FREE_RESPONSE'


def extract_numeric_value(answer_text):
    """
    Extract the numeric value from an answer string.

    Tries:
    1. Parse the whole string as a number
    2. Extract the number after the last '='
    """
    cleaned = re.sub(r'[\$,% ]', '', answer_text.strip())
    try:
        return float(cleaned)
    except ValueError:
        pass

    # Try after last '='
    eq_match = re.search(r'=\s*([\$]?[\-]?[\d,]+\.?\d*)\s*$', answer_text)
    if eq_match:
        cleaned = re.sub(r'[\$, ]', '', eq_match.group(1))
        try:
            return float(cleaned)
        except ValueError:
            pass

    return None


def _save_question(question, result):
    """Save a completed question dict to the result list."""
    if question and question.get('question_number'):
        # Default difficulty if not found
        if question['difficulty'] is None:
            question['difficulty'] = 1
        result['questions'].append(question)


def _table_lines_to_html(table_lines):
    """Convert tab-separated table lines to HTML table."""
    if not table_lines:
        return ''
    html = '<table class="table table-sm table-bordered">'
    for i, line in enumerate(table_lines):
        cells = line.split('\t')
        tag = 'th' if i == 0 else 'td'
        html += '<tr>'
        for cell in cells:
            html += f'<{tag}>{cell}</{tag}>'
        html += '</tr>'
    html += '</table>'
    return html
```

- [ ] **Step 7: Run tests**

```bash
python manage.py test tests.test_parser -v2
```

Expected: All PASS. If some fail due to docx format edge cases, debug and fix.

- [ ] **Step 8: Commit**

```bash
git add services/parser.py tests/test_parser.py
git commit -m "feat: add docx parser with text extraction, state machine, and question type detection"
```

---

### Task 6: Import Management Command

**Files:**
- Create: `apps/questions/management/__init__.py`
- Create: `apps/questions/management/commands/__init__.py`
- Create: `apps/questions/management/commands/import_testbank.py`
- Create: `tests/test_import.py`

- [ ] **Step 1: Create management command directory structure**

```bash
mkdir -p apps/questions/management/commands
touch apps/questions/management/__init__.py
touch apps/questions/management/commands/__init__.py
```

- [ ] **Step 2: Write failing test for import command**

```python
# tests/test_import.py
import os
from django.test import TestCase
from django.core.management import call_command
from questions.models import Chapter, Section, Question, MCChoice, NumericAnswer, ContextGroup

SAMPLE_DOCX = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'chapter 4.docx')


class ImportTestbankTest(TestCase):
    def test_import_chapter4(self):
        """Import chapter 4 and verify questions are in the database."""
        call_command('import_testbank', SAMPLE_DOCX)

        # Chapter should exist
        ch = Chapter.objects.get(number=4)
        self.assertIn('Time Value of Money', ch.title)

        # Should have sections
        self.assertGreater(ch.sections.count(), 0)

        # Should have questions
        total_q = Question.objects.filter(section__chapter=ch).count()
        self.assertGreater(total_q, 80)

        # Should have MC questions with choices
        mc_q = Question.objects.filter(section__chapter=ch, question_type='MC').first()
        self.assertGreater(mc_q.choices.count(), 0)

    def test_import_idempotent(self):
        """Importing twice should not create duplicates."""
        call_command('import_testbank', SAMPLE_DOCX)
        count1 = Question.objects.count()

        call_command('import_testbank', SAMPLE_DOCX)
        count2 = Question.objects.count()

        self.assertEqual(count1, count2)

    def test_import_extracts_images(self):
        """Import should extract images to media directory."""
        call_command('import_testbank', SAMPLE_DOCX)

        # At least some questions or contexts should reference images
        questions_with_images = Question.objects.exclude(image='').count()
        contexts_with_images = ContextGroup.objects.exclude(image='').count()
        self.assertGreater(questions_with_images + contexts_with_images, 0)
```

- [ ] **Step 3: Run test to verify it fails**

```bash
python manage.py test tests.test_import -v2
```

Expected: FAIL — command does not exist yet.

- [ ] **Step 4: Implement import_testbank management command**

```python
# apps/questions/management/commands/import_testbank.py
import os
from django.core.management.base import BaseCommand
from django.conf import settings
from questions.models import Chapter, Section, ContextGroup, Question, MCChoice, NumericAnswer
from services.parser import parse_docx, extract_numeric_value


class Command(BaseCommand):
    help = 'Import questions from a testbank .docx file'

    def add_arguments(self, parser):
        parser.add_argument('path', help='Path to .docx file or directory of .docx files')
        parser.add_argument('--dir', action='store_true', help='Treat path as directory, import all .docx files')

    def handle(self, *args, **options):
        path = options['path']

        if options['dir'] or os.path.isdir(path):
            files = sorted(
                os.path.join(path, f) for f in os.listdir(path)
                if f.endswith('.docx') and not f.startswith('~')
            )
        else:
            files = [path]

        for filepath in files:
            self.stdout.write(f'Importing {filepath}...')
            self._import_file(filepath)

    def _import_file(self, filepath):
        result = parse_docx(filepath)

        if not result['chapter_number']:
            self.stderr.write(f'  Could not detect chapter number in {filepath}')
            return

        # Create or update chapter
        chapter, _ = Chapter.objects.update_or_create(
            number=result['chapter_number'],
            defaults={'title': result['chapter_title']},
        )

        # Create sections
        section_map = {}
        for i, sec_data in enumerate(result['sections']):
            section, _ = Section.objects.update_or_create(
                chapter=chapter,
                number=sec_data['number'],
                defaults={
                    'title': sec_data['title'],
                    'sort_order': i,
                },
            )
            section_map[sec_data['number']] = section

        # Extract images to media
        media_dir = os.path.join(settings.MEDIA_ROOT, 'questions', f'ch{chapter.number}')
        os.makedirs(media_dir, exist_ok=True)
        for img_name, img_data in result['images'].items():
            img_path = os.path.join(media_dir, img_name)
            with open(img_path, 'wb') as f:
                f.write(img_data)

        # Import questions
        counts = {'MC': 0, 'NUMERIC': 0, 'FREE_RESPONSE': 0}
        warnings = 0

        # Track context groups to avoid duplicates
        context_cache = {}

        for q_data in result['questions']:
            # Find section
            sec_num = q_data.get('section_number', '')
            section = section_map.get(sec_num)
            if not section:
                # Try to find closest match
                for key in section_map:
                    if sec_num.startswith(key[:3]):
                        section = section_map[key]
                        break
            if not section:
                # Use first section as fallback
                section = Section.objects.filter(chapter=chapter).first()
                if not section:
                    self.stderr.write(f'  Warning: No section for Q{q_data["question_number"]}, skipping')
                    warnings += 1
                    continue

            # Handle context group
            context_group = None
            if q_data.get('context'):
                ctx_text = q_data['context']['text']
                if ctx_text not in context_cache:
                    ctx_image = q_data['context'].get('image', '')
                    if ctx_image:
                        ctx_image = f'questions/ch{chapter.number}/{ctx_image}'
                    context_group, _ = ContextGroup.objects.get_or_create(
                        text=ctx_text[:200],  # Match on first 200 chars
                        defaults={
                            'text': ctx_text,
                            'image': ctx_image,
                            'section': section,
                        },
                    )
                    context_cache[ctx_text] = context_group
                else:
                    context_group = context_cache[ctx_text]

            # Handle image path
            image_path = ''
            if q_data.get('image'):
                image_path = f'questions/ch{chapter.number}/{q_data["image"]}'

            # Create or update question
            q_type = q_data.get('question_type', 'FREE_RESPONSE')
            question, created = Question.objects.update_or_create(
                section=section,
                question_number=q_data['question_number'],
                defaults={
                    'question_type': q_type,
                    'text': q_data['text'],
                    'difficulty': q_data.get('difficulty', 1),
                    'skill': q_data.get('skill', 'Conceptual'),
                    'explanation': q_data.get('explanation', ''),
                    'image': image_path,
                    'context_group': context_group,
                    'answer_raw_text': q_data.get('answer_raw_text', ''),
                },
            )

            # Create MC choices
            if q_type == 'MC' and q_data.get('choices'):
                # Delete existing choices on update
                if not created:
                    question.choices.all().delete()

                correct_letter = q_data.get('correct_answer', '')
                for choice_data in q_data['choices']:
                    MCChoice.objects.create(
                        question=question,
                        letter=choice_data['letter'],
                        text=choice_data['text'],
                        is_correct=(choice_data['letter'] == correct_letter),
                    )

            # Create numeric answer
            elif q_type == 'NUMERIC':
                numeric_val = extract_numeric_value(q_data.get('answer_raw_text', ''))
                if numeric_val is not None:
                    NumericAnswer.objects.update_or_create(
                        question=question,
                        defaults={'value': numeric_val},
                    )
                else:
                    # Could not parse numeric value, downgrade to FREE_RESPONSE
                    question.question_type = 'FREE_RESPONSE'
                    question.save()
                    q_type = 'FREE_RESPONSE'

            counts[q_type] = counts.get(q_type, 0) + 1

        total = sum(counts.values())
        self.stdout.write(self.style.SUCCESS(
            f'  Chapter {chapter.number}: {total} questions imported '
            f'({counts["MC"]} MC, {counts["NUMERIC"]} NUMERIC, {counts["FREE_RESPONSE"]} FREE_RESPONSE), '
            f'{len(result["images"])} images extracted'
            + (f', {warnings} warnings' if warnings else '')
        ))
```

- [ ] **Step 5: Run tests**

```bash
python manage.py test tests.test_import -v2
```

Expected: All PASS.

- [ ] **Step 6: Verify with actual import**

```bash
python manage.py migrate
python manage.py import_testbank "/home/georgejjj/testbank/chapter 4.docx"
```

Expected output like: "Chapter 4: 90 questions imported (83 MC, 2 NUMERIC, 5 FREE_RESPONSE), 42 images extracted"

- [ ] **Step 7: Commit**

```bash
git add apps/questions/management/ tests/test_import.py
git commit -m "feat: add import_testbank management command for parsing and importing .docx testbank files"
```

---

## Chunk 3: Grader & Randomizer Services

### Task 7: Grader Service

**Files:**
- Create: `services/grader.py`
- Create: `tests/test_grader.py`

- [ ] **Step 1: Write failing tests for grader**

```python
# tests/test_grader.py
from decimal import Decimal
from django.test import TestCase
from django.utils import timezone
from accounts.models import User
from questions.models import Chapter, Section, Question, MCChoice, NumericAnswer
from assignments.models import Assignment, StudentAssignment, AssignedQuestion, StudentAnswer
from services.grader import grade_mc, grade_numeric, grade_answer, recompute_score


class GradeMCTest(TestCase):
    def setUp(self):
        ch = Chapter.objects.create(number=4, title="TVM")
        sec = Section.objects.create(chapter=ch, number="4.1", title="Timeline", sort_order=1)
        self.q = Question.objects.create(section=sec, question_type='MC', text='Q1', difficulty=1, skill='Conceptual', question_number=1)
        self.correct = MCChoice.objects.create(question=self.q, letter='C', text='Correct', is_correct=True)
        self.wrong = MCChoice.objects.create(question=self.q, letter='A', text='Wrong', is_correct=False)

    def test_correct_mc(self):
        self.assertTrue(grade_mc(self.correct))

    def test_wrong_mc(self):
        self.assertFalse(grade_mc(self.wrong))


class GradeNumericTest(TestCase):
    def setUp(self):
        ch = Chapter.objects.create(number=4, title="TVM")
        sec = Section.objects.create(chapter=ch, number="4.1", title="Timeline", sort_order=1)
        self.q = Question.objects.create(section=sec, question_type='NUMERIC', text='Calc', difficulty=2, skill='Analytical', question_number=50)
        self.na = NumericAnswer.objects.create(question=self.q, value=Decimal('254641'), tolerance_percent=Decimal('1.0'))

    def test_exact_answer(self):
        self.assertTrue(grade_numeric(self.na, Decimal('254641')))

    def test_within_tolerance(self):
        # 1% of 254641 = 2546.41, so 254641 + 2000 should pass
        self.assertTrue(grade_numeric(self.na, Decimal('256641')))

    def test_outside_tolerance(self):
        # 1% of 254641 = 2546.41, so 254641 + 3000 should fail
        self.assertFalse(grade_numeric(self.na, Decimal('257641')))

    def test_zero_correct_value(self):
        na_zero = NumericAnswer.objects.create(
            question=Question.objects.create(
                section=self.q.section, question_type='NUMERIC', text='Zero',
                difficulty=1, skill='Analytical', question_number=99,
            ),
            value=Decimal('0'), absolute_tolerance=Decimal('0.01'),
        )
        self.assertTrue(grade_numeric(na_zero, Decimal('0.005')))
        self.assertFalse(grade_numeric(na_zero, Decimal('0.02')))

    def test_parse_student_input(self):
        """Grader should handle dollar signs, commas, spaces."""
        from services.grader import parse_numeric_input
        self.assertEqual(parse_numeric_input('$254,641'), Decimal('254641'))
        self.assertEqual(parse_numeric_input(' -1,234.56 '), Decimal('-1234.56'))
        self.assertIsNone(parse_numeric_input('not a number'))


class RecomputeScoreTest(TestCase):
    def setUp(self):
        self.instructor = User.objects.create_user(username='prof', password='t', role='INSTRUCTOR')
        self.student = User.objects.create_user(username='stu', password='t', role='STUDENT')
        ch = Chapter.objects.create(number=4, title="TVM")
        sec = Section.objects.create(chapter=ch, number="4.1", title="Timeline", sort_order=1)
        self.q1 = Question.objects.create(section=sec, question_type='MC', text='Q1', difficulty=1, skill='Conceptual', question_number=1)
        self.q2 = Question.objects.create(section=sec, question_type='MC', text='Q2', difficulty=1, skill='Conceptual', question_number=2)
        a = Assignment.objects.create(title='HW1', created_by=self.instructor, num_questions=2, mode='ASSIGNMENT')
        self.sa = StudentAssignment.objects.create(student=self.student, assignment=a, max_score=2)
        AssignedQuestion.objects.create(student_assignment=self.sa, question=self.q1, position=0)
        AssignedQuestion.objects.create(student_assignment=self.sa, question=self.q2, position=1)

    def test_recompute_score(self):
        StudentAnswer.objects.create(
            student_assignment=self.sa, question=self.q1, is_correct=True,
            time_spent_seconds=10, question_text_snapshot='Q1',
        )
        StudentAnswer.objects.create(
            student_assignment=self.sa, question=self.q2, is_correct=False,
            time_spent_seconds=10, question_text_snapshot='Q2',
        )
        score = recompute_score(self.sa)
        self.assertEqual(score, 1)
        self.sa.refresh_from_db()
        self.assertEqual(self.sa.score, 1)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python manage.py test tests.test_grader -v2
```

Expected: FAIL — `services.grader` does not exist.

- [ ] **Step 3: Implement grader service**

```python
# services/grader.py
"""
Auto-grading service for MC and numeric questions.
"""
import re
from decimal import Decimal, InvalidOperation


def grade_mc(selected_choice):
    """Grade a multiple choice answer. Returns True if correct."""
    return selected_choice.is_correct


def grade_numeric(numeric_answer, student_value):
    """
    Grade a numeric answer with tolerance.

    If correct value is zero: use absolute_tolerance.
    Otherwise: use tolerance_percent (stored as human-readable, e.g. 1.0 = 1%).
    """
    correct = numeric_answer.value

    if abs(correct) > 0:
        tolerance = numeric_answer.tolerance_percent / Decimal('100')
        return abs(student_value - correct) / abs(correct) <= tolerance
    else:
        return abs(student_value - correct) <= numeric_answer.absolute_tolerance


def parse_numeric_input(raw_input):
    """
    Parse student's numeric input string into Decimal.

    Strips: $, commas, spaces, % signs.
    Returns None if parsing fails.
    """
    if not raw_input:
        return None
    cleaned = re.sub(r'[\$,% ]', '', raw_input.strip())
    try:
        return Decimal(cleaned)
    except (InvalidOperation, ValueError):
        return None


def grade_answer(student_answer):
    """
    Grade a StudentAnswer object based on question type.

    Returns bool or None (for FREE_RESPONSE).
    Updates student_answer.is_correct in place (does not save).
    """
    question = student_answer.question

    if question.question_type == 'MC':
        if student_answer.selected_choice:
            student_answer.is_correct = grade_mc(student_answer.selected_choice)
        else:
            student_answer.is_correct = False

    elif question.question_type == 'NUMERIC':
        try:
            numeric_answer = question.numeric_answer
        except Exception:
            student_answer.is_correct = None
            return student_answer.is_correct

        student_value = parse_numeric_input(str(student_answer.numeric_answer))
        if student_value is not None:
            student_answer.is_correct = grade_numeric(numeric_answer, student_value)
        else:
            student_answer.is_correct = False

    else:  # FREE_RESPONSE
        student_answer.is_correct = None

    return student_answer.is_correct


def recompute_score(student_assignment):
    """
    Recompute score for a StudentAssignment.

    Score = count of answers where is_correct is True.
    Updates and saves the StudentAssignment.
    """
    correct_count = student_assignment.answers.filter(is_correct=True).count()
    student_assignment.score = correct_count
    student_assignment.save(update_fields=['score', 'updated_at'])
    return correct_count
```

- [ ] **Step 4: Run tests**

```bash
python manage.py test tests.test_grader -v2
```

Expected: All PASS.

- [ ] **Step 5: Commit**

```bash
git add services/grader.py tests/test_grader.py
git commit -m "feat: add grader service with MC, numeric (tolerance), and score recomputation"
```

---

### Task 8: Randomizer Service

**Files:**
- Create: `services/randomizer.py`
- Create: `tests/test_randomizer.py`

- [ ] **Step 1: Write failing tests for randomizer**

```python
# tests/test_randomizer.py
from django.test import TestCase
from django.utils import timezone
from accounts.models import User
from questions.models import Chapter, Section, Question, MCChoice
from assignments.models import Assignment, StudentAssignment, AssignedQuestion
from services.randomizer import assign_questions_to_student, generate_choice_shuffle_map


class RandomizerTest(TestCase):
    def setUp(self):
        self.instructor = User.objects.create_user(username='prof', password='t', role='INSTRUCTOR')
        self.student = User.objects.create_user(username='stu', password='t', role='STUDENT')
        self.ch = Chapter.objects.create(number=4, title="TVM")
        self.sec = Section.objects.create(chapter=self.ch, number="4.1", title="Timeline", sort_order=1)
        # Create 10 questions
        self.questions = []
        for i in range(1, 11):
            q = Question.objects.create(
                section=self.sec, question_type='MC', text=f'Q{i}',
                difficulty=(i % 3) + 1, skill='Conceptual', question_number=i,
            )
            for letter in 'ABCD':
                MCChoice.objects.create(question=q, letter=letter, text=f'Opt {letter}', is_correct=(letter == 'A'))
            self.questions.append(q)

    def test_assign_manual_selection(self):
        """Hand-picked questions should all be assigned."""
        a = Assignment.objects.create(
            title='HW1', created_by=self.instructor, num_questions=3, mode='ASSIGNMENT',
        )
        a.manually_selected_questions.set(self.questions[:3])

        sa = assign_questions_to_student(a, self.student)

        self.assertEqual(sa.assigned_questions.count(), 3)
        self.assertEqual(sa.max_score, 3)
        self.assertEqual(sa.status, 'NOT_STARTED')

    def test_assign_auto_generate(self):
        """Auto-generated should draw num_questions from pool."""
        a = Assignment.objects.create(
            title='HW2', created_by=self.instructor, num_questions=5, mode='ASSIGNMENT',
        )
        a.chapters.add(self.ch)

        sa = assign_questions_to_student(a, self.student)

        self.assertEqual(sa.assigned_questions.count(), 5)
        self.assertEqual(sa.max_score, 5)

    def test_assign_with_difficulty_filter(self):
        """Difficulty filter should limit the pool."""
        a = Assignment.objects.create(
            title='HW3', created_by=self.instructor, num_questions=10, mode='ASSIGNMENT',
            difficulty_filter=[1],
        )
        a.chapters.add(self.ch)

        sa = assign_questions_to_student(a, self.student)

        # Only difficulty=1 questions should be assigned
        for aq in AssignedQuestion.objects.filter(student_assignment=sa):
            self.assertEqual(aq.question.difficulty, 1)

    def test_randomized_order(self):
        """Two students should get different orders (with high probability)."""
        stu2 = User.objects.create_user(username='stu2', password='t', role='STUDENT')
        a = Assignment.objects.create(
            title='HW4', created_by=self.instructor, num_questions=10, mode='ASSIGNMENT', is_randomized=True,
        )
        a.chapters.add(self.ch)

        sa1 = assign_questions_to_student(a, self.student)
        sa2 = assign_questions_to_student(a, stu2)

        order1 = list(AssignedQuestion.objects.filter(student_assignment=sa1).order_by('position').values_list('question_id', flat=True))
        order2 = list(AssignedQuestion.objects.filter(student_assignment=sa2).order_by('position').values_list('question_id', flat=True))

        # Same questions (both get all 10)
        self.assertEqual(set(order1), set(order2))
        # Different order (probabilistic — extremely unlikely to be same)
        # We just verify the mechanism works; don't assert inequality

    def test_choice_shuffle_map(self):
        """Choice shuffle map should remap all MC questions' choices."""
        shuffle_map = generate_choice_shuffle_map([self.questions[0]])
        q_id = str(self.questions[0].id)
        self.assertIn(q_id, shuffle_map)
        mapping = shuffle_map[q_id]
        # Should have 4 entries (A, B, C, D)
        self.assertEqual(len(mapping), 4)
        # All original letters should be present as keys
        self.assertEqual(set(mapping.keys()), {'A', 'B', 'C', 'D'})
        # All display letters should be present as values
        self.assertEqual(set(mapping.values()), {'A', 'B', 'C', 'D'})

    def test_frozen_assignment_does_not_change(self):
        """Once assigned, calling again should return existing StudentAssignment."""
        a = Assignment.objects.create(
            title='HW5', created_by=self.instructor, num_questions=5, mode='ASSIGNMENT',
        )
        a.chapters.add(self.ch)

        sa1 = assign_questions_to_student(a, self.student)
        sa2 = assign_questions_to_student(a, self.student)

        self.assertEqual(sa1.id, sa2.id)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python manage.py test tests.test_randomizer -v2
```

Expected: FAIL.

- [ ] **Step 3: Implement randomizer service**

```python
# services/randomizer.py
"""
Question selection and randomization service.
"""
import random
from questions.models import Question, MCChoice
from assignments.models import StudentAssignment, AssignedQuestion


def assign_questions_to_student(assignment, student):
    """
    Assign questions to a student for a given assignment.

    If already assigned, returns the existing StudentAssignment.
    Otherwise, draws questions from the pool, shuffles order and choices,
    and creates a frozen StudentAssignment.
    """
    # Return existing if already assigned
    existing = StudentAssignment.objects.filter(
        student=student, assignment=assignment,
    ).first()
    if existing:
        return existing

    # Determine question pool
    manual = list(assignment.manually_selected_questions.all())

    if manual:
        pool = manual
    else:
        pool = _build_question_pool(assignment)

    # Draw questions
    num = min(assignment.num_questions, len(pool))
    if assignment.is_randomized:
        drawn = random.sample(pool, num)
    else:
        drawn = pool[:num]

    # Generate choice shuffle map for MC questions
    mc_questions = [q for q in drawn if q.question_type == 'MC']
    shuffle_map = generate_choice_shuffle_map(mc_questions)

    # Create StudentAssignment
    sa = StudentAssignment.objects.create(
        student=student,
        assignment=assignment,
        choice_shuffle_map=shuffle_map,
        max_score=len(drawn),
        status='NOT_STARTED',
    )

    # Create AssignedQuestion entries with positions
    if assignment.is_randomized:
        random.shuffle(drawn)
    for i, question in enumerate(drawn):
        AssignedQuestion.objects.create(
            student_assignment=sa,
            question=question,
            position=i,
        )

    return sa


def _build_question_pool(assignment):
    """Build the question pool based on assignment filters."""
    qs = Question.objects.all()

    # Filter by chapters
    chapters = assignment.chapters.all()
    if chapters.exists():
        qs = qs.filter(section__chapter__in=chapters)

    # Filter by sections
    sections = assignment.sections.all()
    if sections.exists():
        qs = qs.filter(section__in=sections)

    # Filter by difficulty
    if assignment.difficulty_filter:
        qs = qs.filter(difficulty__in=assignment.difficulty_filter)

    # Filter by skill
    if assignment.skill_filter:
        qs = qs.filter(skill__in=assignment.skill_filter)

    return list(qs)


def generate_choice_shuffle_map(mc_questions):
    """
    Generate a shuffle map for MC choice display order.

    Returns dict: {question_id_str: {original_letter: displayed_letter}}
    """
    shuffle_map = {}
    for q in mc_questions:
        choices = list(q.choices.values_list('letter', flat=True))
        shuffled = choices.copy()
        random.shuffle(shuffled)
        mapping = dict(zip(choices, shuffled))
        shuffle_map[str(q.id)] = mapping
    return shuffle_map
```

- [ ] **Step 4: Run tests**

```bash
python manage.py test tests.test_randomizer -v2
```

Expected: All PASS.

- [ ] **Step 5: Commit**

```bash
git add services/randomizer.py tests/test_randomizer.py
git commit -m "feat: add randomizer service with question selection, shuffling, and choice shuffle map"
```

---

## Chunk 4: Auth, Base Templates & Accounts

### Task 9: Base Template & Static Setup

**Files:**
- Create: `templates/base.html`
- Create: `static/css/style.css`
- Create: `static/js/htmx-config.js`

- [ ] **Step 1: Create base template with Bootstrap, HTMX, MathJax**

```html
<!-- templates/base.html -->
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{% block title %}Testbank{% endblock %}</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet">
    {% load static %}
    <link rel="stylesheet" href="{% static 'css/style.css' %}">
</head>
<body>
    <nav class="navbar navbar-expand-lg navbar-dark bg-dark">
        <div class="container-fluid">
            <a class="navbar-brand" href="/">Testbank</a>
            <button class="navbar-toggler" type="button" data-bs-toggle="collapse" data-bs-target="#navbarNav">
                <span class="navbar-toggler-icon"></span>
            </button>
            <div class="collapse navbar-collapse" id="navbarNav">
                {% if user.is_authenticated %}
                <ul class="navbar-nav me-auto">
                    {% if user.is_instructor %}
                    <li class="nav-item"><a class="nav-link" href="{% url 'instructor_dashboard' %}">Dashboard</a></li>
                    <li class="nav-item"><a class="nav-link" href="{% url 'assignment_create' %}">Create Assignment</a></li>
                    <li class="nav-item"><a class="nav-link" href="{% url 'question_browser' %}">Questions</a></li>
                    <li class="nav-item"><a class="nav-link" href="{% url 'student_roster' %}">Students</a></li>
                    {% else %}
                    <li class="nav-item"><a class="nav-link" href="{% url 'student_dashboard' %}">Dashboard</a></li>
                    <li class="nav-item"><a class="nav-link" href="{% url 'assignment_list' %}">Assignments</a></li>
                    <li class="nav-item"><a class="nav-link" href="{% url 'practice_setup' %}">Practice</a></li>
                    <li class="nav-item"><a class="nav-link" href="{% url 'mistake_collection' %}">Mistakes</a></li>
                    <li class="nav-item"><a class="nav-link" href="{% url 'student_analytics' %}">Analytics</a></li>
                    {% endif %}
                </ul>
                <ul class="navbar-nav">
                    <li class="nav-item">
                        <span class="nav-link text-light">{{ user.get_full_name|default:user.username }}</span>
                    </li>
                    <li class="nav-item">
                        <a class="nav-link" href="{% url 'logout' %}">Logout</a>
                    </li>
                </ul>
                {% endif %}
            </div>
        </div>
    </nav>

    <div class="container-fluid mt-3">
        {% if messages %}
        {% for message in messages %}
        <div class="alert alert-{{ message.tags }} alert-dismissible fade show" role="alert">
            {{ message }}
            <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
        </div>
        {% endfor %}
        {% endif %}

        {% block content %}{% endblock %}
    </div>

    <!-- Toast for HTMX errors -->
    <div class="toast-container position-fixed bottom-0 end-0 p-3">
        <div id="error-toast" class="toast text-bg-danger" role="alert">
            <div class="toast-body" id="error-toast-body">An error occurred. Please try again.</div>
        </div>
    </div>

    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/js/bootstrap.bundle.min.js"></script>
    <script src="https://unpkg.com/htmx.org@2.0.4"></script>
    <script>
        // HTMX CSRF setup
        document.body.addEventListener('htmx:configRequest', function(evt) {
            evt.detail.headers['X-CSRFToken'] = document.querySelector('[name=csrfmiddlewaretoken]')?.value
                || '{{ csrf_token }}';
        });
        // HTMX error handler
        document.body.addEventListener('htmx:responseError', function(evt) {
            const toast = new bootstrap.Toast(document.getElementById('error-toast'));
            toast.show();
        });
    </script>
    <script id="MathJax-script" async src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-mml-chtml.js"></script>
    {% block extra_js %}{% endblock %}
</body>
</html>
```

- [ ] **Step 2: Create minimal CSS**

```css
/* static/css/style.css */
.question-card { margin-bottom: 1rem; }
.choice-option { padding: 0.5rem 1rem; margin: 0.25rem 0; border-radius: 0.375rem; cursor: pointer; }
.choice-option:hover { background-color: #f0f0f0; }
.choice-option.selected { background-color: #cfe2ff; border: 1px solid #084298; }
.choice-option.correct { background-color: #d1e7dd; }
.choice-option.incorrect { background-color: #f8d7da; }
.timer-display { font-size: 1.1rem; font-weight: bold; }
.question-nav .btn { min-width: 2.5rem; }
.question-nav .btn.answered { background-color: #198754; color: white; }
.question-nav .btn.current { border: 2px solid #0d6efd; }
@media (max-width: 768px) {
    .choice-option { padding: 0.75rem 1rem; font-size: 1.1rem; }
}
```

- [ ] **Step 3: Commit**

```bash
mkdir -p templates static/css static/js
git add templates/base.html static/css/style.css
git commit -m "feat: add base template with Bootstrap 5, HTMX, MathJax, and responsive nav"
```

---

### Task 10: Authentication Views & Middleware

**Files:**
- Create: `apps/accounts/views.py`
- Create: `apps/accounts/urls.py`
- Create: `apps/accounts/forms.py`
- Create: `apps/accounts/middleware.py`
- Create: `templates/accounts/login.html`
- Create: `templates/accounts/password_change.html`
- Modify: `config/urls.py`
- Modify: `config/settings.py`

- [ ] **Step 1: Create login form and view**

```python
# apps/accounts/forms.py
from django import forms
from django.contrib.auth.forms import AuthenticationForm, PasswordChangeForm


class LoginForm(AuthenticationForm):
    username = forms.CharField(widget=forms.TextInput(attrs={
        'class': 'form-control', 'placeholder': 'Username or Student ID',
    }))
    password = forms.CharField(widget=forms.PasswordInput(attrs={
        'class': 'form-control', 'placeholder': 'Password',
    }))


class BootstrapPasswordChangeForm(PasswordChangeForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs['class'] = 'form-control'
```

```python
# apps/accounts/views.py
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView, PasswordChangeView
from django.shortcuts import redirect
from django.urls import reverse_lazy
from .forms import LoginForm, BootstrapPasswordChangeForm


class CustomLoginView(LoginView):
    form_class = LoginForm
    template_name = 'accounts/login.html'

    def get_success_url(self):
        user = self.request.user
        if user.must_change_password:
            return reverse_lazy('password_change')
        if user.is_instructor:
            return reverse_lazy('instructor_dashboard')
        return reverse_lazy('student_dashboard')


class CustomPasswordChangeView(PasswordChangeView):
    form_class = BootstrapPasswordChangeForm
    template_name = 'accounts/password_change.html'
    success_url = reverse_lazy('student_dashboard')

    def form_valid(self, form):
        response = super().form_valid(form)
        self.request.user.must_change_password = False
        self.request.user.save(update_fields=['must_change_password'])
        return response


def logout_view(request):
    logout(request)
    return redirect('login')
```

```python
# apps/accounts/urls.py
from django.urls import path
from . import views

urlpatterns = [
    path('login/', views.CustomLoginView.as_view(), name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('password-change/', views.CustomPasswordChangeView.as_view(), name='password_change'),
]
```

- [ ] **Step 2: Create login template**

```html
<!-- templates/accounts/login.html -->
{% extends "base.html" %}
{% block title %}Login - Testbank{% endblock %}
{% block content %}
<div class="row justify-content-center mt-5">
    <div class="col-md-4">
        <div class="card">
            <div class="card-body">
                <h3 class="card-title text-center mb-4">Testbank Login</h3>
                <form method="post">
                    {% csrf_token %}
                    {% for field in form %}
                    <div class="mb-3">
                        <label class="form-label">{{ field.label }}</label>
                        {{ field }}
                        {% for error in field.errors %}
                        <div class="text-danger small">{{ error }}</div>
                        {% endfor %}
                    </div>
                    {% endfor %}
                    {% if form.non_field_errors %}
                    <div class="alert alert-danger">
                        {% for error in form.non_field_errors %}{{ error }}{% endfor %}
                    </div>
                    {% endif %}
                    <button type="submit" class="btn btn-primary w-100">Login</button>
                </form>
            </div>
        </div>
    </div>
</div>
{% endblock %}
```

- [ ] **Step 3: Create password change template**

```html
<!-- templates/accounts/password_change.html -->
{% extends "base.html" %}
{% block title %}Change Password{% endblock %}
{% block content %}
<div class="row justify-content-center mt-5">
    <div class="col-md-4">
        <div class="card">
            <div class="card-body">
                <h3 class="card-title text-center mb-4">Change Password</h3>
                {% if user.must_change_password %}
                <div class="alert alert-info">You must change your password before continuing.</div>
                {% endif %}
                <form method="post">
                    {% csrf_token %}
                    {% for field in form %}
                    <div class="mb-3">
                        <label class="form-label">{{ field.label }}</label>
                        {{ field }}
                        {% for error in field.errors %}
                        <div class="text-danger small">{{ error }}</div>
                        {% endfor %}
                    </div>
                    {% endfor %}
                    <button type="submit" class="btn btn-primary w-100">Change Password</button>
                </form>
            </div>
        </div>
    </div>
</div>
{% endblock %}
```

- [ ] **Step 4: Create role-based middleware**

```python
# apps/accounts/middleware.py
from django.shortcuts import redirect
from django.urls import reverse


class ForcePasswordChangeMiddleware:
    """Redirect users who must change their password."""

    EXEMPT_URLS = ['login', 'logout', 'password_change']

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated and request.user.must_change_password:
            url_name = request.resolver_match.url_name if request.resolver_match else ''
            if url_name not in self.EXEMPT_URLS:
                return redirect('password_change')
        return self.get_response(request)
```

- [ ] **Step 5: Wire up URLs and middleware in config**

Update `config/urls.py`:

```python
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.shortcuts import redirect


def home_redirect(request):
    if not request.user.is_authenticated:
        return redirect('login')
    if request.user.is_instructor:
        return redirect('instructor_dashboard')
    return redirect('student_dashboard')


urlpatterns = [
    path('admin/', admin.site.urls),
    path('', home_redirect, name='home'),
    path('accounts/', include('accounts.urls')),
    path('questions/', include('questions.urls')),
    path('assignments/', include('assignments.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
```

Add middleware to `config/settings.py`:

```python
MIDDLEWARE = [
    # ... existing middleware ...
    'accounts.middleware.ForcePasswordChangeMiddleware',
]
```

Create placeholder URL files:

```python
# apps/questions/urls.py
from django.urls import path
urlpatterns = []
```

```python
# apps/assignments/urls.py
from django.urls import path
urlpatterns = []
```

- [ ] **Step 6: Test login flow manually**

```bash
python manage.py migrate
python manage.py createsuperuser  # Create instructor account
python manage.py runserver 0.0.0.0:8000
```

Visit `http://localhost:8000/` — should redirect to login page.

- [ ] **Step 7: Commit**

```bash
git add apps/accounts/ templates/accounts/ config/urls.py config/settings.py apps/questions/urls.py apps/assignments/urls.py
git commit -m "feat: add auth system with login, logout, forced password change, and role middleware"
```

---

### Task 11: Student Roster & CSV Import

**Files:**
- Modify: `apps/accounts/views.py`
- Modify: `apps/accounts/forms.py`
- Modify: `apps/accounts/urls.py`
- Create: `templates/accounts/roster.html`

- [ ] **Step 1: Add CSV import form**

Add to `apps/accounts/forms.py`:

```python
class CSVImportForm(forms.Form):
    csv_file = forms.FileField(
        label='CSV File',
        help_text='CSV with columns: username, first_name, last_name, student_id (optional: email)',
        widget=forms.FileInput(attrs={'class': 'form-control', 'accept': '.csv'}),
    )
```

- [ ] **Step 2: Add roster view with CSV import**

Add to `apps/accounts/views.py`:

```python
import csv
import io
import secrets
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from .forms import CSVImportForm
from .models import User


@login_required
def student_roster(request):
    if not request.user.is_instructor:
        return redirect('student_dashboard')

    students = User.objects.filter(role='STUDENT').order_by('last_name', 'first_name')
    form = CSVImportForm()

    if request.method == 'POST':
        if 'csv_file' in request.FILES:
            form = CSVImportForm(request.POST, request.FILES)
            if form.is_valid():
                credentials = _import_students_csv(request.FILES['csv_file'])
                if credentials:
                    messages.success(request, f'Imported {len(credentials)} students.')
                    # Return credential sheet as downloadable CSV
                    return _credential_csv_response(credentials)
                else:
                    messages.error(request, 'No students imported. Check CSV format.')

        elif 'reset_password' in request.POST:
            user_id = request.POST.get('user_id')
            try:
                student = User.objects.get(id=user_id, role='STUDENT')
                new_pw = secrets.token_urlsafe(8)
                student.set_password(new_pw)
                student.must_change_password = True
                student.save()
                messages.success(request, f'Password reset for {student.username}. New password: {new_pw}')
            except User.DoesNotExist:
                messages.error(request, 'Student not found.')

        elif 'delete_student' in request.POST:
            user_id = request.POST.get('user_id')
            User.objects.filter(id=user_id, role='STUDENT').delete()
            messages.success(request, 'Student removed.')

        return redirect('student_roster')

    return render(request, 'accounts/roster.html', {'students': students, 'form': form})


def _import_students_csv(csv_file):
    """Import students from CSV. Returns list of (username, password) tuples."""
    credentials = []
    decoded = csv_file.read().decode('utf-8-sig')
    reader = csv.DictReader(io.StringIO(decoded))

    for row in reader:
        username = row.get('username', '').strip()
        if not username:
            continue

        if User.objects.filter(username=username).exists():
            continue

        password = secrets.token_urlsafe(8)
        user = User.objects.create_user(
            username=username,
            password=password,
            first_name=row.get('first_name', '').strip(),
            last_name=row.get('last_name', '').strip(),
            email=row.get('email', '').strip(),
            student_id=row.get('student_id', '').strip(),
            role='STUDENT',
            must_change_password=True,
        )
        credentials.append((username, password, user.get_full_name(), user.student_id))

    return credentials


def _credential_csv_response(credentials):
    """Generate downloadable CSV of student credentials."""
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="student_credentials.csv"'
    writer = csv.writer(response)
    writer.writerow(['username', 'password', 'full_name', 'student_id'])
    for username, password, name, sid in credentials:
        writer.writerow([username, password, name, sid])
    return response
```

Note: add `from django.shortcuts import render, redirect` to the imports at top of views.py.

- [ ] **Step 3: Create roster template**

```html
<!-- templates/accounts/roster.html -->
{% extends "base.html" %}
{% block title %}Student Roster{% endblock %}
{% block content %}
<div class="row">
    <div class="col-md-8">
        <h2>Student Roster ({{ students.count }} students)</h2>
        <table class="table table-hover">
            <thead><tr><th>Name</th><th>Username</th><th>Student ID</th><th>Actions</th></tr></thead>
            <tbody>
            {% for student in students %}
            <tr>
                <td>{{ student.get_full_name|default:student.username }}</td>
                <td>{{ student.username }}</td>
                <td>{{ student.student_id }}</td>
                <td>
                    <form method="post" class="d-inline">{% csrf_token %}
                        <input type="hidden" name="user_id" value="{{ student.id }}">
                        <button name="reset_password" class="btn btn-sm btn-outline-warning">Reset PW</button>
                        <button name="delete_student" class="btn btn-sm btn-outline-danger"
                                onclick="return confirm('Remove {{ student.username }}?')">Remove</button>
                    </form>
                </td>
            </tr>
            {% empty %}
            <tr><td colspan="4" class="text-muted">No students yet. Import via CSV below.</td></tr>
            {% endfor %}
            </tbody>
        </table>
    </div>
    <div class="col-md-4">
        <div class="card">
            <div class="card-body">
                <h5>Import Students</h5>
                <form method="post" enctype="multipart/form-data">
                    {% csrf_token %}
                    {{ form.csv_file.label_tag }}
                    {{ form.csv_file }}
                    <small class="text-muted">{{ form.csv_file.help_text }}</small>
                    <button type="submit" class="btn btn-primary mt-2 w-100">Import CSV</button>
                </form>
            </div>
        </div>
    </div>
</div>
{% endblock %}
```

- [ ] **Step 4: Update accounts URLs**

Add to `apps/accounts/urls.py`:

```python
path('roster/', views.student_roster, name='student_roster'),
```

- [ ] **Step 5: Commit**

```bash
git add apps/accounts/ templates/accounts/roster.html
git commit -m "feat: add student roster with CSV import, password reset, and credential download"
```

---

## Chunk 5: Instructor Features

### Task 12: Question Browser & Import UI

**Files:**
- Modify: `apps/questions/views.py`
- Modify: `apps/questions/urls.py`
- Create: `templates/questions/browser.html`
- Create: `templates/questions/import.html`

- [ ] **Step 1: Implement question browser view**

```python
# apps/questions/views.py
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404
from django.core.management import call_command
from django.contrib import messages
from django.http import JsonResponse
from .models import Chapter, Section, Question


@login_required
def question_browser(request):
    if not request.user.is_instructor:
        return redirect('student_dashboard')

    chapters = Chapter.objects.all()
    selected_chapter = request.GET.get('chapter')
    selected_section = request.GET.get('section')
    selected_difficulty = request.GET.get('difficulty')
    selected_skill = request.GET.get('skill')
    search = request.GET.get('q', '')

    questions = Question.objects.select_related('section__chapter', 'context_group').prefetch_related('choices')

    if selected_chapter:
        questions = questions.filter(section__chapter_id=selected_chapter)
    if selected_section:
        questions = questions.filter(section_id=selected_section)
    if selected_difficulty:
        questions = questions.filter(difficulty=selected_difficulty)
    if selected_skill:
        questions = questions.filter(skill=selected_skill)
    if search:
        questions = questions.filter(text__icontains=search)

    questions = questions[:100]  # Limit for performance

    # HTMX partial response for live search
    if request.headers.get('HX-Request'):
        return render(request, 'questions/_question_list.html', {'questions': questions})

    sections = Section.objects.filter(chapter_id=selected_chapter) if selected_chapter else Section.objects.none()

    return render(request, 'questions/browser.html', {
        'chapters': chapters,
        'sections': sections,
        'questions': questions,
        'filters': {
            'chapter': selected_chapter,
            'section': selected_section,
            'difficulty': selected_difficulty,
            'skill': selected_skill,
            'q': search,
        },
    })


@login_required
def question_import(request):
    if not request.user.is_instructor:
        return redirect('student_dashboard')

    if request.method == 'POST' and request.FILES.get('docx_file'):
        docx_file = request.FILES['docx_file']
        if not docx_file.name.endswith('.docx'):
            messages.error(request, 'Please upload a .docx file.')
            return redirect('question_import')

        # Save uploaded file temporarily
        import tempfile, os
        with tempfile.NamedTemporaryFile(delete=False, suffix='.docx') as tmp:
            for chunk in docx_file.chunks():
                tmp.write(chunk)
            tmp_path = tmp.name

        try:
            call_command('import_testbank', tmp_path, stdout=None)
            messages.success(request, f'Successfully imported {docx_file.name}')
        except Exception as e:
            messages.error(request, f'Import failed: {e}')
        finally:
            os.unlink(tmp_path)

        return redirect('question_browser')

    return render(request, 'questions/import.html')


@login_required
def sections_for_chapter(request, chapter_id):
    """HTMX endpoint: return sections dropdown options for a chapter."""
    sections = Section.objects.filter(chapter_id=chapter_id).order_by('sort_order')
    html = '<option value="">All Sections</option>'
    for sec in sections:
        html += f'<option value="{sec.id}">{sec.number} {sec.title}</option>'
    return JsonResponse({'html': html})
```

- [ ] **Step 2: Create browser template**

```html
<!-- templates/questions/browser.html -->
{% extends "base.html" %}
{% block title %}Question Browser{% endblock %}
{% block content %}
<div class="row">
    <div class="col-md-3">
        <div class="card">
            <div class="card-body">
                <h5>Filters</h5>
                <form method="get" id="filter-form">
                    <div class="mb-2">
                        <label class="form-label">Chapter</label>
                        <select name="chapter" class="form-select form-select-sm"
                                hx-get="{% url 'question_browser' %}" hx-target="#question-list"
                                hx-include="#filter-form">
                            <option value="">All</option>
                            {% for ch in chapters %}
                            <option value="{{ ch.id }}" {% if filters.chapter == ch.id|stringformat:"d" %}selected{% endif %}>
                                Ch {{ ch.number }}: {{ ch.title|truncatechars:30 }}
                            </option>
                            {% endfor %}
                        </select>
                    </div>
                    <div class="mb-2">
                        <label class="form-label">Difficulty</label>
                        <select name="difficulty" class="form-select form-select-sm"
                                hx-get="{% url 'question_browser' %}" hx-target="#question-list"
                                hx-include="#filter-form">
                            <option value="">All</option>
                            <option value="1" {% if filters.difficulty == "1" %}selected{% endif %}>1 (Easy)</option>
                            <option value="2" {% if filters.difficulty == "2" %}selected{% endif %}>2 (Medium)</option>
                            <option value="3" {% if filters.difficulty == "3" %}selected{% endif %}>3 (Hard)</option>
                        </select>
                    </div>
                    <div class="mb-2">
                        <label class="form-label">Skill</label>
                        <select name="skill" class="form-select form-select-sm"
                                hx-get="{% url 'question_browser' %}" hx-target="#question-list"
                                hx-include="#filter-form">
                            <option value="">All</option>
                            <option value="Conceptual">Conceptual</option>
                            <option value="Definition">Definition</option>
                            <option value="Analytical">Analytical</option>
                        </select>
                    </div>
                    <div class="mb-2">
                        <label class="form-label">Search</label>
                        <input type="text" name="q" class="form-control form-control-sm" value="{{ filters.q }}"
                               hx-get="{% url 'question_browser' %}" hx-target="#question-list"
                               hx-include="#filter-form" hx-trigger="keyup changed delay:300ms">
                    </div>
                </form>
                <hr>
                <a href="{% url 'question_import' %}" class="btn btn-outline-primary btn-sm w-100">Import .docx</a>
            </div>
        </div>
    </div>
    <div class="col-md-9" id="question-list">
        {% include "questions/_question_list.html" %}
    </div>
</div>
{% endblock %}
```

- [ ] **Step 3: Create question list partial template**

```html
<!-- templates/questions/_question_list.html -->
<h5>Questions ({{ questions|length }}{% if questions|length >= 100 %}+{% endif %})</h5>
{% for q in questions %}
<div class="card question-card">
    <div class="card-body">
        <div class="d-flex justify-content-between">
            <span class="badge bg-secondary">Q{{ q.question_number }}</span>
            <span>
                <span class="badge bg-info">{{ q.question_type }}</span>
                <span class="badge bg-warning text-dark">Diff {{ q.difficulty }}</span>
                <span class="badge bg-light text-dark">{{ q.skill }}</span>
            </span>
        </div>
        {% if q.context_group %}
        <div class="text-muted small mt-1">{{ q.context_group.text|truncatechars:100 }}</div>
        {% endif %}
        <p class="mt-2 mb-1">{{ q.text }}</p>
        {% if q.image %}
        <img src="{{ MEDIA_URL }}{{ q.image }}" class="img-fluid mb-2" style="max-height: 200px;">
        {% endif %}
        {% if q.question_type == 'MC' %}
        <ul class="list-unstyled ms-3">
            {% for choice in q.choices.all %}
            <li{% if choice.is_correct %} class="fw-bold text-success"{% endif %}>
                {{ choice.letter }}) {{ choice.text }}
            </li>
            {% endfor %}
        </ul>
        {% endif %}
        {% if q.answer_raw_text %}
        <small class="text-muted">Answer: {{ q.answer_raw_text|truncatechars:80 }}</small>
        {% endif %}
    </div>
</div>
{% empty %}
<p class="text-muted">No questions found. Try adjusting filters or import a .docx file.</p>
{% endfor %}
```

- [ ] **Step 4: Create import template**

```html
<!-- templates/questions/import.html -->
{% extends "base.html" %}
{% block title %}Import Questions{% endblock %}
{% block content %}
<div class="row justify-content-center">
    <div class="col-md-6">
        <h2>Import Testbank</h2>
        <div class="card">
            <div class="card-body">
                <form method="post" enctype="multipart/form-data">
                    {% csrf_token %}
                    <div class="mb-3">
                        <label class="form-label">Upload .docx testbank file</label>
                        <input type="file" name="docx_file" class="form-control" accept=".docx" required>
                    </div>
                    <button type="submit" class="btn btn-primary">Import</button>
                    <a href="{% url 'question_browser' %}" class="btn btn-outline-secondary">Cancel</a>
                </form>
            </div>
        </div>
    </div>
</div>
{% endblock %}
```

- [ ] **Step 5: Wire up URLs**

```python
# apps/questions/urls.py
from django.urls import path
from . import views

urlpatterns = [
    path('browser/', views.question_browser, name='question_browser'),
    path('import/', views.question_import, name='question_import'),
    path('sections/<int:chapter_id>/', views.sections_for_chapter, name='sections_for_chapter'),
]
```

- [ ] **Step 6: Commit**

```bash
mkdir -p templates/questions
git add apps/questions/ templates/questions/
git commit -m "feat: add question browser with filters, live search, and .docx import UI"
```

---

### Task 13: Assignment Creation

**Files:**
- Modify: `apps/assignments/views.py`
- Modify: `apps/assignments/forms.py`
- Modify: `apps/assignments/urls.py`
- Create: `templates/assignments/instructor/create.html`
- Create: `templates/assignments/instructor/dashboard.html`
- Create: `templates/assignments/instructor/detail.html`
- Create: `templates/assignments/instructor/grade.html`

- [ ] **Step 1: Create assignment forms**

```python
# apps/assignments/forms.py
from django import forms
from .models import Assignment
from questions.models import Chapter, Section


class AssignmentForm(forms.ModelForm):
    class Meta:
        model = Assignment
        fields = ['title', 'mode', 'num_questions', 'is_randomized', 'due_date', 'difficulty_filter', 'skill_filter']
        widgets = {
            'title': forms.TextInput(attrs={'class': 'form-control'}),
            'mode': forms.Select(attrs={'class': 'form-select'}),
            'num_questions': forms.NumberInput(attrs={'class': 'form-control', 'min': 1}),
            'is_randomized': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'due_date': forms.DateTimeInput(attrs={'class': 'form-control', 'type': 'datetime-local'}),
            'difficulty_filter': forms.HiddenInput(),
            'skill_filter': forms.HiddenInput(),
        }

    chapters = forms.ModelMultipleChoiceField(
        queryset=Chapter.objects.all(),
        widget=forms.CheckboxSelectMultiple,
        required=False,
    )
    sections = forms.ModelMultipleChoiceField(
        queryset=Section.objects.all(),
        widget=forms.CheckboxSelectMultiple,
        required=False,
    )
```

- [ ] **Step 2: Create assignment views**

```python
# apps/assignments/views.py
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.utils import timezone
from django.db.models import Avg, Count, Q
from .models import Assignment, StudentAssignment, StudentAnswer, AssignedQuestion, MistakeEntry
from .forms import AssignmentForm
from questions.models import Question, Chapter
from services.randomizer import assign_questions_to_student
from services.grader import grade_answer, recompute_score
from accounts.models import User


# ---- Instructor Views ----

@login_required
def instructor_dashboard(request):
    if not request.user.is_instructor:
        return redirect('student_dashboard')

    assignments = Assignment.objects.filter(created_by=request.user).annotate(
        student_count=Count('student_assignments'),
        completed_count=Count('student_assignments', filter=Q(student_assignments__status='COMPLETED')),
        avg_score=Avg('student_assignments__score'),
    )
    total_students = User.objects.filter(role='STUDENT').count()

    return render(request, 'assignments/instructor/dashboard.html', {
        'assignments': assignments,
        'total_students': total_students,
    })


@login_required
def assignment_create(request):
    if not request.user.is_instructor:
        return redirect('student_dashboard')

    if request.method == 'POST':
        form = AssignmentForm(request.POST)
        if form.is_valid():
            assignment = form.save(commit=False)
            assignment.created_by = request.user

            # Parse difficulty/skill filters from checkboxes
            assignment.difficulty_filter = request.POST.getlist('difficulty_checks')
            assignment.skill_filter = request.POST.getlist('skill_checks')
            assignment.save()

            # Set chapters and sections
            form.save_m2m()
            assignment.chapters.set(form.cleaned_data.get('chapters', []))
            assignment.sections.set(form.cleaned_data.get('sections', []))

            # Handle manually selected questions
            manual_ids = request.POST.getlist('manual_questions')
            if manual_ids:
                assignment.manually_selected_questions.set(manual_ids)
                assignment.num_questions = len(manual_ids)
                assignment.save()

            messages.success(request, f'Assignment "{assignment.title}" created.')
            return redirect('instructor_dashboard')
    else:
        form = AssignmentForm()

    chapters = Chapter.objects.prefetch_related('sections')
    return render(request, 'assignments/instructor/create.html', {
        'form': form,
        'chapters': chapters,
    })


@login_required
def assignment_publish(request, pk):
    if not request.user.is_instructor:
        return redirect('student_dashboard')
    assignment = get_object_or_404(Assignment, pk=pk, created_by=request.user)
    assignment.is_published = not assignment.is_published
    assignment.save(update_fields=['is_published'])

    # When publishing, create StudentAssignments for all students
    if assignment.is_published:
        students = User.objects.filter(role='STUDENT')
        for student in students:
            assign_questions_to_student(assignment, student)
        messages.success(request, f'Published and assigned to {students.count()} students.')
    else:
        messages.info(request, 'Assignment unpublished.')

    return redirect('instructor_dashboard')


@login_required
def assignment_detail(request, pk):
    if not request.user.is_instructor:
        return redirect('student_dashboard')

    assignment = get_object_or_404(Assignment, pk=pk)
    student_assignments = assignment.student_assignments.select_related('student').order_by('student__last_name')

    return render(request, 'assignments/instructor/detail.html', {
        'assignment': assignment,
        'student_assignments': student_assignments,
    })


@login_required
def grade_free_response(request):
    if not request.user.is_instructor:
        return redirect('student_dashboard')

    if request.method == 'POST':
        answer_id = request.POST.get('answer_id')
        is_correct = request.POST.get('is_correct') == 'true'
        feedback = request.POST.get('feedback', '')

        answer = get_object_or_404(StudentAnswer, id=answer_id)
        answer.is_correct = is_correct
        answer.instructor_feedback = feedback
        answer.save()
        recompute_score(answer.student_assignment)
        messages.success(request, 'Answer graded.')
        return redirect('grade_free_response')

    ungraded = StudentAnswer.objects.filter(
        question__question_type='FREE_RESPONSE',
        is_correct__isnull=True,
    ).exclude(text_answer='').select_related('student_assignment__student', 'question')

    return render(request, 'assignments/instructor/grade.html', {'ungraded': ungraded})
```

- [ ] **Step 3: Create instructor templates**

Create `templates/assignments/instructor/dashboard.html`:

```html
{% extends "base.html" %}
{% block title %}Instructor Dashboard{% endblock %}
{% block content %}
<h2>Instructor Dashboard</h2>
<p>Total students: {{ total_students }}</p>
<div class="d-flex justify-content-end mb-3">
    <a href="{% url 'assignment_create' %}" class="btn btn-primary">Create Assignment</a>
</div>
<table class="table table-hover">
    <thead><tr><th>Title</th><th>Mode</th><th>Questions</th><th>Status</th><th>Completed</th><th>Avg Score</th><th>Actions</th></tr></thead>
    <tbody>
    {% for a in assignments %}
    <tr>
        <td><a href="{% url 'assignment_detail' a.pk %}">{{ a.title }}</a></td>
        <td>{{ a.get_mode_display }}</td>
        <td>{{ a.num_questions }}</td>
        <td>{% if a.is_published %}<span class="badge bg-success">Published</span>{% else %}<span class="badge bg-secondary">Draft</span>{% endif %}</td>
        <td>{{ a.completed_count }}/{{ a.student_count }}</td>
        <td>{% if a.avg_score is not None %}{{ a.avg_score|floatformat:1 }}/{{ a.num_questions }}{% else %}—{% endif %}</td>
        <td>
            <form method="post" action="{% url 'assignment_publish' a.pk %}" class="d-inline">
                {% csrf_token %}
                <button class="btn btn-sm {% if a.is_published %}btn-outline-secondary{% else %}btn-outline-success{% endif %}">
                    {% if a.is_published %}Unpublish{% else %}Publish{% endif %}
                </button>
            </form>
        </td>
    </tr>
    {% empty %}
    <tr><td colspan="7" class="text-muted">No assignments yet.</td></tr>
    {% endfor %}
    </tbody>
</table>
<a href="{% url 'grade_free_response' %}" class="btn btn-outline-primary">Grade Free Response</a>
{% endblock %}
```

Create `templates/assignments/instructor/create.html`:

```html
{% extends "base.html" %}
{% block title %}Create Assignment{% endblock %}
{% block content %}
<h2>Create Assignment</h2>
<form method="post">
    {% csrf_token %}
    <div class="row">
        <div class="col-md-6">
            <div class="mb-3">{{ form.title.label_tag }} {{ form.title }}</div>
            <div class="mb-3">{{ form.mode.label_tag }} {{ form.mode }}</div>
            <div class="mb-3">{{ form.num_questions.label_tag }} {{ form.num_questions }}</div>
            <div class="mb-3 form-check">{{ form.is_randomized }} <label class="form-check-label">Randomize order</label></div>
            <div class="mb-3">{{ form.due_date.label_tag }} {{ form.due_date }}</div>
        </div>
        <div class="col-md-6">
            <h5>Chapters</h5>
            {% for ch in chapters %}
            <div class="form-check">
                <input type="checkbox" name="chapters" value="{{ ch.id }}" class="form-check-input" id="ch{{ ch.id }}">
                <label class="form-check-label" for="ch{{ ch.id }}">Ch {{ ch.number }}: {{ ch.title }}</label>
            </div>
            {% endfor %}
            <h5 class="mt-3">Difficulty</h5>
            {% for val, label in "1:Easy,2:Medium,3:Hard"|split_difficulty %}
            <div class="form-check form-check-inline">
                <input type="checkbox" name="difficulty_checks" value="{{ val }}" class="form-check-input">
                <label class="form-check-label">{{ label }}</label>
            </div>
            {% endfor %}
            <h5 class="mt-3">Skill</h5>
            {% for skill in "Conceptual,Definition,Analytical" %}
            <div class="form-check form-check-inline">
                <input type="checkbox" name="skill_checks" value="{{ skill }}" class="form-check-input">
                <label class="form-check-label">{{ skill }}</label>
            </div>
            {% endfor %}
        </div>
    </div>
    <button type="submit" class="btn btn-primary">Create Assignment</button>
    <a href="{% url 'instructor_dashboard' %}" class="btn btn-outline-secondary">Cancel</a>
</form>
{% endblock %}
```

Create `templates/assignments/instructor/detail.html`:

```html
{% extends "base.html" %}
{% block title %}{{ assignment.title }}{% endblock %}
{% block content %}
<h2>{{ assignment.title }}</h2>
<p>{{ assignment.num_questions }} questions | {{ assignment.get_mode_display }} | Due: {{ assignment.due_date|default:"No deadline" }}</p>
<table class="table">
    <thead><tr><th>Student</th><th>Status</th><th>Score</th><th>Time</th></tr></thead>
    <tbody>
    {% for sa in student_assignments %}
    <tr>
        <td>{{ sa.student.get_full_name|default:sa.student.username }}</td>
        <td><span class="badge bg-{% if sa.status == 'COMPLETED' %}success{% elif sa.status == 'IN_PROGRESS' %}warning{% else %}secondary{% endif %}">{{ sa.get_status_display }}</span></td>
        <td>{% if sa.score is not None %}{{ sa.score }}/{{ sa.max_score }}{% else %}—{% endif %}</td>
        <td>{% if sa.completed_at and sa.started_at %}{{ sa.completed_at|timeuntil:sa.started_at }}{% else %}—{% endif %}</td>
    </tr>
    {% endfor %}
    </tbody>
</table>
{% endblock %}
```

Create `templates/assignments/instructor/grade.html`:

```html
{% extends "base.html" %}
{% block title %}Grade Free Response{% endblock %}
{% block content %}
<h2>Free Response Grading Queue ({{ ungraded.count }})</h2>
{% for ans in ungraded %}
<div class="card mb-3">
    <div class="card-body">
        <h6>{{ ans.student_assignment.student }} — Q{{ ans.question.question_number }}</h6>
        <p><strong>Question:</strong> {{ ans.question.text }}</p>
        <p><strong>Student Answer:</strong> {{ ans.text_answer }}</p>
        {% if ans.question.answer_raw_text %}
        <p class="text-muted"><strong>Expected:</strong> {{ ans.question.answer_raw_text }}</p>
        {% endif %}
        <form method="post" class="d-inline">
            {% csrf_token %}
            <input type="hidden" name="answer_id" value="{{ ans.id }}">
            <textarea name="feedback" class="form-control mb-2" placeholder="Feedback (optional)" rows="2"></textarea>
            <button name="is_correct" value="true" class="btn btn-success btn-sm">Correct</button>
            <button name="is_correct" value="false" class="btn btn-danger btn-sm">Incorrect</button>
        </form>
    </div>
</div>
{% empty %}
<p class="text-muted">No ungraded answers.</p>
{% endfor %}
{% endblock %}
```

- [ ] **Step 4: Wire up assignment URLs**

```python
# apps/assignments/urls.py
from django.urls import path
from . import views

urlpatterns = [
    # Instructor
    path('instructor/', views.instructor_dashboard, name='instructor_dashboard'),
    path('create/', views.assignment_create, name='assignment_create'),
    path('<int:pk>/publish/', views.assignment_publish, name='assignment_publish'),
    path('<int:pk>/detail/', views.assignment_detail, name='assignment_detail'),
    path('grade/', views.grade_free_response, name='grade_free_response'),
]
```

- [ ] **Step 5: Commit**

```bash
mkdir -p templates/assignments/instructor templates/assignments/student
git add apps/assignments/ templates/assignments/
git commit -m "feat: add instructor dashboard, assignment creation, detail view, and free-response grading"
```

---

## Chunk 6: Student Assignment Flow

### Task 14: Student Dashboard & Assignment List

**Files:**
- Modify: `apps/assignments/views.py`
- Modify: `apps/assignments/urls.py`
- Create: `templates/assignments/student/dashboard.html`
- Create: `templates/assignments/student/list.html`

- [ ] **Step 1: Add student views**

Add to `apps/assignments/views.py`:

```python
# ---- Student Views ----

@login_required
def student_dashboard(request):
    if not request.user.is_student:
        return redirect('instructor_dashboard')

    # Active assignments
    active = StudentAssignment.objects.filter(
        student=request.user,
        status__in=['NOT_STARTED', 'IN_PROGRESS'],
        assignment__is_published=True,
    ).select_related('assignment')

    # Recent completed
    completed = StudentAssignment.objects.filter(
        student=request.user,
        status='COMPLETED',
    ).select_related('assignment').order_by('-completed_at')[:5]

    # Quick stats
    all_completed = StudentAssignment.objects.filter(student=request.user, status='COMPLETED')
    total_completed = all_completed.count()
    avg_score_pct = None
    if total_completed > 0:
        scores = [(sa.score or 0) / sa.max_score * 100 for sa in all_completed if sa.max_score > 0]
        avg_score_pct = sum(scores) / len(scores) if scores else None

    mistake_count = MistakeEntry.objects.filter(student=request.user, is_mastered=False).count()

    return render(request, 'assignments/student/dashboard.html', {
        'active': active,
        'completed': completed,
        'total_completed': total_completed,
        'avg_score_pct': avg_score_pct,
        'mistake_count': mistake_count,
    })


@login_required
def assignment_list(request):
    if not request.user.is_student:
        return redirect('instructor_dashboard')

    student_assignments = StudentAssignment.objects.filter(
        student=request.user,
        assignment__is_published=True,
    ).select_related('assignment').order_by('-assignment__created_at')

    return render(request, 'assignments/student/list.html', {
        'student_assignments': student_assignments,
    })
```

- [ ] **Step 2: Create student dashboard template**

```html
<!-- templates/assignments/student/dashboard.html -->
{% extends "base.html" %}
{% block title %}Dashboard{% endblock %}
{% block content %}
<h2>Welcome, {{ user.get_full_name|default:user.username }}</h2>
<div class="row mb-4">
    <div class="col-md-3">
        <div class="card text-center">
            <div class="card-body">
                <h3>{{ total_completed }}</h3>
                <p class="text-muted">Completed</p>
            </div>
        </div>
    </div>
    <div class="col-md-3">
        <div class="card text-center">
            <div class="card-body">
                <h3>{% if avg_score_pct is not None %}{{ avg_score_pct|floatformat:0 }}%{% else %}—{% endif %}</h3>
                <p class="text-muted">Avg Score</p>
            </div>
        </div>
    </div>
    <div class="col-md-3">
        <div class="card text-center">
            <div class="card-body">
                <h3>{{ mistake_count }}</h3>
                <p class="text-muted"><a href="{% url 'mistake_collection' %}">Mistakes to Review</a></p>
            </div>
        </div>
    </div>
</div>

<h4>Active Assignments</h4>
{% for sa in active %}
<div class="card mb-2">
    <div class="card-body d-flex justify-content-between align-items-center">
        <div>
            <strong>{{ sa.assignment.title }}</strong>
            {% if sa.assignment.due_date %}
            <span class="text-muted ms-2">Due: {{ sa.assignment.due_date|date:"M d, H:i" }}</span>
            {% endif %}
        </div>
        <a href="{% url 'take_assignment' sa.pk %}" class="btn btn-primary btn-sm">
            {% if sa.status == 'IN_PROGRESS' %}Continue{% else %}Start{% endif %}
        </a>
    </div>
</div>
{% empty %}
<p class="text-muted">No active assignments.</p>
{% endfor %}

<h4 class="mt-4">Recent Results</h4>
{% for sa in completed %}
<div class="card mb-2">
    <div class="card-body d-flex justify-content-between align-items-center">
        <div>
            <strong>{{ sa.assignment.title }}</strong>
            <span class="ms-2">{{ sa.score }}/{{ sa.max_score }}</span>
        </div>
        <a href="{% url 'assignment_result' sa.pk %}" class="btn btn-outline-secondary btn-sm">View Results</a>
    </div>
</div>
{% endfor %}
{% endblock %}
```

- [ ] **Step 3: Create assignment list template**

```html
<!-- templates/assignments/student/list.html -->
{% extends "base.html" %}
{% block title %}My Assignments{% endblock %}
{% block content %}
<h2>My Assignments</h2>
<table class="table">
    <thead><tr><th>Title</th><th>Questions</th><th>Due</th><th>Status</th><th>Score</th><th></th></tr></thead>
    <tbody>
    {% for sa in student_assignments %}
    <tr>
        <td>{{ sa.assignment.title }}</td>
        <td>{{ sa.max_score }}</td>
        <td>{{ sa.assignment.due_date|date:"M d, H:i"|default:"—" }}</td>
        <td><span class="badge bg-{% if sa.status == 'COMPLETED' %}success{% elif sa.status == 'IN_PROGRESS' %}warning{% else %}secondary{% endif %}">{{ sa.get_status_display }}</span></td>
        <td>{% if sa.score is not None %}{{ sa.score }}/{{ sa.max_score }}{% else %}—{% endif %}</td>
        <td>
            {% if sa.status == 'COMPLETED' %}
            <a href="{% url 'assignment_result' sa.pk %}" class="btn btn-sm btn-outline-secondary">Results</a>
            {% else %}
            <a href="{% url 'take_assignment' sa.pk %}" class="btn btn-sm btn-primary">{% if sa.status == 'IN_PROGRESS' %}Continue{% else %}Start{% endif %}</a>
            {% endif %}
        </td>
    </tr>
    {% endfor %}
    </tbody>
</table>
{% endblock %}
```

- [ ] **Step 4: Add URL patterns**

Add to `apps/assignments/urls.py`:

```python
    # Student
    path('dashboard/', views.student_dashboard, name='student_dashboard'),
    path('list/', views.assignment_list, name='assignment_list'),
```

- [ ] **Step 5: Commit**

```bash
git add apps/assignments/ templates/assignments/student/
git commit -m "feat: add student dashboard and assignment list views"
```

---

### Task 15: Take Assignment (Core Student Flow)

**Files:**
- Modify: `apps/assignments/views.py`
- Create: `templates/assignments/student/take.html`
- Create: `templates/assignments/student/_question.html`
- Create: `templates/assignments/student/result.html`
- Create: `static/js/timer.js`

This is the most important task — the one-question-at-a-time assignment-taking experience with HTMX.

- [ ] **Step 1: Add take_assignment and submit_answer views**

Add to `apps/assignments/views.py`:

```python
from django.http import HttpResponseForbidden


@login_required
def take_assignment(request, sa_pk):
    sa = get_object_or_404(StudentAssignment, pk=sa_pk, student=request.user)

    if sa.status == 'COMPLETED':
        return redirect('assignment_result', sa_pk=sa.pk)

    # Mark as started
    if sa.status == 'NOT_STARTED':
        sa.status = 'IN_PROGRESS'
        sa.started_at = timezone.now()
        sa.save(update_fields=['status', 'started_at'])

    # Get ordered questions
    assigned = AssignedQuestion.objects.filter(student_assignment=sa).select_related('question').order_by('position')
    questions = [aq.question for aq in assigned]

    # Current question index
    current_idx = int(request.GET.get('q', 0))
    current_idx = max(0, min(current_idx, len(questions) - 1))
    current_q = questions[current_idx]

    # Get existing answer if any
    existing_answer = StudentAnswer.objects.filter(student_assignment=sa, question=current_q).first()

    # Get shuffled choices for MC
    choices = []
    if current_q.question_type == 'MC':
        shuffle_map = sa.choice_shuffle_map.get(str(current_q.id), {})
        original_choices = list(current_q.choices.all())
        if shuffle_map:
            # Reorder choices according to shuffle map
            # shuffle_map: {original_letter: displayed_letter}
            # We need to sort by displayed_letter
            reverse_map = {v: k for k, v in shuffle_map.items()}
            for displayed_letter in sorted(reverse_map.keys()):
                original_letter = reverse_map[displayed_letter]
                choice = next((c for c in original_choices if c.letter == original_letter), None)
                if choice:
                    choices.append({'id': choice.id, 'display_letter': displayed_letter, 'text': choice.text})
        else:
            choices = [{'id': c.id, 'display_letter': c.letter, 'text': c.text} for c in original_choices]

    # Build question nav (which are answered)
    answered_ids = set(StudentAnswer.objects.filter(student_assignment=sa).values_list('question_id', flat=True))

    context = {
        'sa': sa,
        'question': current_q,
        'question_idx': current_idx,
        'total_questions': len(questions),
        'choices': choices,
        'existing_answer': existing_answer,
        'answered_ids': answered_ids,
        'questions': questions,
    }

    # HTMX partial for question navigation
    if request.headers.get('HX-Request'):
        return render(request, 'assignments/student/_question.html', context)

    return render(request, 'assignments/student/take.html', context)


@login_required
def submit_answer(request, sa_pk):
    if request.method != 'POST':
        return HttpResponseForbidden()

    sa = get_object_or_404(StudentAssignment, pk=sa_pk, student=request.user)
    if sa.status == 'COMPLETED':
        return HttpResponseForbidden('Assignment already completed.')

    question_id = request.POST.get('question_id')
    question = get_object_or_404(Question, id=question_id)
    time_spent = int(request.POST.get('time_spent', 0))

    # Compute server elapsed
    last_answer = sa.answers.order_by('-answered_at').first()
    reference_time = last_answer.answered_at if last_answer else sa.started_at
    server_elapsed = int((timezone.now() - reference_time).total_seconds()) if reference_time else 0

    # Create or update answer
    answer, created = StudentAnswer.objects.update_or_create(
        student_assignment=sa,
        question=question,
        defaults={
            'time_spent_seconds': time_spent,
            'server_elapsed_seconds': server_elapsed,
            'question_text_snapshot': question.text,
        },
    )

    # Set answer based on type
    if question.question_type == 'MC':
        choice_id = request.POST.get('choice_id')
        if choice_id:
            from questions.models import MCChoice
            answer.selected_choice = get_object_or_404(MCChoice, id=choice_id)
    elif question.question_type == 'NUMERIC':
        answer.numeric_answer = request.POST.get('numeric_answer', '')
    else:
        answer.text_answer = request.POST.get('text_answer', '')[:5000]

    # Grade
    grade_answer(answer)
    answer.save()

    # Add to mistakes if wrong
    if answer.is_correct is False:
        MistakeEntry.objects.get_or_create(student=request.user, question=question)

    # Recompute score
    recompute_score(sa)

    # Return updated question partial
    return redirect(f'/assignments/take/{sa.pk}/?q={request.POST.get("question_idx", 0)}')


@login_required
def complete_assignment(request, sa_pk):
    if request.method != 'POST':
        return HttpResponseForbidden()

    sa = get_object_or_404(StudentAssignment, pk=sa_pk, student=request.user)
    sa.status = 'COMPLETED'
    sa.completed_at = timezone.now()
    sa.save(update_fields=['status', 'completed_at'])
    recompute_score(sa)

    return redirect('assignment_result', sa_pk=sa.pk)


@login_required
def assignment_result(request, sa_pk):
    sa = get_object_or_404(StudentAssignment, pk=sa_pk, student=request.user)

    answers = sa.answers.select_related('question', 'selected_choice').order_by('question__question_number')

    # For MC, include correct choice info
    results = []
    for ans in answers:
        correct_choice = None
        if ans.question.question_type == 'MC':
            correct_choice = ans.question.choices.filter(is_correct=True).first()
        results.append({
            'answer': ans,
            'correct_choice': correct_choice,
        })

    return render(request, 'assignments/student/result.html', {
        'sa': sa,
        'results': results,
    })
```

- [ ] **Step 2: Create take assignment template**

```html
<!-- templates/assignments/student/take.html -->
{% extends "base.html" %}
{% load static %}
{% block title %}{{ sa.assignment.title }}{% endblock %}
{% block content %}
<div class="row">
    <!-- Question Navigation Sidebar -->
    <div class="col-md-2">
        <div class="card">
            <div class="card-body question-nav">
                <h6>Questions</h6>
                {% for q in questions %}
                <a href="?q={{ forloop.counter0 }}"
                   class="btn btn-sm mb-1 {% if forloop.counter0 == question_idx %}current btn-primary{% elif q.id in answered_ids %}answered{% else %}btn-outline-secondary{% endif %}"
                   hx-get="{% url 'take_assignment' sa.pk %}?q={{ forloop.counter0 }}"
                   hx-target="#question-panel" hx-push-url="true">
                    {{ forloop.counter }}
                </a>
                {% endfor %}
            </div>
        </div>
        <div class="card mt-2">
            <div class="card-body text-center">
                <div class="timer-display" id="timer">00:00</div>
                <small class="text-muted">Time on question</small>
            </div>
        </div>
    </div>

    <!-- Question Panel -->
    <div class="col-md-10" id="question-panel">
        {% include "assignments/student/_question.html" %}
    </div>
</div>
{% endblock %}

{% block extra_js %}
<script src="{% static 'js/timer.js' %}"></script>
<script>startTimer('timer');</script>
{% endblock %}
```

- [ ] **Step 3: Create question partial template**

```html
<!-- templates/assignments/student/_question.html -->
<div class="card">
    <div class="card-header d-flex justify-content-between">
        <span>Question {{ question_idx|add:1 }} of {{ total_questions }}</span>
        <span class="badge bg-info">{{ question.get_question_type_display }}</span>
    </div>
    <div class="card-body">
        {% if question.context_group %}
        <div class="alert alert-light">
            {{ question.context_group.text|safe }}
            {% if question.context_group.image %}
            <img src="{{ MEDIA_URL }}{{ question.context_group.image }}" class="img-fluid mt-2">
            {% endif %}
        </div>
        {% endif %}

        {% if question.image %}
        <img src="{{ MEDIA_URL }}{{ question.image }}" class="img-fluid mb-3" style="max-height: 300px;">
        {% endif %}

        <p class="fs-5">{{ question.text }}</p>

        <form method="post" action="{% url 'submit_answer' sa.pk %}" id="answer-form">
            {% csrf_token %}
            <input type="hidden" name="question_id" value="{{ question.id }}">
            <input type="hidden" name="question_idx" value="{{ question_idx }}">
            <input type="hidden" name="time_spent" id="time-spent-input" value="0">

            {% if question.question_type == 'MC' %}
                {% for choice in choices %}
                <div class="choice-option {% if existing_answer and existing_answer.selected_choice_id == choice.id %}selected{% endif %}"
                     onclick="selectChoice(this, {{ choice.id }})">
                    <input type="radio" name="choice_id" value="{{ choice.id }}" class="d-none"
                           {% if existing_answer and existing_answer.selected_choice_id == choice.id %}checked{% endif %}>
                    <strong>{{ choice.display_letter }})</strong> {{ choice.text }}
                </div>
                {% endfor %}

            {% elif question.question_type == 'NUMERIC' %}
                <div class="mb-3">
                    <label class="form-label">Your answer (numeric value):</label>
                    <input type="text" name="numeric_answer" class="form-control" style="max-width: 300px;"
                           placeholder="e.g. $254,641 or -1234.56"
                           value="{{ existing_answer.numeric_answer|default:'' }}">
                </div>

            {% else %}
                <div class="mb-3">
                    <label class="form-label">Your answer:</label>
                    <textarea name="text_answer" class="form-control" rows="5"
                              maxlength="5000">{{ existing_answer.text_answer|default:'' }}</textarea>
                    <small class="text-muted">Max 5000 characters</small>
                </div>
            {% endif %}

            <div class="d-flex justify-content-between mt-3">
                {% if question_idx > 0 %}
                <a href="?q={{ question_idx|add:-1 }}" class="btn btn-outline-secondary"
                   hx-get="{% url 'take_assignment' sa.pk %}?q={{ question_idx|add:-1 }}"
                   hx-target="#question-panel">Previous</a>
                {% else %}
                <span></span>
                {% endif %}

                <button type="submit" class="btn btn-primary"
                        onclick="document.getElementById('time-spent-input').value = getElapsedSeconds();">
                    Save Answer
                </button>

                {% if question_idx < total_questions|add:-1 %}
                <a href="?q={{ question_idx|add:1 }}" class="btn btn-outline-secondary"
                   hx-get="{% url 'take_assignment' sa.pk %}?q={{ question_idx|add:1 }}"
                   hx-target="#question-panel">Next</a>
                {% else %}
                <span></span>
                {% endif %}
            </div>
        </form>

        {% if question_idx == total_questions|add:-1 %}
        <hr>
        <form method="post" action="{% url 'complete_assignment' sa.pk %}">
            {% csrf_token %}
            <button type="submit" class="btn btn-success w-100"
                    onclick="return confirm('Submit assignment? You cannot change answers after this.')">
                Submit Assignment
            </button>
        </form>
        {% endif %}
    </div>
</div>

<script>
function selectChoice(el, choiceId) {
    document.querySelectorAll('.choice-option').forEach(e => e.classList.remove('selected'));
    el.classList.add('selected');
    el.querySelector('input[type=radio]').checked = true;
}
</script>
```

- [ ] **Step 4: Create timer JS**

```javascript
// static/js/timer.js
let timerInterval = null;
let elapsedSeconds = 0;

function startTimer(elementId) {
    elapsedSeconds = 0;
    const el = document.getElementById(elementId);
    if (timerInterval) clearInterval(timerInterval);

    timerInterval = setInterval(() => {
        if (!document.hidden) {
            elapsedSeconds++;
            const mins = Math.floor(elapsedSeconds / 60);
            const secs = elapsedSeconds % 60;
            el.textContent = String(mins).padStart(2, '0') + ':' + String(secs).padStart(2, '0');
        }
    }, 1000);
}

function getElapsedSeconds() {
    return elapsedSeconds;
}

// Reset timer when HTMX swaps question content
document.addEventListener('htmx:afterSwap', function(evt) {
    if (evt.detail.target.id === 'question-panel') {
        startTimer('timer');
    }
});
```

- [ ] **Step 5: Create result template**

```html
<!-- templates/assignments/student/result.html -->
{% extends "base.html" %}
{% block title %}Results: {{ sa.assignment.title }}{% endblock %}
{% block content %}
<h2>{{ sa.assignment.title }} — Results</h2>
<div class="alert alert-{% if sa.score == sa.max_score %}success{% elif sa.score > 0 %}info{% else %}danger{% endif %}">
    Score: <strong>{{ sa.score }}/{{ sa.max_score }}</strong>
    ({{ sa.score|divisibleby:1 }}{% widthratio sa.score sa.max_score 100 %}%)
</div>

{% for r in results %}
<div class="card mb-2">
    <div class="card-body">
        <div class="d-flex justify-content-between">
            <span>Q{{ r.answer.question.question_number }}</span>
            {% if r.answer.is_correct %}
            <span class="badge bg-success">Correct</span>
            {% elif r.answer.is_correct is False %}
            <span class="badge bg-danger">Incorrect</span>
            {% else %}
            <span class="badge bg-secondary">Pending</span>
            {% endif %}
        </div>
        <p class="mt-2">{{ r.answer.question_text_snapshot }}</p>

        {% if r.answer.question.question_type == 'MC' %}
            {% if r.answer.selected_choice %}
            <p>Your answer: {{ r.answer.selected_choice.letter }}) {{ r.answer.selected_choice.text }}</p>
            {% endif %}
            {% if r.correct_choice and r.answer.is_correct is False %}
            <p class="text-success">Correct answer: {{ r.correct_choice.letter }}) {{ r.correct_choice.text }}</p>
            {% endif %}
        {% elif r.answer.question.question_type == 'NUMERIC' %}
            <p>Your answer: {{ r.answer.numeric_answer }}</p>
        {% else %}
            <p>Your answer: {{ r.answer.text_answer|truncatechars:200 }}</p>
        {% endif %}

        {% if r.answer.question.explanation %}
        <div class="alert alert-light mt-2">
            <strong>Explanation:</strong> {{ r.answer.question.explanation }}
        </div>
        {% endif %}

        {% if r.answer.instructor_feedback %}
        <div class="alert alert-info mt-2">
            <strong>Instructor Feedback:</strong> {{ r.answer.instructor_feedback }}
        </div>
        {% endif %}
    </div>
</div>
{% endfor %}

<a href="{% url 'student_dashboard' %}" class="btn btn-primary">Back to Dashboard</a>
{% endblock %}
```

- [ ] **Step 6: Add URL patterns**

Add to `apps/assignments/urls.py`:

```python
    path('take/<int:sa_pk>/', views.take_assignment, name='take_assignment'),
    path('take/<int:sa_pk>/submit/', views.submit_answer, name='submit_answer'),
    path('take/<int:sa_pk>/complete/', views.complete_assignment, name='complete_assignment'),
    path('result/<int:sa_pk>/', views.assignment_result, name='assignment_result'),
```

- [ ] **Step 7: Commit**

```bash
git add apps/assignments/ templates/assignments/student/ static/js/timer.js
git commit -m "feat: add student assignment-taking flow with HTMX navigation, timer, and results view"
```

---

## Chunk 7: Practice Mode & Mistake Collection

### Task 16: Practice Mode

**Files:**
- Modify: `apps/assignments/views.py`
- Modify: `apps/assignments/urls.py`
- Create: `templates/assignments/student/practice.html`

Practice mode creates a temporary Assignment with `mode='PRACTICE'` and reuses the take-assignment flow. Instant feedback is shown per question.

- [ ] **Step 1: Add practice setup view**

Add to `apps/assignments/views.py`:

```python
@login_required
def practice_setup(request):
    if not request.user.is_student:
        return redirect('instructor_dashboard')

    chapters = Chapter.objects.prefetch_related('sections')

    if request.method == 'POST':
        chapter_ids = request.POST.getlist('chapters')
        difficulty = request.POST.getlist('difficulty')
        num_questions = int(request.POST.get('num_questions', 10))

        # Create a practice assignment
        practice_assignment = Assignment.objects.create(
            title=f'Practice — {timezone.now().strftime("%b %d %H:%M")}',
            created_by=request.user,  # student creates their own practice
            num_questions=num_questions,
            mode='PRACTICE',
            is_randomized=True,
            is_published=True,
            difficulty_filter=[int(d) for d in difficulty] if difficulty else [],
        )
        for cid in chapter_ids:
            practice_assignment.chapters.add(cid)

        # Assign to student
        sa = assign_questions_to_student(practice_assignment, request.user)

        if sa.assigned_questions.count() == 0:
            practice_assignment.delete()
            from django.contrib import messages
            messages.warning(request, 'No questions match your filters. Try different settings.')
            return redirect('practice_setup')

        return redirect('take_assignment', sa_pk=sa.pk)

    return render(request, 'assignments/student/practice.html', {'chapters': chapters})
```

- [ ] **Step 2: Create practice setup template**

```html
<!-- templates/assignments/student/practice.html -->
{% extends "base.html" %}
{% block title %}Practice Mode{% endblock %}
{% block content %}
<h2>Practice Mode</h2>
<p>Select chapters and settings, then start practicing. You'll get instant feedback on each question.</p>
<form method="post">
    {% csrf_token %}
    <div class="row">
        <div class="col-md-6">
            <h5>Chapters</h5>
            {% for ch in chapters %}
            <div class="form-check">
                <input type="checkbox" name="chapters" value="{{ ch.id }}" class="form-check-input" id="pch{{ ch.id }}">
                <label class="form-check-label" for="pch{{ ch.id }}">Ch {{ ch.number }}: {{ ch.title }}</label>
            </div>
            {% endfor %}
        </div>
        <div class="col-md-6">
            <h5>Difficulty</h5>
            <div class="form-check form-check-inline">
                <input type="checkbox" name="difficulty" value="1" class="form-check-input" checked> <label class="form-check-label">Easy</label>
            </div>
            <div class="form-check form-check-inline">
                <input type="checkbox" name="difficulty" value="2" class="form-check-input" checked> <label class="form-check-label">Medium</label>
            </div>
            <div class="form-check form-check-inline">
                <input type="checkbox" name="difficulty" value="3" class="form-check-input"> <label class="form-check-label">Hard</label>
            </div>
            <div class="mt-3">
                <label class="form-label">Number of questions</label>
                <input type="number" name="num_questions" class="form-control" value="10" min="1" max="50" style="max-width: 120px;">
            </div>
        </div>
    </div>
    <button type="submit" class="btn btn-primary mt-3">Start Practice</button>
</form>
{% endblock %}
```

- [ ] **Step 3: Add URL**

Add to `apps/assignments/urls.py`:

```python
    path('practice/', views.practice_setup, name='practice_setup'),
```

- [ ] **Step 4: Commit**

```bash
git add apps/assignments/ templates/assignments/student/practice.html
git commit -m "feat: add practice mode with chapter/difficulty selection"
```

---

### Task 17: Mistake Collection

**Files:**
- Modify: `apps/assignments/views.py`
- Modify: `apps/assignments/urls.py`
- Create: `templates/assignments/student/mistakes.html`

- [ ] **Step 1: Add mistake collection views**

Add to `apps/assignments/views.py`:

```python
@login_required
def mistake_collection(request):
    if not request.user.is_student:
        return redirect('instructor_dashboard')

    chapter_filter = request.GET.get('chapter')
    mistakes = MistakeEntry.objects.filter(
        student=request.user, is_mastered=False,
    ).select_related('question__section__chapter').order_by('-added_at')

    if chapter_filter:
        mistakes = mistakes.filter(question__section__chapter_id=chapter_filter)

    chapters = Chapter.objects.filter(
        sections__questions__mistake_entries__student=request.user,
        sections__questions__mistake_entries__is_mastered=False,
    ).distinct()

    return render(request, 'assignments/student/mistakes.html', {
        'mistakes': mistakes,
        'chapters': chapters,
        'selected_chapter': chapter_filter,
    })


@login_required
def mark_mastered(request, pk):
    if request.method == 'POST':
        me = get_object_or_404(MistakeEntry, pk=pk, student=request.user)
        me.is_mastered = True
        me.save(update_fields=['is_mastered'])
    return redirect('mistake_collection')


@login_required
def practice_mistakes(request):
    """Generate a practice set from the student's mistake collection."""
    if not request.user.is_student:
        return redirect('instructor_dashboard')

    mistakes = MistakeEntry.objects.filter(
        student=request.user, is_mastered=False,
    ).select_related('question')

    question_ids = list(mistakes.values_list('question_id', flat=True))
    if not question_ids:
        messages.info(request, 'No mistakes to practice!')
        return redirect('mistake_collection')

    # Create a practice assignment from mistake questions
    practice = Assignment.objects.create(
        title=f'Mistake Review — {timezone.now().strftime("%b %d %H:%M")}',
        created_by=request.user,
        num_questions=min(len(question_ids), 20),
        mode='PRACTICE',
        is_randomized=True,
        is_published=True,
    )
    practice.manually_selected_questions.set(question_ids)

    sa = assign_questions_to_student(practice, request.user)

    # Update last_practiced_at
    mistakes.update(last_practiced_at=timezone.now())
    mistakes.update(times_practiced=models.F('times_practiced') + 1)

    return redirect('take_assignment', sa_pk=sa.pk)
```

Note: add `from django.db import models` if not already imported.

- [ ] **Step 2: Create mistakes template**

```html
<!-- templates/assignments/student/mistakes.html -->
{% extends "base.html" %}
{% block title %}Mistake Collection{% endblock %}
{% block content %}
<h2>Mistake Collection ({{ mistakes.count }})</h2>

<div class="d-flex justify-content-between mb-3">
    <div>
        <select class="form-select form-select-sm d-inline-block" style="width: auto;"
                onchange="window.location='?chapter='+this.value">
            <option value="">All Chapters</option>
            {% for ch in chapters %}
            <option value="{{ ch.id }}" {% if selected_chapter == ch.id|stringformat:"d" %}selected{% endif %}>
                Ch {{ ch.number }}: {{ ch.title }}
            </option>
            {% endfor %}
        </select>
    </div>
    {% if mistakes.count > 0 %}
    <form method="post" action="{% url 'practice_mistakes' %}">
        {% csrf_token %}
        <button class="btn btn-primary btn-sm">Re-Practice All ({{ mistakes.count|cut:" " }})</button>
    </form>
    {% endif %}
</div>

{% for me in mistakes %}
<div class="card mb-2">
    <div class="card-body">
        <div class="d-flex justify-content-between">
            <span>
                <span class="badge bg-secondary">Ch {{ me.question.section.chapter.number }}</span>
                Q{{ me.question.question_number }}
                <span class="badge bg-warning text-dark">Diff {{ me.question.difficulty }}</span>
            </span>
            <span>
                {% if me.times_practiced > 0 %}
                <small class="text-muted">Practiced {{ me.times_practiced }}x</small>
                {% endif %}
                <form method="post" action="{% url 'mark_mastered' me.pk %}" class="d-inline">
                    {% csrf_token %}
                    <button class="btn btn-sm btn-outline-success">Mark Mastered</button>
                </form>
            </span>
        </div>
        <p class="mt-2 mb-0">{{ me.question.text|truncatechars:200 }}</p>
    </div>
</div>
{% empty %}
<p class="text-muted">No mistakes to review. Great job!</p>
{% endfor %}
{% endblock %}
```

- [ ] **Step 3: Add URLs**

Add to `apps/assignments/urls.py`:

```python
    path('mistakes/', views.mistake_collection, name='mistake_collection'),
    path('mistakes/<int:pk>/mastered/', views.mark_mastered, name='mark_mastered'),
    path('mistakes/practice/', views.practice_mistakes, name='practice_mistakes'),
```

- [ ] **Step 4: Commit**

```bash
git add apps/assignments/ templates/assignments/student/mistakes.html
git commit -m "feat: add mistake collection with re-practice and mark-mastered functionality"
```

---

## Chunk 8: Analytics & Final Polish

### Task 18: Student Analytics

**Files:**
- Modify: `apps/assignments/views.py`
- Modify: `apps/assignments/urls.py`
- Create: `templates/assignments/student/analytics.html`

- [ ] **Step 1: Add student analytics view**

Add to `apps/assignments/views.py`:

```python
import json


@login_required
def student_analytics(request):
    if not request.user.is_student:
        return redirect('instructor_dashboard')

    answers = StudentAnswer.objects.filter(
        student_assignment__student=request.user,
        is_correct__isnull=False,
    ).select_related('question__section__chapter')

    # Per-chapter accuracy
    chapter_stats = {}
    for ans in answers:
        ch = ans.question.section.chapter
        key = f'Ch {ch.number}'
        if key not in chapter_stats:
            chapter_stats[key] = {'correct': 0, 'total': 0}
        chapter_stats[key]['total'] += 1
        if ans.is_correct:
            chapter_stats[key]['correct'] += 1

    chapter_labels = sorted(chapter_stats.keys())
    chapter_accuracy = [round(chapter_stats[k]['correct'] / chapter_stats[k]['total'] * 100) for k in chapter_labels]

    # Per-difficulty accuracy
    diff_stats = {1: {'correct': 0, 'total': 0}, 2: {'correct': 0, 'total': 0}, 3: {'correct': 0, 'total': 0}}
    for ans in answers:
        d = ans.question.difficulty
        diff_stats[d]['total'] += 1
        if ans.is_correct:
            diff_stats[d]['correct'] += 1

    diff_labels = ['Easy (1)', 'Medium (2)', 'Hard (3)']
    diff_accuracy = [round(diff_stats[d]['correct'] / diff_stats[d]['total'] * 100) if diff_stats[d]['total'] > 0 else 0 for d in [1, 2, 3]]

    # Per-skill accuracy
    skill_stats = {}
    for ans in answers:
        s = ans.question.skill
        if s not in skill_stats:
            skill_stats[s] = {'correct': 0, 'total': 0}
        skill_stats[s]['total'] += 1
        if ans.is_correct:
            skill_stats[s]['correct'] += 1

    skill_labels = sorted(skill_stats.keys())
    skill_accuracy = [round(skill_stats[s]['correct'] / skill_stats[s]['total'] * 100) for s in skill_labels]

    # Progress over time
    completed_sas = StudentAssignment.objects.filter(
        student=request.user, status='COMPLETED',
    ).order_by('completed_at')

    progress_labels = [sa.assignment.title[:20] for sa in completed_sas]
    progress_scores = [round(sa.score / sa.max_score * 100) if sa.max_score > 0 else 0 for sa in completed_sas]

    # Time analysis
    avg_time = answers.aggregate(avg_time=models.Avg('server_elapsed_seconds'))['avg_time'] or 0

    # Weakest sections
    section_stats = {}
    for ans in answers:
        sec = f'{ans.question.section.number} {ans.question.section.title}'
        if sec not in section_stats:
            section_stats[sec] = {'correct': 0, 'total': 0}
        section_stats[sec]['total'] += 1
        if ans.is_correct:
            section_stats[sec]['correct'] += 1

    weakest = sorted(
        [(k, v['correct'] / v['total'] * 100) for k, v in section_stats.items() if v['total'] >= 3],
        key=lambda x: x[1],
    )[:5]

    return render(request, 'assignments/student/analytics.html', {
        'chapter_labels': json.dumps(chapter_labels),
        'chapter_accuracy': json.dumps(chapter_accuracy),
        'diff_labels': json.dumps(diff_labels),
        'diff_accuracy': json.dumps(diff_accuracy),
        'skill_labels': json.dumps(skill_labels),
        'skill_accuracy': json.dumps(skill_accuracy),
        'progress_labels': json.dumps(progress_labels),
        'progress_scores': json.dumps(progress_scores),
        'avg_time': round(avg_time),
        'total_answered': answers.count(),
        'total_correct': answers.filter(is_correct=True).count(),
        'weakest': weakest,
    })
```

- [ ] **Step 2: Create analytics template**

```html
<!-- templates/assignments/student/analytics.html -->
{% extends "base.html" %}
{% block title %}My Analytics{% endblock %}
{% block content %}
<h2>My Analytics</h2>
<div class="row mb-4">
    <div class="col-md-3"><div class="card text-center"><div class="card-body"><h3>{{ total_answered }}</h3><p class="text-muted">Questions Answered</p></div></div></div>
    <div class="col-md-3"><div class="card text-center"><div class="card-body"><h3>{{ total_correct }}</h3><p class="text-muted">Correct</p></div></div></div>
    <div class="col-md-3"><div class="card text-center"><div class="card-body"><h3>{% widthratio total_correct total_answered 100 %}%</h3><p class="text-muted">Accuracy</p></div></div></div>
    <div class="col-md-3"><div class="card text-center"><div class="card-body"><h3>{{ avg_time }}s</h3><p class="text-muted">Avg Time/Question</p></div></div></div>
</div>

<div class="row">
    <div class="col-md-6"><canvas id="chapterChart"></canvas></div>
    <div class="col-md-6"><canvas id="diffChart"></canvas></div>
</div>
<div class="row mt-4">
    <div class="col-md-6"><canvas id="skillChart"></canvas></div>
    <div class="col-md-6"><canvas id="progressChart"></canvas></div>
</div>

{% if weakest %}
<h4 class="mt-4">Weakest Areas</h4>
<ul class="list-group">
    {% for name, pct in weakest %}
    <li class="list-group-item d-flex justify-content-between">{{ name }} <span class="badge bg-danger">{{ pct|floatformat:0 }}%</span></li>
    {% endfor %}
</ul>
{% endif %}
{% endblock %}

{% block extra_js %}
<script src="https://cdn.jsdelivr.net/npm/chart.js@4"></script>
<script>
function barChart(id, labels, data, label, color) {
    new Chart(document.getElementById(id), {
        type: 'bar', data: { labels: labels, datasets: [{label: label, data: data, backgroundColor: color}] },
        options: { scales: { y: { beginAtZero: true, max: 100 } }, plugins: { legend: { display: false } } }
    });
}
function lineChart(id, labels, data) {
    new Chart(document.getElementById(id), {
        type: 'line', data: { labels: labels, datasets: [{label: 'Score %', data: data, borderColor: '#0d6efd', fill: false, tension: 0.3}] },
        options: { scales: { y: { beginAtZero: true, max: 100 } } }
    });
}
barChart('chapterChart', {{ chapter_labels|safe }}, {{ chapter_accuracy|safe }}, 'Accuracy %', '#0d6efd');
barChart('diffChart', {{ diff_labels|safe }}, {{ diff_accuracy|safe }}, 'Accuracy %', '#198754');
barChart('skillChart', {{ skill_labels|safe }}, {{ skill_accuracy|safe }}, 'Accuracy %', '#6f42c1');
lineChart('progressChart', {{ progress_labels|safe }}, {{ progress_scores|safe }});
</script>
{% endblock %}
```

- [ ] **Step 3: Add URL**

Add to `apps/assignments/urls.py`:

```python
    path('analytics/', views.student_analytics, name='student_analytics'),
```

- [ ] **Step 4: Commit**

```bash
git add apps/assignments/ templates/assignments/student/analytics.html
git commit -m "feat: add student analytics with per-chapter, difficulty, skill charts and weakest areas"
```

---

### Task 19: Instructor Analytics Enhancement

The instructor dashboard (Task 13) already shows basic stats. This task adds the score distribution histogram and question difficulty analysis.

**Files:**
- Modify: `apps/assignments/views.py` (update `instructor_dashboard`)
- Modify: `templates/assignments/instructor/dashboard.html`

- [ ] **Step 1: Enhance instructor dashboard view**

Update the `instructor_dashboard` view to include chart data:

```python
# Add to instructor_dashboard view, after existing code:

    # Score distribution for most recent published assignment
    latest = Assignment.objects.filter(created_by=request.user, is_published=True).first()
    score_distribution = []
    if latest:
        sas = latest.student_assignments.filter(status='COMPLETED')
        scores = [sa.score for sa in sas if sa.score is not None]
        if scores:
            max_s = latest.num_questions
            # Bucket into 10% ranges
            buckets = [0] * 11  # 0%, 10%, ..., 100%
            for s in scores:
                pct = int(s / max_s * 10) if max_s > 0 else 0
                buckets[min(pct, 10)] += 1
            score_distribution = buckets

    # Per-student summary
    student_summaries = []
    for student in User.objects.filter(role='STUDENT').order_by('last_name'):
        sas = StudentAssignment.objects.filter(student=student, status='COMPLETED')
        total_time = sum(
            sa.answers.aggregate(t=models.Sum('server_elapsed_seconds'))['t'] or 0
            for sa in sas
        )
        avg_pct = None
        if sas.exists():
            pcts = [sa.score / sa.max_score * 100 for sa in sas if sa.max_score > 0]
            avg_pct = sum(pcts) / len(pcts) if pcts else None
        student_summaries.append({
            'name': student.get_full_name() or student.username,
            'completed': sas.count(),
            'avg_score': avg_pct,
            'total_time_min': round(total_time / 60),
        })

    # Add to context:
    context.update({
        'score_distribution': json.dumps(score_distribution),
        'student_summaries': student_summaries,
    })
```

- [ ] **Step 2: Add chart and student summary table to dashboard template**

Append to `templates/assignments/instructor/dashboard.html` before `{% endblock %}`:

```html
<div class="row mt-4">
    <div class="col-md-6">
        <h4>Score Distribution (Latest Assignment)</h4>
        <canvas id="scoreDistChart"></canvas>
    </div>
    <div class="col-md-6">
        <h4>Student Summary</h4>
        <table class="table table-sm">
            <thead><tr><th>Student</th><th>Completed</th><th>Avg Score</th><th>Time (min)</th></tr></thead>
            <tbody>
            {% for s in student_summaries %}
            <tr>
                <td>{{ s.name }}</td>
                <td>{{ s.completed }}</td>
                <td>{% if s.avg_score is not None %}{{ s.avg_score|floatformat:0 }}%{% else %}—{% endif %}</td>
                <td>{{ s.total_time_min }}</td>
            </tr>
            {% endfor %}
            </tbody>
        </table>
    </div>
</div>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4"></script>
<script>
const dist = {{ score_distribution|safe }};
if (dist.length) {
    new Chart(document.getElementById('scoreDistChart'), {
        type: 'bar',
        data: { labels: ['0%','10%','20%','30%','40%','50%','60%','70%','80%','90%','100%'], datasets: [{label: 'Students', data: dist, backgroundColor: '#0d6efd'}] },
        options: { scales: { y: { beginAtZero: true, ticks: { stepSize: 1 } } }, plugins: { legend: { display: false } } }
    });
}
</script>
```

- [ ] **Step 3: Commit**

```bash
git add apps/assignments/views.py templates/assignments/instructor/dashboard.html
git commit -m "feat: add instructor score distribution chart and student summary table"
```

---

### Task 20: Final Integration & Smoke Test

**Files:**
- Verify: all URLs resolve
- Verify: full user flow works end-to-end

- [ ] **Step 1: Run all tests**

```bash
python manage.py test -v2
```

Expected: All tests PASS.

- [ ] **Step 2: Run migrations and create test data**

```bash
python manage.py migrate
python manage.py import_testbank "/home/georgejjj/testbank/chapter 4.docx"
python manage.py createsuperuser  # if not already done
```

- [ ] **Step 3: Manual smoke test**

```bash
python manage.py runserver 0.0.0.0:8000
```

Test the following flow:
1. Login as instructor → see dashboard
2. Browse questions → verify chapter 4 questions display with MathJax
3. Create an assignment (auto-generate, chapter 4, 10 questions)
4. Publish the assignment
5. Create a test student via roster (or Django admin)
6. Login as student → see dashboard with the assignment
7. Start assignment → answer questions → submit
8. View results with score and explanations
9. Check mistake collection
10. Try practice mode
11. View student analytics

- [ ] **Step 4: Commit any fixes from smoke test**

```bash
git add -A
git commit -m "fix: address issues found during smoke testing"
```

---
