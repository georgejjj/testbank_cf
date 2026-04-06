import csv
import json
from datetime import date

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import models
from django.db.models import Avg, Count, Q
from django.http import HttpResponse, HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from questions.models import Chapter, Question
from services.analytics import compute_analytics
from services.grader import grade_answer, recompute_score
from services.randomizer import assign_questions_to_student

from .models import (
    Assignment,
    AssignedQuestion,
    Message,
    MistakeEntry,
    StudentAnswer,
    StudentAssignment,
)


def _check_late(sa):
    """Mark a StudentAssignment as late if the deadline has passed."""
    due = sa.assignment.due_date
    if due and timezone.now() > due and not sa.is_late:
        sa.is_late = True
        sa.save(update_fields=['is_late'])


# ---- Instructor Views ----

@login_required
def instructor_dashboard(request):
    if not request.user.is_staff_role:
        return redirect('student_dashboard')

    assignments = Assignment.objects.exclude(
        created_by__role='STUDENT',
    ).annotate(
        student_count=Count('student_assignments'),
        completed_count=Count('student_assignments', filter=Q(student_assignments__status='COMPLETED')),
        avg_score=Avg('student_assignments__score'),
    )
    total_students = User.objects.filter(role='STUDENT').count()

    # Score distribution for most recent published assignment
    latest = Assignment.objects.filter(is_published=True).exclude(created_by__role='STUDENT').first()
    score_distribution = []
    if latest:
        sas = latest.student_assignments.filter(status='COMPLETED')
        scores = [sa.score for sa in sas if sa.score is not None]
        if scores and latest.num_questions > 0:
            buckets = [0] * 11
            for s in scores:
                pct = int(s / latest.num_questions * 10)
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
            pcts = [sa.score / sa.max_score * 100 for sa in sas if sa.max_score > 0 and sa.score is not None]
            avg_pct = sum(pcts) / len(pcts) if pcts else None
        student_summaries.append({
            'name': student.get_full_name() or student.username,
            'completed': sas.count(),
            'avg_score': avg_pct,
            'total_time_min': round(total_time / 60),
        })

    return render(request, 'assignments/instructor/dashboard.html', {
        'assignments': assignments,
        'total_students': total_students,
        'score_distribution': json.dumps(score_distribution),
        'student_summaries': student_summaries,
    })


@login_required
def assignment_create(request):
    if not request.user.is_instructor:
        return redirect('student_dashboard')

    if request.method == 'POST':
        title = request.POST.get('title', 'Untitled')
        mode = request.POST.get('mode', 'ASSIGNMENT')
        num_questions = int(request.POST.get('num_questions', 10))
        is_randomized = request.POST.get('is_randomized') == 'on'
        due_date = request.POST.get('due_date') or None

        difficulty_filter = [int(d) for d in request.POST.getlist('difficulty_checks')]
        skill_filter = request.POST.getlist('skill_checks')
        type_filter = request.POST.getlist('type_checks')

        assignment = Assignment.objects.create(
            title=title,
            created_by=request.user,
            num_questions=num_questions,
            mode=mode,
            is_randomized=is_randomized,
            due_date=due_date,
            difficulty_filter=difficulty_filter,
            skill_filter=skill_filter,
            type_filter=type_filter,
        )

        chapter_ids = request.POST.getlist('chapters')
        if chapter_ids:
            assignment.chapters.set(chapter_ids)

        section_ids = request.POST.getlist('sections')
        if section_ids:
            assignment.sections.set(section_ids)

        manual_ids = request.POST.getlist('manual_questions')
        if manual_ids:
            assignment.manually_selected_questions.set(manual_ids)
            assignment.num_questions = len(manual_ids)
            assignment.save()

        # For auto-generate (no manual picks), pre-draw questions so instructor can review/edit
        if not manual_ids:
            from services.randomizer import _build_question_pool
            import random
            pool = _build_question_pool(assignment)
            num = min(assignment.num_questions, len(pool))
            drawn = random.sample(pool, num) if num > 0 else []
            assignment.manually_selected_questions.set(drawn)
            assignment.num_questions = len(drawn)
            assignment.save()
            messages.success(request, f'Assignment "{assignment.title}" created with {len(drawn)} questions. Review and edit before publishing.')
            return redirect('assignment_edit', pk=assignment.pk)

        messages.success(request, f'Assignment "{assignment.title}" created.')
        return redirect('assignment_edit', pk=assignment.pk)

    chapters = Chapter.objects.prefetch_related('sections')
    all_questions = Question.objects.select_related('section__chapter').order_by('section__chapter__number', 'question_number')
    return render(request, 'assignments/instructor/create.html', {
        'chapters': chapters,
        'all_questions': all_questions,
    })


