import os
import tempfile

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.management import call_command
from django.http import JsonResponse
from django.shortcuts import redirect, render

from .models import Chapter, Section, Question


@login_required
def question_browser(request):
    if not request.user.is_instructor:
        return redirect('student_dashboard')

    chapters = Chapter.objects.all()
    selected_chapter = request.GET.get('chapter')
    selected_difficulty = request.GET.get('difficulty')
    selected_skill = request.GET.get('skill')
    search = request.GET.get('q', '')

    questions = Question.objects.select_related(
        'section__chapter', 'context_group'
    ).prefetch_related('choices')

    if selected_chapter:
        questions = questions.filter(section__chapter_id=selected_chapter)
    if selected_difficulty:
        questions = questions.filter(difficulty=selected_difficulty)
    if selected_skill:
        questions = questions.filter(skill=selected_skill)
    if search:
        questions = questions.filter(text__icontains=search)

    questions = questions[:100]

    if request.headers.get('HX-Request'):
        return render(request, 'questions/_question_list.html', {'questions': questions})

    return render(request, 'questions/browser.html', {
        'chapters': chapters,
        'questions': questions,
        'filters': {
            'chapter': selected_chapter,
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

        with tempfile.NamedTemporaryFile(delete=False, suffix='.docx') as tmp:
            for chunk in docx_file.chunks():
                tmp.write(chunk)
            tmp_path = tmp.name

        try:
            call_command('import_testbank', tmp_path)
            messages.success(request, f'Successfully imported {docx_file.name}')
        except Exception as e:
            messages.error(request, f'Import failed: {e}')
        finally:
            os.unlink(tmp_path)

        return redirect('question_browser')

    return render(request, 'questions/import.html')


@login_required
def sections_for_chapter(request, chapter_id):
    sections = Section.objects.filter(chapter_id=chapter_id).order_by('sort_order')
    html = '<option value="">All Sections</option>'
    for sec in sections:
        html += f'<option value="{sec.id}">{sec.number} {sec.title}</option>'
    return JsonResponse({'html': html})
