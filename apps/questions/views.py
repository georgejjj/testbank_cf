import os
import shutil
import tempfile

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import FileResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render

from .models import Chapter, Section, Question, MCChoice, NumericAnswer
from services.parser import parse_docx


@login_required
def question_browser(request):
    if not request.user.is_instructor:
        return redirect('student_dashboard')

    chapters = Chapter.objects.prefetch_related('sections')
    selected_chapter = request.GET.get('chapter')
    selected_section = request.GET.get('section')
    selected_difficulty = request.GET.get('difficulty')
    selected_skill = request.GET.get('skill')
    selected_type = request.GET.get('qtype')
    search = request.GET.get('q', '')

    questions = Question.objects.select_related(
        'section__chapter', 'context_group'
    ).prefetch_related('choices')

    if selected_chapter:
        questions = questions.filter(section__chapter_id=selected_chapter)
    if selected_section:
        questions = questions.filter(section_id=selected_section)
    if selected_difficulty:
        questions = questions.filter(difficulty=selected_difficulty)
    if selected_skill:
        questions = questions.filter(skill=selected_skill)
    if selected_type:
        questions = questions.filter(question_type=selected_type)
    if search:
        questions = questions.filter(text__icontains=search)

    questions = questions[:100]

    # Build sections list for selected chapter
    sections = []
    if selected_chapter:
        sections = Section.objects.filter(chapter_id=selected_chapter).order_by('sort_order')

    if request.headers.get('HX-Request'):
        return render(request, 'questions/_question_list.html', {'questions': questions})

    return render(request, 'questions/browser.html', {
        'chapters': chapters,
        'sections': sections,
        'questions': questions,
        'filters': {
            'chapter': selected_chapter,
            'section': selected_section,
            'difficulty': selected_difficulty,
            'skill': selected_skill,
            'qtype': selected_type,
            'q': search,
        },
    })


@login_required
def question_import(request):
    """Step 1: Upload file. Step 2: Preview. Step 3: Confirm import."""
    if not request.user.is_instructor:
        return redirect('student_dashboard')

    if request.method == 'POST':
        # Step 3: Confirm import
        if request.POST.get('confirm') == 'yes':
            tmp_path = request.POST.get('tmp_path', '')
            if tmp_path and os.path.exists(tmp_path):
                try:
                    from django.core.management import call_command
                    call_command('import_testbank', tmp_path)
                    messages.success(request, 'Questions imported successfully!')
                except Exception as e:
                    messages.error(request, f'Import failed: {e}')
                finally:
                    os.unlink(tmp_path)
            else:
                messages.error(request, 'Upload expired. Please upload again.')
            return redirect('question_browser')

        # Step 2: Parse and preview
        if request.FILES.get('docx_file'):
            docx_file = request.FILES['docx_file']
            if not docx_file.name.endswith('.docx'):
                messages.error(request, 'Please upload a .docx file.')
                return redirect('question_import')

            with tempfile.NamedTemporaryFile(delete=False, suffix='.docx', dir=tempfile.gettempdir()) as tmp:
                for chunk in docx_file.chunks():
                    tmp.write(chunk)
                tmp_path = tmp.name

            try:
                result = parse_docx(tmp_path)
            except Exception as e:
                os.unlink(tmp_path)
                messages.error(request, f'Failed to parse file: {e}')
                return redirect('question_import')

            # Check for existing chapter
            existing_chapter = Chapter.objects.filter(number=result['chapter_number']).first()
            existing_count = 0
            if existing_chapter:
                existing_count = Question.objects.filter(section__chapter=existing_chapter).count()

            # Count question types
            type_counts = {'MC': 0, 'NUMERIC': 0, 'FREE_RESPONSE': 0}
            for q in result['questions']:
                qt = q.get('question_type') or 'FREE_RESPONSE'
                type_counts[qt] = type_counts.get(qt, 0) + 1

            return render(request, 'questions/import_preview.html', {
                'result': result,
                'tmp_path': tmp_path,
                'filename': docx_file.name,
                'total_questions': len(result['questions']),
                'total_images': len(result['images']),
                'total_sections': len(result['sections']),
                'type_counts': type_counts,
                'existing_chapter': existing_chapter,
                'existing_count': existing_count,
            })

    return render(request, 'questions/import.html')