@login_required
def assignment_edit(request, pk):
    """Edit assignment questions before publishing — add, remove, replace."""
    if not request.user.is_instructor:
        return redirect('student_dashboard')

    assignment = get_object_or_404(Assignment, pk=pk, created_by=request.user)

    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'remove':
            q_id = request.POST.get('question_id')
            assignment.manually_selected_questions.remove(q_id)
            assignment.num_questions = assignment.manually_selected_questions.count()
            assignment.save()
            messages.success(request, 'Question removed.')

        elif action == 'add':
            q_ids = request.POST.getlist('add_questions')
            for qid in q_ids:
                assignment.manually_selected_questions.add(qid)
            assignment.num_questions = assignment.manually_selected_questions.count()
            assignment.save()
            if q_ids:
                messages.success(request, f'Added {len(q_ids)} question(s).')

        elif action == 'replace':
            old_id = request.POST.get('old_question_id')
            new_id = request.POST.get('new_question_id')
            if old_id and new_id and old_id != new_id:
                assignment.manually_selected_questions.remove(old_id)
                assignment.manually_selected_questions.add(new_id)
                messages.success(request, 'Question replaced.')

        elif action == 'update_details':
            assignment.title = request.POST.get('title', assignment.title)
            assignment.mode = request.POST.get('mode', assignment.mode)
            due_date = request.POST.get('due_date')
            assignment.due_date = due_date or None
            assignment.is_randomized = request.POST.get('is_randomized') == 'on'
            assignment.save()
            messages.success(request, 'Assignment details updated.')

        elif action == 'regenerate':
            # Re-draw from the same filters
            from services.randomizer import _build_question_pool
            import random
            pool = _build_question_pool(assignment)
            num = min(assignment.num_questions or 10, len(pool))
            drawn = random.sample(pool, num) if num > 0 else []
            assignment.manually_selected_questions.set(drawn)
            assignment.num_questions = len(drawn)
            assignment.save()
            messages.success(request, f'Regenerated {len(drawn)} questions.')

        return redirect('assignment_edit', pk=assignment.pk)

    current_questions = assignment.manually_selected_questions.select_related(
        'section__chapter'
    ).prefetch_related('choices').order_by('section__chapter__number', 'global_number')

    # Available questions for adding (exclude already selected)
    selected_ids = set(current_questions.values_list('id', flat=True))
    available_questions = Question.objects.select_related(
        'section__chapter'
    ).exclude(id__in=selected_ids).order_by('section__chapter__number', 'global_number')

    # Apply chapter filter if the assignment has chapters set
    assigned_chapters = assignment.chapters.all()
    if assigned_chapters.exists():
        available_questions = available_questions.filter(section__chapter__in=assigned_chapters)

    return render(request, 'assignments/instructor/edit.html', {
        'assignment': assignment,
        'current_questions': current_questions,
        'available_questions': available_questions[:300],
        'chapters': Chapter.objects.all(),
    })


@login_required
def assignment_delete(request, pk):
    if not request.user.is_instructor or request.method != 'POST':
        return redirect('instructor_dashboard')
    assignment = get_object_or_404(Assignment, pk=pk, created_by=request.user)
    title = assignment.title
    assignment.delete()
    messages.success(request, f'Assignment "{title}" deleted.')
    return redirect('instructor_dashboard')


@login_required
def assignment_publish(request, pk):
    if not request.user.is_instructor:
        return redirect('student_dashboard')
    assignment = get_object_or_404(Assignment, pk=pk, created_by=request.user)
    assignment.is_published = not assignment.is_published
    assignment.save(update_fields=['is_published'])

    if assignment.is_published:
        students = User.objects.filter(role='STUDENT')
        for student in students:
            assign_questions_to_student(assignment, student)
        messages.success(request, f'Published and assigned to {students.count()} students.')
    else:
        messages.info(request, 'Assignment unpublished.')

    return redirect('instructor_dashboard')


