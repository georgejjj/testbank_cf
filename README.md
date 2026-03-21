# TestBank

A web-based question bank and assignment platform for university courses. Import questions from official textbook test bank files (.docx), create assignments, and let students complete them with auto-grading and analytics.

Built for **Corporate Finance (Berk/DeMarzo 6e)** but works with any Pearson-format test bank.

**Live:** [testbank.fin-tech.fun](https://testbank.fin-tech.fun)

---

## Features

### Instructor

- **Import questions** from .docx test bank files with preview and confirmation
- **Question browser** with filters (chapter, section, difficulty, skill, type, search)
- **Edit questions** — fix text, change type, update choices, edit context info
- **Create assignments** — auto-generate from filters or hand-pick individual questions
- **Randomization** — each student gets a different question set and shuffled MC choices
- **Auto-grading** — MC (instant) and numeric (with tolerance)
- **Manual grading** — free-response grading queue with feedback
- **Student monitoring** — per-student answer drill-down, scores, time spent
- **Analytics dashboard** — score distribution, student summary, completion rates
- **Student roster** — CSV import with auto-generated credentials, password reset
- **Backup & restore** — download/upload database from the web interface

### Student

- **Dashboard** — active assignments, recent results, quick stats
- **Assignment taking** — one question at a time, timer, progress bar, smooth MC selection
- **Mistake collection** — auto-collects wrong answers, re-practice, mark mastered
- **Analytics** — per-chapter/difficulty/skill accuracy charts, progress over time, weakest areas
- **Results review** — correct answers, explanations, instructor feedback

### Question Types

| Type | Grading | Input |
|------|---------|-------|
| Multiple Choice | Auto (instant) | Click to select |
| Numeric | Auto (1% tolerance) | Type number |
| Free Response | Manual (instructor) | Text area |

---

## Quick Start

### Prerequisites

- Python 3.10+
- pip

### Installation

```bash
git clone <repo-url>
cd testbank
pip install -r requirements.txt
python3 manage.py migrate
python3 manage.py createsuperuser  # Create instructor account
```

### Import Questions

```bash
python3 manage.py import_testbank "chapter 4.docx"
```

Or use the web interface: **Questions > Import .docx**

### Run Development Server

```bash
python3 manage.py runserver 0.0.0.0:8000
```

Visit `http://localhost:8000`

---

## Production Deployment

Designed for a single server (2-core, 2GB RAM). Uses Gunicorn + Nginx + SSL.

```bash
bash deploy/setup.sh testbank.yourdomain.com
```

This sets up:
- Gunicorn (3 workers, port 8001)
- Nginx reverse proxy with static file serving
- SSL via Let's Encrypt
- systemd service with auto-restart

See `deploy/` directory for individual config files.

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Django 5.0, Python 3.12 |
| Database | SQLite (WAL mode) |
| Frontend | Bootstrap 5, HTMX, MathJax 3, Chart.js 4 |
| Typography | DM Serif Display + DM Sans |
| Server | Gunicorn, Nginx, systemd |
| SSL | Let's Encrypt (certbot) |

---

## Project Structure

```
testbank/
├── apps/
│   ├── accounts/        # User auth, roles, student roster
│   ├── questions/       # Question pool, parser, browser, import
│   └── assignments/     # Assignments, student work, grading, analytics
├── services/
│   ├── parser.py        # .docx test bank parser
│   ├── grader.py        # Auto-grading engine
│   └── randomizer.py    # Question selection & shuffling
├── templates/           # Django HTML templates
├── static/              # CSS, JS (timer, chart helpers)
├── media/questions/     # Extracted images from .docx files
├── deploy/              # Gunicorn, Nginx, systemd configs
└── tests/               # 32 tests (models, parser, grader, randomizer)
```

---

## Adding Students

1. Go to **Students** in the nav
2. Upload a CSV with columns: `username, first_name, last_name, student_id, email`
3. Download the generated credential sheet
4. Distribute to students — they must change password on first login

---

## Backup

From the **Questions** page:
- **Backup** — downloads the entire database
- **Restore** — upload a backup to replace current data

---

## Tests

```bash
python3 manage.py test -v2
```

32 tests covering models, parser, grader, and randomizer.

---

## License

For educational use.
