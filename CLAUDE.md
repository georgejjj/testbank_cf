# CLAUDE.md

## Project Overview

TestBank is a Django web application for managing and delivering textbook test bank questions to students. Built for Corporate Finance (Berk/DeMarzo 6e) but designed to work with any Pearson-format .docx test bank files.

**Live URL:** https://testbank.fin-tech.fun

## Tech Stack

- **Backend:** Django 5.0, Python 3.12, SQLite (WAL mode)
- **Frontend:** Bootstrap 5, HTMX, MathJax 3, Chart.js 4
- **Fonts:** DM Serif Display + DM Sans (Google Fonts)
- **Server:** Gunicorn + Nginx, systemd service
- **No JS build step** — all frontend is server-rendered templates with CDN libraries

## Project Structure

```
testbank/
├── config/              # Django project settings, URLs, WSGI
├── apps/
│   ├── accounts/        # User model (role: INSTRUCTOR/STUDENT), auth, roster
│   ├── questions/       # Chapter, Section, Question, MCChoice, NumericAnswer models
│   └── assignments/     # Assignment, StudentAssignment, StudentAnswer, MistakeEntry
├── services/
│   ├── parser.py        # .docx testbank parser (XML extraction, state machine)
│   ├── grader.py        # Auto-grading (MC, numeric with tolerance)
│   └── randomizer.py    # Question pool selection, shuffling, choice shuffle map
├── templates/           # Django templates (base.html, accounts/, questions/, assignments/)
├── static/css/style.css # Custom design system (navy/gold academic theme)
├── static/js/timer.js   # Per-question timer
├── media/questions/     # Extracted images from .docx files (not in git)
├── deploy/              # Gunicorn config, nginx config, systemd service, setup.sh
├── tests/               # Model, parser, grader, randomizer tests
└── docs/superpowers/    # Design spec and implementation plan
```

## Key Architecture Decisions

- **Business logic in `services/`**, not in views — views are thin wrappers. This enables future API upgrade (DRF).
- **SQLite** is sufficient for 60 students. WAL mode + busy_timeout for concurrency.
- **Apps path trick**: `sys.path.insert(0, 'apps/')` so imports are `from accounts.models` not `from apps.accounts.models`.
- **Question UIDs**: `CH{chapter}-{global_number:03d}` format (e.g., CH4-037). `global_number` is sequential within a chapter, assigned during import.
- **Randomization frozen at assignment start**: Each student's question set and choice shuffle stored in `StudentAssignment`.
- **MC answers submitted via fetch()**: No page reload — instant visual feedback.

## Common Commands

```bash
# Development
python3 manage.py runserver 0.0.0.0:8000

# Import questions
python3 manage.py import_testbank "chapter 4.docx"
python3 manage.py import_testbank --dir ./testbank_files/

# Run tests
python3 manage.py test -v2

# Production
sudo systemctl restart testbank
sudo journalctl -u testbank -f

# Create instructor account
python3 manage.py createsuperuser
```

## Code Conventions

- Views use `@login_required` and check `request.user.is_instructor` / `request.user.is_student`
- Templates extend `base.html`, use Bootstrap 5 classes + custom CSS variables (see style.css)
- HTMX used for: question browser live filtering, MC answer submission, question navigation
- All dates stored as UTC, displayed via Django template filters
- CSS uses custom properties: `--navy`, `--gold`, `--warm-bg`, `--success`, etc.

## Testing

32 tests covering: models (13), parser (6), grader (8), randomizer (5).

```bash
python3 manage.py test -v2
```

## Deployment

Deployed at `testbank.fin-tech.fun` via:
- Gunicorn on port 8001 (3 workers, max-requests=1000)
- Nginx reverse proxy with static/media serving
- SSL via Let's Encrypt
- systemd service: `testbank.service`

Deploy script: `bash deploy/setup.sh testbank.fin-tech.fun`