@login_required
def assignment_preview(request, pk):
    """Let instructor take the assignment themselves as a preview/test."""
    if not request.user.is_instructor:
        return redirect('student_dashboard')

    assignment = get_object_or_404(Assignment, pk=pk, created_by=request.user)
    # Delete any previous preview so we always get fresh questions
    StudentAssignment.objects.filter(
        student=request.user, assignment=assignment,
    ).delete()
    sa = assign_questions_to_student(assignment, request.user)

    if sa.assigned_questions.count() == 0:
        messages.warning(request, 'No questions match the assignment filters. Check chapter/difficulty/type settings.')
        return redirect('instructor_dashboard')

    return redirect('take_assignment', sa_pk=sa.pk)


@login_required
def assignment_detail(request, pk):
    if not request.user.is_staff_role:
        return redirect('student_dashboard')
    assignment = get_object_or_404(Assignment, pk=pk)
    student_assignments = assignment.student_assignments.select_related('student').order_by('student__last_name')
    return render(request, 'assignments/instructor/detail.html', {
        'assignment': assignment,
        'student_assignments': student_assignments,
    })


@login_required
def assignment_update_deadline(request, pk):
    """Let instructor change the due date on a published assignment."""
    if not request.user.is_instructor or request.method != 'POST':
        return redirect('instructor_dashboard')
    assignment = get_object_or_404(Assignment, pk=pk, created_by=request.user)
    due_date = request.POST.get('due_date')
    assignment.due_date = due_date or None
    assignment.save(update_fields=['due_date'])
    messages.success(request, f'Deadline updated for "{assignment.title}".')
    return redirect(request.POST.get('next') or 'instructor_dashboard')


@login_required
def student_detail(request, sa_pk):
    """Instructor/TA view: see a specific student's answers for an assignment."""
    if not request.user.is_staff_role:
        return redirect('student_dashboard')

    sa = get_object_or_404(StudentAssignment, pk=sa_pk)

    if request.method == 'POST' and request.POST.get('regrade'):
        answer_id = request.POST.get('answer_id')
        grade_value = request.POST.get('regrade')
        feedback = request.POST.get('feedback', '').strip()
        answer = get_object_or_404(StudentAnswer, id=answer_id, student_assignment=sa)
        answer.is_correct = (grade_value == 'correct')
        if feedback:
            answer.instructor_feedback = feedback
        answer.save()
        recompute_score(sa)
        messages.success(request, f'Answer re-graded as {"correct" if answer.is_correct else "incorrect"}.')
        return redirect('student_detail', sa_pk=sa_pk)

    answers = sa.answers.select_related(
        'question', 'selected_choice'
    ).order_by('question__global_number')

    results = []
    for ans in answers:
        correct_choice = None
        if ans.question.question_type == 'MC':
            correct_choice = ans.question.choices.filter(is_correct=True).first()
        results.append({
            'answer': ans,
            'correct_choice': correct_choice,
        })

    return render(request, 'assignments/instructor/student_detail.html', {
        'sa': sa,
        'results': results,
    })


