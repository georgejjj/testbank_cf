# Testbank System Design

**Date**: 2026-03-16
**Textbook**: Corporate Finance, 6e (Berk/DeMarzo)
**Stack**: Django + SQLite + Bootstrap 5 + HTMX + MathJax + Chart.js

## Overview

A web-based testbank system where an instructor creates assignments drawn from a question pool (parsed from official textbook .docx files), and 60 students log in to complete them. The system auto-grades MC and numeric questions, tracks study behavior, and provides analytics to both instructor and students.

## Constraints

- Single server: 2-core CPU, 2GB RAM
- 60 students, primarily desktop browsers, some mobile
- MVP target: days; polish over 1 month before student testing
- Future: exam mode (deferred from MVP)

---

## 1. Data Model

### Question Pool

```
Chapter
├── id, number (int), title (str)
├── textbook (str)

Section
├── id, chapter (FK), number (str, e.g. "4.1"), title (str)
├── sort_order (int — for correct ordering, since "4.10" sorts before "4.2" as strings)

ContextGroup
├── id, text (str — shared prompt, e.g. "Use the figure below...", may contain HTML tables)
├── image (file path, optional)
├── section (FK to Section, optional — for organizational browsing)

Question
├── id, section (FK)
├── question_type: MC | NUMERIC | FREE_RESPONSE
├── text (str — supports LaTeX delimiters for MathJax)
├── difficulty: 1 | 2 | 3
├── skill: Conceptual | Definition | Analytical
├── explanation (str, optional — worked solution)
├── image (file path, optional)
├── context_group (FK to ContextGroup, optional)
├── question_number (int — original number in the Word file)
├── answer_raw_text (str, optional — original answer text from Word file for instructor review)
├── created_at, updated_at (auto-managed by Django)
├── UNIQUE CONSTRAINT: (section__chapter, question_number)

MCChoice
├── id, question (FK)
├── letter: str (A through E — unconstrained to handle any number of choices)
├── text (str)
├── is_correct: bool

NumericAnswer
├── id, question (FK)
├── value: decimal
├── tolerance_percent: decimal (default 1.0 — stored as human-readable percent; divide by 100 in grading formula)
├── absolute_tolerance: decimal (default 0.01 — used when correct value is zero)
```

### Users & Assignments

```
User (extends Django AbstractUser)
├── role: INSTRUCTOR | STUDENT
├── student_id (str, optional)

Assignment
├── id, title (str), created_by (FK instructor)
├── chapters (M2M to Chapter)
├── sections (M2M to Section) — optional scope filter
├── difficulty_filter (JSON list, optional, e.g. [1,2])
├── skill_filter (JSON list, optional)
├── num_questions: int
├── mode: PRACTICE | ASSIGNMENT
├── is_randomized: bool
├── is_published: bool (default false — students only see published assignments)
├── due_date (datetime, optional)
├── time_limit_minutes (int, optional — for future exam mode)
├── manually_selected_questions (M2M to Question — for hand-pick mode)

StudentAssignment
├── id, student (FK), assignment (FK)
├── choice_shuffle_map (JSON — maps question_id → {original_letter: displayed_letter})
├── started_at (datetime), completed_at (datetime)
├── score (int, nullable), max_score (int) — whole points only, no partial credit
├── status: NOT_STARTED | IN_PROGRESS | COMPLETED
├── UNIQUE CONSTRAINT: (student, assignment)

AssignedQuestion (through-model for StudentAssignment ↔ Question)
├── id, student_assignment (FK), question (FK)
├── position (int — preserves shuffled order, eliminates separate JSON list)
├── UNIQUE CONSTRAINT: (student_assignment, question)

StudentAnswer
├── id, student_assignment (FK), question (FK)
├── selected_choice (FK to MCChoice, nullable) — always the MCChoice.id, not the displayed letter
├── numeric_answer (decimal, nullable)
├── text_answer (text, nullable, max 5000 chars)
├── is_correct: bool (null for FREE_RESPONSE until manually graded)
├── time_spent_seconds: int (client-side)
├── server_elapsed_seconds: int (computed server-side as fallback)
├── answered_at: datetime
├── instructor_feedback (text, optional — for free response grading)
├── question_text_snapshot (text — frozen copy of question text at submission time)
├── UNIQUE CONSTRAINT: (student_assignment, question)
```

