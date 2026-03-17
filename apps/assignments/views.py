import json

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import models
from django.db.models import Avg, Count, Q
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from accounts.models import User
from questions.models import Chapter, Question
from services.grader import grade_answer, recompute_score
from services.randomizer import assign_questions_to_student

from .models import (
    Assignment,
    AssignedQuestion,
    MistakeEntry,
    StudentAnswer,
    StudentAssignment,
)


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

    # Score distribution for most recent published assignment
    latest = Assignment.objects.filter(created_by=request.user, is_published=True).first()
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

        manual_ids = request.POST.getlist('manual_questions')
        if manual_ids:
            assignment.manually_selected_questions.set(manual_ids)
            assignment.num_questions = len(manual_ids)
            assignment.save()

        messages.success(request, f'Assignment "{assignment.title}" created.')
        return redirect('instructor_dashboard')

    chapters = Chapter.objects.prefetch_related('sections')
    all_questions = Question.objects.select_related('section__chapter').order_by('section__chapter__number', 'question_number')[:500]
    return render(request, 'assignments/instructor/create.html', {
        'chapters': chapters,
        'all_questions': all_questions,
    })


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


@login_required
def take_assignment(request, sa_pk):
    sa = get_object_or_404(StudentAssignment, pk=sa_pk, student=request.user)

    if sa.status == 'COMPLETED':
        return redirect('assignment_result', sa_pk=sa.pk)

    if sa.status == 'NOT_STARTED':
        sa.status = 'IN_PROGRESS'
        sa.started_at = timezone.now()
        sa.save(update_fields=['status', 'started_at'])

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

    question_id = request.POST.get('question_id')
    question = get_object_or_404(Question, id=question_id)
    time_spent = int(request.POST.get('time_spent', 0))
    question_idx = request.POST.get('question_idx', 0)

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

    if answer.is_correct is False:
        MistakeEntry.objects.get_or_create(student=request.user, question=question)

    recompute_score(sa)

    return redirect(f'/assignments/take/{sa.pk}/?q={question_idx}')


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

    answers = sa.answers.select_related(
        'question', 'selected_choice'
    ).order_by('question__question_number')

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