@login_required
def grade_free_response(request):
    if not request.user.is_staff_role:
        return redirect('student_dashboard')

    if request.method == 'POST':
        answer_id = request.POST.get('answer_id')
        grade_value = request.POST.get('grade', '')
        is_correct = grade_value == 'correct'
        feedback = request.POST.get('feedback', '')

        answer = get_object_or_404(StudentAnswer, id=answer_id)
        answer.is_correct = is_correct
        answer.instructor_feedback = feedback
        answer.save()
        recompute_score(answer.student_assignment)
        messages.success(request, 'Answer graded.')
        # Preserve assignment filter on redirect
        assignment_id = request.POST.get('assignment_id', '')
        url = reverse('grade_free_response')
        if assignment_id:
            url += f'?assignment={assignment_id}'
        return redirect(url)

    ungraded = StudentAnswer.objects.filter(
        question__question_type__in=['FREE_RESPONSE', 'NUMERIC'],
        is_correct__isnull=True,
        student_assignment__status='COMPLETED',
    ).exclude(
        text_answer='', numeric_answer__isnull=True,
    ).select_related('student_assignment__student', 'student_assignment__assignment', 'question')

    # Filter by assignment if selected
    selected_assignment = request.GET.get('assignment', '')
    if selected_assignment:
        ungraded = ungraded.filter(student_assignment__assignment_id=selected_assignment)

    # Get assignments that have ungraded answers for the dropdown
    all_ungraded = StudentAnswer.objects.filter(
        question__question_type__in=['FREE_RESPONSE', 'NUMERIC'],
        is_correct__isnull=True,
        student_assignment__status='COMPLETED',
    ).exclude(
        text_answer='', numeric_answer__isnull=True,
    )
    assignment_ids = all_ungraded.values_list(
        'student_assignment__assignment_id', flat=True
    ).distinct()
    assignments_with_ungraded = Assignment.objects.filter(id__in=assignment_ids).order_by('-created_at')

    # Compute auto-grade suggestion for numeric answers
    from services.grader import grade_numeric, parse_numeric_input
    for answer in ungraded:
        answer.auto_suggestion = None
        if answer.question.question_type == 'NUMERIC':
            try:
                numeric_answer = answer.question.numeric_answer
                student_value = parse_numeric_input(answer.numeric_answer)
                if student_value is not None:
                    answer.auto_suggestion = grade_numeric(numeric_answer, student_value)
            except Exception:
                pass

    return render(request, 'assignments/instructor/grade.html', {
        'ungraded': ungraded,
        'assignments': assignments_with_ungraded,
        'selected_assignment': selected_assignment,
    })


# ---- Student Views ----

@login_required
def student_dashboard(request):
    if not request.user.is_student:
        return redirect('instructor_dashboard')

    active = StudentAssignment.objects.filter(
        student=request.user,
        status__in=['NOT_STARTED', 'IN_PROGRESS'],
        assignment__is_published=True,
    ).select_related('assignment')

    completed = StudentAssignment.objects.filter(
        student=request.user,
        status='COMPLETED',
    ).select_related('assignment').order_by('-completed_at')[:5]

    all_completed = StudentAssignment.objects.filter(student=request.user, status='COMPLETED')
    total_completed = all_completed.count()
    avg_score_pct = None
    if total_completed > 0:
        scores = [(sa.score or 0) / sa.max_score * 100 for sa in all_completed if sa.max_score > 0]
        avg_score_pct = round(sum(scores) / len(scores)) if scores else None

    mistake_count = MistakeEntry.objects.filter(student=request.user, is_mastered=False).count()

    return render(request, 'assignments/student/dashboard.html', {
        'active': active,
        'completed': completed,
        'total_completed': total_completed,
        'avg_score_pct': avg_score_pct,
        'mistake_count': mistake_count,
        'now': timezone.now(),
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
        'now': timezone.now(),
    })


