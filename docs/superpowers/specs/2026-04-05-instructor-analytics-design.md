# Instructor Analytics Page — Design Spec

## Overview

A dedicated "Analyze" tab in the instructor navigation that provides flexible, filterable analytics across assignments and students. Replaces the basic score distribution on the existing dashboard with a comprehensive analysis tool.

## Navigation

- New top-level nav item: **Analyze** — placed after "Messages" in the instructor navbar
- URL: `/assignments/analyze/`
- Instructor-only (no student/TA access)

## Page Layout

Single scrollable page. All sections update dynamically via HTMX when filters change.

### 1. Filters (top of page, side-by-side)

**Assignment Selector (left)**
- Toggle-able pills for each published assignment (mode=ASSIGNMENT only, not PRACTICE)
- "All" button selects all, "Clear" deselects all
- Default state: all selected
- Pills show assignment title, styled navy when selected, grey when deselected

**Student Selector (right)**
- Default: "All Students" pill selected (shows student count)
- Search box to find and toggle individual students
- When individual students are selected, show them as pills (same toggle style)
- "All" / "Clear" buttons like assignments

**HTMX behavior:** Changing either filter triggers a POST to the same URL with selected assignment IDs and student IDs. The server re-renders the analytics content area below the filters. Use `hx-target` on a wrapper div around everything below the filters.

### 2. Summary Statistics Cards (row of 5)

Computed from completed `StudentAssignment` records matching the selected assignments and students:

| Card | Calculation |
|------|-------------|
| **Mean** | Average of per-student average scores (as %) |
| **Median** | Median of per-student average scores (as %) |
| **Std Dev** | Standard deviation of per-student average scores |
| **Pass Rate** | % of students with average score >= 70% |
| **Avg Time** | Mean of `total_time_seconds` across all matching StudentAssignments, displayed in minutes |

### 3. Min/Max Row (2 cards)

- **Highest**: Best per-student average score, with student name
- **Lowest**: Worst per-student average score, with student name

### 4. Score Distribution Chart

- Chart.js bar chart (consistent with existing dashboard style)
- 11 buckets: 0%, 10%, 20%, ... 100%
- Each student's average score across selected assignments placed into a bucket
- Gold bars (`#d4a843`), green for 100% bucket (`#2d8a4e`), grey for empty buckets
- Subtitle shows count of assignments and students in current filter

### 5. Student Breakdown (collapsible)

**Header bar** (always visible, clickable to expand/collapse):
- Toggle arrow (▼/▶) + "Student Breakdown" + student count
- **Export Raw Scores CSV** button (navy, prominent)
- **Export Breakdown CSV** button (grey)
- Sort dropdown (default: Score descending)

**Table columns:**
| Column | Data |
|--------|------|
| # | Rank by sort order |
| Student | Full name |
| Completed | `X/Y` where Y = number of selected assignments |
| Avg Score | Average score % across selected assignments (color-coded: green >= 80, gold 60-79, red < 60) |
| Accuracy | Total correct / total answered as % |
| Avg Time | Average `total_time_seconds` in minutes |
| Bar | Visual progress bar matching avg score |

**Collapse behavior:** Use Bootstrap 5 `collapse` component. Default state: expanded. Toggled by clicking the header bar.

### 6. Weakest Sections Table

- Query all `StudentAnswer` records for the selected assignments/students
- Group by `question.section`, compute accuracy = correct / total
- Filter: minimum 5 attempts
- Sort: ascending by accuracy
- Show top 10

**Columns:** Section number, Topic (section title), Attempts, Accuracy %, visual bar

### 7. Most-Missed Questions Table

- Query `StudentAnswer` records, group by question
- Error rate = incorrect / total attempts
- Filter: minimum 3 attempts
- Sort: descending by error rate
- Paginated display: show top 10 by default, toggle to 20 / All

**Columns:** UID (`question.uid`), Question text (truncated to ~60 chars), Times Asked, Error Rate %, Section

## CSV Exports

### Export Raw Scores CSV

- URL: `/assignments/analyze/export-raw/` (GET, with assignment IDs + student IDs as query params)
- Format: one row per student, one column per selected assignment
- Header: `Student, {Assignment 1 title}, {Assignment 2 title}, ...`
- Cell value: `score/max_score` (e.g., `19/20`), or `—` if not completed
- Filename: `raw_scores_YYYY-MM-DD.csv`

### Export Breakdown CSV

- URL: `/assignments/analyze/export-breakdown/` (GET, same query params)
- Format: mirrors the Student Breakdown table
- Header: `Rank, Student, Completed, Avg Score %, Accuracy %, Avg Time (min)`
- Filename: `student_breakdown_YYYY-MM-DD.csv`

## Data Flow

1. Page loads with all assignments and all students selected
2. View queries:
   - All published assignments (for filter pills)
   - All students with role=STUDENT (for filter)
   - `StudentAssignment` objects filtered by selected assignment + student IDs, status=COMPLETED
   - `StudentAnswer` objects joined through those StudentAssignments (for section/question analysis)
3. Filter changes trigger HTMX POST → server re-computes and returns partial HTML for the analytics content area
4. Export buttons link to GET endpoints that stream CSV responses using Django's `StreamingHttpResponse`

## Technical Notes

- **View location:** New view function `instructor_analyze` in `apps/assignments/views.py`
- **Template:** `templates/assignments/instructor/analyze.html`
- **No new models needed** — all data derived from existing `StudentAssignment` and `StudentAnswer`
- **Statistics:** Use Python's `statistics` module (`mean`, `median`, `stdev`)
- **Chart.js:** Same CDN already in use, same styling conventions as existing dashboard
- **HTMX:** Filter form posts to same URL, swaps `#analytics-content` div
- **Collapsible section:** Bootstrap 5 `data-bs-toggle="collapse"` on the Student Breakdown header
- **Permissions:** `@login_required` + `request.user.is_instructor` check
