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

    db_path = settings.DATABASES['default']['NAME']
    # Create a safe backup copy
    backup_path = tempfile.mktemp(suffix='.sqlite3')
    os.system(f'sqlite3 "{db_path}" ".backup \'{backup_path}\'"')

    response = FileResponse(open(backup_path, 'rb'), content_type='application/x-sqlite3')
    response['Content-Disposition'] = 'attachment; filename="testbank_backup.sqlite3"'

    # Clean up after response is sent
    response._backup_path = backup_path
    return response


@login_required
def sections_for_chapter(request, chapter_id):
    sections = Section.objects.filter(chapter_id=chapter_id).order_by('sort_order')
    html = '<option value="">All Sections</option>'
    for sec in sections:
        html += f'<option value="{sec.id}">{sec.number} {sec.title}</option>'
    return JsonResponse({'html': html})