@login_required
def take_assignment(request, sa_pk):
    sa = get_object_or_404(StudentAssignment, pk=sa_pk, student=request.user)

    if sa.status == 'COMPLETED':
        return redirect('assignment_result', sa_pk=sa.pk)

    if sa.status == 'NOT_STARTED':
        sa.status = 'IN_PROGRESS'
        sa.started_at = timezone.now()
        sa.save(update_fields=['status', 'started_at'])

    _check_late(sa)

    assigned = AssignedQuestion.objects.filter(
        student_assignment=sa
    ).select_related('question').order_by('position')
    questions = [aq.question for aq in assigned]

    if not questions:
        messages.warning(request, 'No questions in this assignment.')
        return redirect('student_dashboard')

    current_idx = int(request.GET.get('q', 0))
    current_idx = max(0, min(current_idx, len(questions) - 1))
    current_q = questions[current_idx]

    existing_answer = StudentAnswer.objects.filter(
        student_assignment=sa, question=current_q
    ).first()

    # Get shuffled choices for MC
    choices = []
    if current_q.question_type == 'MC':
        shuffle_map = sa.choice_shuffle_map.get(str(current_q.id), {})
        original_choices = list(current_q.choices.all())
        if shuffle_map:
            reverse_map = {v: k for k, v in shuffle_map.items()}
            for displayed_letter in sorted(reverse_map.keys()):
                original_letter = reverse_map[displayed_letter]
                choice = next((c for c in original_choices if c.letter == original_letter), None)
                if choice:
                    choices.append({
                        'id': choice.id,
                        'display_letter': displayed_letter,
                        'text': choice.text,
                    })
        else:
            choices = [{'id': c.id, 'display_letter': c.letter, 'text': c.text} for c in original_choices]

    answered_ids = set(
        StudentAnswer.objects.filter(student_assignment=sa).values_list('question_id', flat=True)
    )

    due = sa.assignment.due_date
    is_past_due = bool(due and timezone.now() > due)

    context = {
        'sa': sa,
        'question': current_q,
        'question_idx': current_idx,
        'total_questions': len(questions),
        'choices': choices,
        'existing_answer': existing_answer,
        'answered_ids': answered_ids,
        'questions': questions,
        'is_practice': sa.assignment.mode == 'PRACTICE',
        'accumulated_seconds': sa.total_time_seconds,
        'is_past_due': is_past_due,
    }

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

    _check_late(sa)

    question_id = request.POST.get('question_id')
    question = get_object_or_404(Question, id=question_id)
    time_spent = int(request.POST.get('time_spent', 0))
    question_idx = request.POST.get('question_idx', 0)

    # Update accumulated time from client
    accumulated = int(request.POST.get('accumulated_time', 0))
    if accumulated > sa.total_time_seconds:
        sa.total_time_seconds = accumulated
        sa.save(update_fields=['total_time_seconds'])

    # Compute server elapsed
    last_answer = sa.answers.order_by('-answered_at').first()
    reference_time = last_answer.answered_at if last_answer else sa.started_at
    server_elapsed = int((timezone.now() - reference_time).total_seconds()) if reference_time else 0

    answer, created = StudentAnswer.objects.update_or_create(
        student_assignment=sa,
        question=question,
        defaults={
            'time_spent_seconds': time_spent,
            'server_elapsed_seconds': server_elapsed,
            'question_text_snapshot': question.text,
        },
    )

    if question.question_type == 'MC':
        choice_id = request.POST.get('choice_id')
        if choice_id:
            from questions.models import MCChoice
            answer.selected_choice = get_object_or_404(MCChoice, id=choice_id)
    elif question.question_type == 'NUMERIC':
        numeric_val = request.POST.get('numeric_answer', '')
        if numeric_val:
            from services.grader import parse_numeric_input
            answer.numeric_answer = parse_numeric_input(numeric_val)
    else:
        answer.text_answer = request.POST.get('text_answer', '')[:5000]

    grade_answer(answer)
    answer.save()
    recompute_score(sa)

    # AJAX request (from MC fetch) — return JSON instead of redirect
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({'status': 'ok', 'is_correct': answer.is_correct})

    return redirect(f'/assignments/take/{sa.pk}/?q={question_idx}')


@login_required
def complete_assignment(request, sa_pk):
    if request.method != 'POST':
        return HttpResponseForbidden()

    sa = get_object_or_404(StudentAssignment, pk=sa_pk, student=request.user)
    _check_late(sa)
    sa.status = 'COMPLETED'
    sa.completed_at = timezone.now()
    sa.save(update_fields=['status', 'completed_at'])
    recompute_score(sa)

    # Add wrong answers to mistake collection now that assignment is submitted
    wrong_answers = sa.answers.filter(is_correct=False)
    for ans in wrong_answers:
        MistakeEntry.objects.get_or_create(student=request.user, question=ans.question)

    return redirect('assignment_result', sa_pk=sa.pk)


@login_required
def assignment_result(request, sa_pk):
    sa = get_object_or_404(StudentAssignment, pk=sa_pk, student=request.user)

    answers = sa.answers.select_related(
        'question__context_group', 'selected_choice'
    ).prefetch_related('question__choices').order_by('question__question_number')

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


# ---- Practice Mode ----

@login_required
def practice_setup(request):
    if not request.user.is_student:
        return redirect('instructor_dashboard')

    chapters = Chapter.objects.prefetch_related('sections')

    if request.method == 'POST':
        chapter_ids = request.POST.getlist('chapters')
        difficulty = request.POST.getlist('difficulty')
        num_questions = int(request.POST.get('num_questions', 10))

        practice_assignment = Assignment.objects.create(
            title=f'Practice — {timezone.now().strftime("%b %d %H:%M")}',
            created_by=request.user,
            num_questions=num_questions,
            mode='PRACTICE',
            is_randomized=True,
            is_published=True,
            difficulty_filter=[int(d) for d in difficulty] if difficulty else [],
        )
        for cid in chapter_ids:
            practice_assignment.chapters.add(cid)

        sa = assign_questions_to_student(practice_assignment, request.user)

        if sa.assigned_questions.count() == 0:
            practice_assignment.delete()
            messages.warning(request, 'No questions match your filters. Try different settings.')
            return redirect('practice_setup')

        return redirect('take_assignment', sa_pk=sa.pk)

    return render(request, 'assignments/student/practice.html', {'chapters': chapters})