### Mistake Collection

```
MistakeEntry
├── id, student (FK), question (FK)
├── added_at (datetime), last_practiced_at (datetime, nullable)
├── times_practiced: int (default 0)
├── is_mastered: bool (default false)
├── UNIQUE CONSTRAINT: (student, question)
```

### Key Decisions

- `ContextGroup` handles shared "Use the figure/info below" prompts that multiple questions reference. Linked to `Section` for browsability.
- Questions are randomized at assignment-start time and stored via `AssignedQuestion` through-model with explicit `position` field — no redundant JSON list.
- MC choice order is also shuffled per student; mapping stored in `choice_shuffle_map`. Answer submission always sends `MCChoice.id` (not the displayed letter) so grading is unaffected by shuffle.
- `time_spent_seconds` tracked per question via client-side JS timer. `server_elapsed_seconds` computed server-side as `answered_at - max(started_at, previous_answer.answered_at)`. Analytics use server time; client time is recorded for comparison.
- `question_text_snapshot` on `StudentAnswer` preserves the exact question wording at submission time, so historical answers remain valid even if questions are re-imported with changes.
- Wrong MC/numeric answers auto-add to `MistakeEntry`.
- Scoring is whole points (1 per correct answer). `score` is recomputed when: (a) student submits an answer, (b) instructor grades a free-response question. `max_score` = number of assigned questions.
- All core models include `created_at` and `updated_at` (auto-managed by Django).

---

## 2. Word File Parser

### Pipeline

```
.docx file
  → Extract XML + images via Python zipfile
  → Parse XML to extract text runs in document order
  → Regex-based state machine identifies:
      1. Chapter header
      2. Section headers
      3. Context blocks (shared prompts with optional images)
      4. Question number + text
      5. MC choices (A/B/C/D)
      6. Answer line
      7. Explanation block
      8. Metadata (Diff, Section, Skill)
      9. Image references
  → Emit structured question objects
  → Save to database via Django ORM
```

### State Machine

States: `IDLE → CONTEXT → QUESTION → CHOICES → ANSWER → METADATA`

### Image Handling