@login_required
def question_edit(request, pk):
    if not request.user.is_instructor:
        return redirect('student_dashboard')

    question = get_object_or_404(Question, pk=pk)

    if request.method == 'POST':
        question.text = request.POST.get('text', question.text)
        question.question_type = request.POST.get('question_type', question.question_type)
        question.difficulty = int(request.POST.get('difficulty', question.difficulty))
        question.skill = request.POST.get('skill', question.skill)
        question.explanation = request.POST.get('explanation', '')
        question.answer_raw_text = request.POST.get('answer_raw_text', '')
        question.save()

        if question.question_type == 'MC':
            correct_letter = request.POST.get('correct_choice', '')
            letters = request.POST.getlist('choice_letter')
            texts = request.POST.getlist('choice_text')
            question.choices.all().delete()
            for letter, text in zip(letters, texts):
                if letter and text:
                    MCChoice.objects.create(
                        question=question,
                        letter=letter,
                        text=text,
                        is_correct=(letter == correct_letter),
                    )
        elif question.question_type == 'NUMERIC':
            numeric_val = request.POST.get('numeric_value', '')
            if numeric_val:
                from decimal import Decimal
                NumericAnswer.objects.update_or_create(
                    question=question,
                    defaults={'value': Decimal(numeric_val)},
                )

        messages.success(request, f'Question {question.uid} updated.')
        return redirect('question_browser')

    choices = list(question.choices.all()) if question.question_type == 'MC' else []
    numeric_answer = None
    if question.question_type == 'NUMERIC':
        try:
            numeric_answer = question.numeric_answer
        except NumericAnswer.DoesNotExist:
            pass

    return render(request, 'questions/edit.html', {
        'question': question,
        'choices': choices,
        'numeric_answer': numeric_answer,
    })


@login_required
def database_backup(request):
    """Download a backup of the SQLite database."""
    if not request.user.is_instructor:
        return redirect('student_dashboard')

    import sqlite3 as sqlite3_lib
    db_path = str(settings.DATABASES['default']['NAME'])
    backup_path = tempfile.mktemp(suffix='.sqlite3')

    # Use Python's sqlite3 backup API (safe even with WAL mode)
    src = sqlite3_lib.connect(db_path)
    dst = sqlite3_lib.connect(backup_path)
    src.backup(dst)
    dst.close()
    src.close()

    response = FileResponse(open(backup_path, 'rb'), content_type='application/x-sqlite3')
    response['Content-Disposition'] = 'attachment; filename="testbank_backup.sqlite3"'
    return response


@login_required
def database_restore(request):
    """Restore database from an uploaded backup file."""
    if not request.user.is_instructor:
        return redirect('student_dashboard')

    if request.method == 'POST' and request.FILES.get('backup_file'):
        backup_file = request.FILES['backup_file']

        # Save uploaded file to temp
        with tempfile.NamedTemporaryFile(delete=False, suffix='.sqlite3') as tmp:
            for chunk in backup_file.chunks():
                tmp.write(chunk)
            tmp_path = tmp.name

        # Validate it's a real SQLite database
        import sqlite3 as sqlite3_lib
        try:
            conn = sqlite3_lib.connect(tmp_path)
            # Check it has our tables
            cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = {row[0] for row in cursor.fetchall()}
            conn.close()

            required = {'questions_question', 'accounts_user', 'assignments_assignment'}
            if not required.issubset(tables):
                os.unlink(tmp_path)
                messages.error(request, 'Invalid backup file — missing required tables.')
                return redirect('question_browser')
        except Exception:
            os.unlink(tmp_path)
            messages.error(request, 'Invalid file — not a valid SQLite database.')
            return redirect('question_browser')

        # Close all Django DB connections before replacing
        from django.db import connections
        for conn_name in connections:
            connections[conn_name].close()

        # Replace the database file
        db_path = str(settings.DATABASES['default']['NAME'])
        shutil.copy2(tmp_path, db_path)
        os.unlink(tmp_path)

        # Remove WAL/SHM files so SQLite starts fresh
        for ext in ['-wal', '-shm']:
            wal_path = db_path + ext
            if os.path.exists(wal_path):
                os.unlink(wal_path)

        messages.success(request, 'Database restored from backup. Please log in again.')
        return redirect('login')

    return render(request, 'questions/restore.html')


@login_required
def sections_for_chapter(request, chapter_id):
    sections = Section.objects.filter(chapter_id=chapter_id).order_by('sort_order')
    html = '<option value="">All Sections</option>'
    for sec in sections:
        html += f'<option value="{sec.id}">{sec.number} {sec.title}</option>'
    return JsonResponse({'html': html})