# ---- Mistake Collection ----

@login_required
def mistake_collection(request):
    if not request.user.is_student:
        return redirect('instructor_dashboard')

    chapter_filter = request.GET.get('chapter')
    mistakes = MistakeEntry.objects.filter(
        student=request.user, is_mastered=False,
    ).select_related(
        'question__section__chapter', 'question__context_group'
    ).prefetch_related('question__choices').order_by('-added_at')

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
    if not request.user.is_student:
        return redirect('instructor_dashboard')

    mistakes = MistakeEntry.objects.filter(
        student=request.user, is_mastered=False,
    ).select_related('question')

    question_ids = list(mistakes.values_list('question_id', flat=True))
    if not question_ids:
        messages.info(request, 'No mistakes to practice!')
        return redirect('mistake_collection')

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

    mistakes.update(last_practiced_at=timezone.now())
    mistakes.update(times_practiced=models.F('times_practiced') + 1)

    return redirect('take_assignment', sa_pk=sa.pk)


# ---- Student Analytics ----

@login_required
def student_analytics(request):
    if not request.user.is_student:
        return redirect('instructor_dashboard')

    answers = StudentAnswer.objects.filter(
        student_assignment__student=request.user,
        student_assignment__status='COMPLETED',
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
    chapter_accuracy = [
        round(chapter_stats[k]['correct'] / chapter_stats[k]['total'] * 100)
        for k in chapter_labels
    ]

    # Per-difficulty accuracy
    diff_stats = {1: {'correct': 0, 'total': 0}, 2: {'correct': 0, 'total': 0}, 3: {'correct': 0, 'total': 0}}
    for ans in answers:
        d = ans.question.difficulty
        diff_stats[d]['total'] += 1
        if ans.is_correct:
            diff_stats[d]['correct'] += 1

    diff_labels = ['Easy (1)', 'Medium (2)', 'Hard (3)']
    diff_accuracy = [
        round(diff_stats[d]['correct'] / diff_stats[d]['total'] * 100)
        if diff_stats[d]['total'] > 0 else 0
        for d in [1, 2, 3]
    ]

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
    skill_accuracy = [
        round(skill_stats[s]['correct'] / skill_stats[s]['total'] * 100)
        for s in skill_labels
    ]

    # Progress over time
    completed_sas = StudentAssignment.objects.filter(
        student=request.user, status='COMPLETED',
    ).order_by('completed_at')

    progress_labels = [sa.assignment.title[:20] for sa in completed_sas]
    progress_scores = [
        round(sa.score / sa.max_score * 100) if sa.max_score > 0 and sa.score is not None else 0
        for sa in completed_sas
    ]

    # Avg time
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


# ---- Messages ----

@login_required
def student_messages(request):
    """Student: send messages and see inbox (replies + announcements)."""
    if not request.user.is_student:
        return redirect('instructor_dashboard')

    if request.method == 'POST':
        subject = request.POST.get('subject', '').strip()
        body = request.POST.get('body', '').strip()
        if subject and body:
            Message.objects.create(
                sender=request.user, subject=subject, body=body,
                message_type='DM',
            )
            messages.success(request, 'Message sent to instructor.')
        else:
            messages.error(request, 'Please fill in both subject and message.')
        return redirect('student_messages')

    # Sent messages + replies to them
    sent = Message.objects.filter(
        sender=request.user, message_type='DM',
    ).prefetch_related('replies__sender')

    # Messages received: replies to my DMs + announcements
    inbox = Message.objects.filter(
        models.Q(recipient=request.user, message_type='REPLY') |
        models.Q(message_type='ANNOUNCEMENT')
    ).select_related('sender').order_by('-created_at')

    unread_count = inbox.filter(is_read=False).count()

    # Mark inbox messages as read when viewing
    if request.GET.get('tab') == 'inbox':
        inbox.filter(is_read=False).update(is_read=True)
        unread_count = 0

    return render(request, 'assignments/student/messages.html', {
        'sent': sent,
        'inbox': inbox,
        'unread_count': unread_count,
        'active_tab': request.GET.get('tab', 'inbox'),
    })


@login_required
def instructor_messages(request):
    """Instructor: view student messages, reply, send announcements."""
    if not request.user.is_instructor:
        return redirect('student_dashboard')

    if request.method == 'POST':
        action = request.POST.get('action', '')

        if action == 'reply':
            parent_id = request.POST.get('parent_id')
            body = request.POST.get('body', '').strip()
            parent = get_object_or_404(Message, id=parent_id)
            if body:
                Message.objects.create(
                    sender=request.user,
                    recipient=parent.sender,
                    subject=f'Re: {parent.subject}',
                    body=body,
                    message_type='REPLY',
                    parent=parent,
                )
                parent.is_read = True
                parent.save(update_fields=['is_read'])
                messages.success(request, f'Reply sent to {parent.sender.get_full_name() or parent.sender.username}.')

        elif action == 'announce':
            subject = request.POST.get('subject', '').strip()
            body = request.POST.get('body', '').strip()
            if subject and body:
                Message.objects.create(
                    sender=request.user,
                    subject=subject,
                    body=body,
                    message_type='ANNOUNCEMENT',
                )
                messages.success(request, 'Announcement sent to all students.')
            else:
                messages.error(request, 'Please fill in both subject and message.')

        elif action == 'mark_read':
            msg_id = request.POST.get('message_id')
            Message.objects.filter(id=msg_id).update(is_read=True)

        return redirect('instructor_messages')

    student_messages_qs = Message.objects.filter(
        message_type='DM',
    ).select_related('sender').prefetch_related('replies__sender').order_by('-created_at')

    announcements = Message.objects.filter(
        message_type='ANNOUNCEMENT',
    ).select_related('sender').order_by('-created_at')

    unread_count = student_messages_qs.filter(is_read=False).count()

    return render(request, 'assignments/instructor/messages.html', {
        'student_messages': student_messages_qs,
        'announcements': announcements,
        'unread_count': unread_count,
        'active_tab': request.GET.get('tab', 'messages'),
    })


# ---- Export Grades ----

@login_required
def export_grades(request):
    """Export grading sheet as CSV for all students and completed assignments."""
    if not request.user.is_staff_role:
        return redirect('student_dashboard')

    import csv
    from django.http import HttpResponse

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="grades.csv"'
    writer = csv.writer(response)

    # Get all instructor-created assignments (exclude student practice)
    assignments = Assignment.objects.exclude(
        created_by__role='STUDENT'
    ).order_by('created_at')

    # Header row
    header = ['Student ID', 'Username', 'Full Name']
    for a in assignments:
        header.append(f'{a.title} (/{a.num_questions})')
    header.append('Total Score')
    header.append('Total Possible')
    header.append('Percentage')
    writer.writerow(header)

    # Data rows
    students = User.objects.filter(role='STUDENT').order_by('last_name', 'first_name')
    for student in students:
        row = [student.student_id, student.username, student.get_full_name()]
        total_score = 0
        total_possible = 0
        for a in assignments:
            sa = StudentAssignment.objects.filter(
                student=student, assignment=a, status='COMPLETED'
            ).first()
            if sa and sa.score is not None:
                row.append(sa.score)
                total_score += sa.score
                total_possible += sa.max_score
            else:
                row.append('')
                total_possible += a.num_questions
        row.append(total_score)
        row.append(total_possible)
        row.append(f'{total_score / total_possible * 100:.1f}%' if total_possible > 0 else '')
        writer.writerow(row)

    return response


@login_required
def instructor_analyze(request):
    if not request.user.is_instructor:
        return redirect('student_dashboard')

    all_assignments = Assignment.objects.filter(
        is_published=True, mode='ASSIGNMENT',
    ).exclude(created_by__role='STUDENT').order_by('created_at')

    all_students = User.objects.filter(role='STUDENT').order_by('last_name', 'first_name')

    if request.method == 'POST':
        selected_assignment_ids = request.POST.getlist('assignment_ids')
        selected_student_ids = request.POST.getlist('student_ids')
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
                row.append('\u2014')
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