- Extract all images from `word/media/` to `MEDIA_ROOT/questions/ch{N}/` (using Django's `media/` convention, not `static/`)
- Track which question/context they belong to by order of appearance in the XML
- Served by Nginx from the `media/` location block

### Formula Handling

- Detect common formula patterns (e.g., `PV = C/r (1 - 1/(1+r)^N)`)
- Wrap in LaTeX delimiters (`$...$`) for MathJax rendering
- Best-effort automatic conversion with manual override field on Question model

### Table Handling

- Parse `<w:tbl>` elements in the XML (not just `<w:p>` paragraphs)
- Extract table cell text in row-major order
- Render as HTML `<table>` in `ContextGroup.text` for display in the web app
- Tables commonly contain cash flow data, investment scenarios referenced by questions

### Question Type Detection

Answer lines in the Word files vary widely:
- `Answer:  C` → MC
- `Answer:  $71,260` → NUMERIC (single clean value)
- `Answer:  PV = $100,000 + ... = $254,641` → NUMERIC (extract final value after last `=`)
- `Answer:  This is a two-step problem...` → FREE_RESPONSE
- `Answer:  ` (empty) → FREE_RESPONSE

Detection heuristic (in order):
1. If answer is a single letter A-E → MC
2. If answer is a single number (possibly with `$`, `,`, `%`, `-`) → NUMERIC, parse directly
3. If answer contains `=` followed by a trailing number → NUMERIC, extract value after last `=`
4. Otherwise → FREE_RESPONSE

The original answer text is always saved to `Question.answer_raw_text` so the instructor can review and correct misclassifications via the Question Browser.

### Management Command

```bash
python manage.py import_testbank "chapter 4.docx"
python manage.py import_testbank --dir ./testbank_files/
```

- Idempotent: re-running updates existing questions (matched by chapter + question number), no duplicates
- Outputs summary: "Chapter 4: 90 questions imported (83 MC, 5 NUMERIC, 2 FREE_RESPONSE), 42 images extracted"
- Logs warnings for unparseable questions

### Design Decisions

- Parser lives in `services/parser.py` — standalone, testable, reusable for future API
- Images stored on disk in `MEDIA_ROOT/`, not database blobs (keeps DB small on 2GB server)
- Default numeric tolerance: 1%, overridable per question by instructor

---

## 3. Application Architecture

### Django App Structure

```
testbank/
├── manage.py
├── config/                 # Django project settings
│   ├── settings.py
│   ├── urls.py
│   └── wsgi.py
├── apps/
│   ├── accounts/           # User auth, profiles, roles
│   ├── questions/          # Question pool, models, parser integration
│   └── assignments/        # Assignment creation, student work, grading
├── services/
│   ├── parser.py           # Word file parser
│   ├── randomizer.py       # Question selection & randomization
│   └── grader.py           # Auto-grading logic (MC + numeric)
├── media/
│   └── questions/          # Extracted images per chapter (served by Nginx)
├── static/
│   ├── css/
│   └── js/                 # Timer, HTMX config, MathJax setup
└── templates/
    ├── base.html           # Bootstrap 5 + MathJax + HTMX
    ├── accounts/
    ├── questions/
    └── assignments/
```

### Business Logic Placement

All grading, randomization, and analytics logic lives in `services/` — not in views or templates. This keeps the codebase clean and makes the future upgrade to API + React frontend straightforward (views become thin wrappers around service calls).

---

## 4. Pages

### Student Pages

| Page | Description |
|------|-------------|
| Login | Student ID + password |
| Dashboard | Active assignments, due dates, past scores, quick stats |
| Assignment list | All assignments with status (not started / in progress / completed / score) |
| Take assignment | One question at a time. Timer visible. MC = radio buttons, Numeric = input field, Free response = textarea. Submit each answer individually via HTMX. Navigate back to review/change before final submit |
| Assignment result | Score summary, per-question breakdown (correct/wrong, correct answer, explanation) |
| Practice mode | Pick chapter/section/difficulty → system generates practice set. Same UI as assignment but no due date, instant feedback per question |
| Mistake collection | All wrong answers, filter by chapter. "Re-practice" button generates quiz from mistake pool. "Mark mastered" to hide |
| My analytics | Per-chapter accuracy, difficulty breakdown (bar charts), progress over time (line chart), time analysis, weakest areas |

### Instructor Pages

| Page | Description |
|------|-------------|
| Dashboard | Active assignments, class average, completion rates |
| Create assignment | Two tabs: "Hand-pick" (browse/search/filter, checkbox select) and "Auto-generate" (set parameters → preview → confirm) |
| Assignment detail | Per-student: score, time spent, completion status. Click to see individual answers |
| Grade free response | Queue of ungraded answers. Show question + student answer. Mark correct/incorrect + optional feedback |
| Question browser | Browse by chapter/section. Preview with images + MathJax. Edit LaTeX if auto-conversion was imperfect |
| Import questions | Upload .docx, see parsing preview, confirm import |
| Student roster | Add/remove students, reset passwords, bulk CSV import. CSV import auto-generates random passwords and produces a downloadable credential sheet (CSV) for the instructor to distribute. Students are forced to change password on first login. |

### Interactivity (HTMX)

- Answer submission: `hx-post` per answer, no page reload, updates status indicator
- Timer: Client-side JS per question, pauses on hidden tab, submitted with each answer
- Question navigation: HTMX swaps question content panel on prev/next click
- Live search: Instructor question browser filters via `hx-get`
- Error handling: HTMX `hx-on::after-request` shows user-visible error toast on failure; automatic retry for transient errors

### Responsive Design

- Bootstrap 5 grid
- Desktop: sidebar nav + main content
- Mobile: hamburger nav, full-width question cards, larger touch targets for MC

---

## 5. Grading & Randomization

### Auto-Grading

**MC**: Compare `selected_choice.is_correct`. Instant result.

**Numeric**: Parse student input as decimal (strip `$`, `,`, whitespace). Grading formula:
- If `|correct| > 0`: check `|student - correct| / |correct| <= tolerance_percent` (default 1%)
- If `correct == 0`: check `|student - correct| <= absolute_tolerance` (default 0.01)
Instant result.

**Free Response**: Saved as text, `is_correct = NULL`. Appears in instructor grading queue. Instructor marks correct/incorrect + optional feedback.

### Randomization

```
When student starts an assignment:

If manually_selected_questions exist:
    pool = manually_selected_questions
    If is_randomized: shuffle order
    Assign all to student

If auto-generate mode:
    pool = Question.filter(
        chapter__in=assignment.chapters,
        section__in=assignment.sections,
        difficulty__in=assignment.difficulty_filter,
        skill__in=assignment.skill_filter,
    )
    draw = random.sample(pool, min(num_questions, len(pool)))
    Assign draw in shuffled order

Store in StudentAssignment.assigned_questions (frozen snapshot)
MC choice order also shuffled per student, mapping stored in choice_shuffle_map
```

**Key rule**: Once assigned, a student's question set never changes.

---

## 6. Analytics

### Student Analytics (computed on-demand)

| Metric | Method |
|--------|--------|
| Per-chapter accuracy | % correct grouped by question.section.chapter |
| Per-difficulty accuracy | % correct grouped by difficulty 1/2/3 |
| Per-skill accuracy | % correct grouped by Conceptual/Definition/Analytical |
| Progress over time | Score per assignment, chronological line chart |
| Time analysis | Avg time per question by chapter and difficulty |
| Weakest areas | Sections with lowest accuracy, sorted |

### Instructor Analytics

| Metric | Method |
|--------|--------|
| Class average per assignment | Avg of StudentAssignment.score |
| Completion rate | % students with status=COMPLETED |
| Score distribution | Histogram per assignment |
| Per-student summary | Table: name, avg score, total time, assignments completed |
| Question difficulty analysis | Actual % correct vs labeled difficulty — flags mismatches |

### Charts

Chart.js loaded client-side. Data served as JSON in template context or via HTMX endpoints.

---

## 7. Deployment & Security

### Server Architecture

```
Nginx (reverse proxy + static files)
  → Gunicorn (3 workers, ~150MB each)
    → Django
      → SQLite (WAL mode — activate via PRAGMA journal_mode=WAL or Django settings)

Django database settings:
  CONN_MAX_AGE = None (persistent connections, avoids re-open overhead per request)
  OPTIONS.init_command = "PRAGMA journal_mode=WAL; PRAGMA busy_timeout=5000;"

Memory: Nginx ~20MB + Gunicorn ~450MB + OS ~500MB = ~1GB used, ~1GB headroom
Gunicorn --max-requests=1000 to recycle workers and prevent memory leaks
```

### Security

| Concern | Approach |
|---------|----------|
| Authentication | Django built-in auth, bcrypt-hashed passwords, session cookies |
| Authorization | Role-based middleware: students see only their own data |
| CSRF | Django CSRF protection, configured for HTMX via `hx-headers` |
| Answer tampering | Server validates all submissions; server computes `server_elapsed_seconds` independently; analytics use server time |
| Question exposure | Students receive only assigned questions, never the full pool; answers shown only after submission |
| SQL injection | Django ORM parameterized queries, no raw SQL |
| File upload | .docx only, validated, processed server-side |
| Backup | Daily SQLite backup via cron using `sqlite3 db.sqlite3 ".backup /path/to/backup.db"` (not `cp`, which can corrupt WAL databases). 7-day rotation. |
| SQLite concurrency | `busy_timeout = 5000ms` in Django settings; keep write transactions short in grader service. Document as scaling trigger for PostgreSQL migration. |

### Static Assets

- MathJax loaded from CDN with local fallback
- Bootstrap 5, Chart.js, HTMX from CDN
- Question images served by Nginx from `media/questions/`

---

## 8. Deferred (Future Exam Mode)

Not built in MVP:
- Timed lockout (prevent navigation away)
- IP/browser restrictions
- Proctoring integrations
- Stricter anti-cheat (no-overlap randomized pools)

---

## 9. Future API Upgrade Path

The backend is structured for easy upgrade to Django REST Framework + React:
- Business logic in `services/` (not views)
- Django session auth supported natively by DRF
- Add `/api/` endpoints alongside existing template views
- Replace templates with React incrementally, page by page
