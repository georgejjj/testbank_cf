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

        # Handle context group
        context_text = request.POST.get('context_text', '').strip()
        if context_text:
            from .models import ContextGroup
            if question.context_group:
                question.context_group.text = context_text
                question.context_group.save()
            else:
                cg = ContextGroup.objects.create(text=context_text, section=question.section)
                question.context_group = cg
        else:
            question.context_group = None

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
def questions_export(request):
    """Export all questions as JSON for backup/transfer."""
    if not request.user.is_instructor:
        return redirect('student_dashboard')

    import json as json_lib
    from django.http import HttpResponse

    data = {'chapters': []}
    for chapter in Chapter.objects.prefetch_related('sections__questions__choices', 'sections__questions__context_group').all():
        ch_data = {'number': chapter.number, 'title': chapter.title, 'textbook': chapter.textbook, 'sections': []}
        for section in chapter.sections.all():
            sec_data = {'number': section.number, 'title': section.title, 'sort_order': section.sort_order, 'questions': []}
            for q in section.questions.all():
                q_data = {
                    'question_number': q.question_number,
                    'global_number': q.global_number,
                    'question_type': q.question_type,
                    'text': q.text,
                    'difficulty': q.difficulty,
                    'skill': q.skill,
                    'explanation': q.explanation,
                    'answer_raw_text': q.answer_raw_text,
                    'image': q.image,
                }
                if q.context_group:
                    q_data['context'] = {'text': q.context_group.text, 'image': q.context_group.image}
                if q.question_type == 'MC':
                    q_data['choices'] = [{'letter': c.letter, 'text': c.text, 'is_correct': c.is_correct} for c in q.choices.all()]
                if q.question_type == 'NUMERIC':
                    try:
                        na = q.numeric_answer
                        q_data['numeric_answer'] = {'value': str(na.value), 'tolerance_percent': str(na.tolerance_percent)}
                    except NumericAnswer.DoesNotExist:
                        pass
                sec_data['questions'].append(q_data)
            ch_data['sections'].append(sec_data)
        data['chapters'].append(ch_data)

    response = HttpResponse(json_lib.dumps(data, ensure_ascii=False, indent=2), content_type='application/json')
    response['Content-Disposition'] = 'attachment; filename="testbank_questions.json"'
    return response


@login_required
def questions_import_json(request):
    """Import questions from a previously exported JSON file."""
    if not request.user.is_instructor:
        return redirect('student_dashboard')

    if request.method == 'POST' and request.FILES.get('json_file'):
        import json as json_lib
        from decimal import Decimal

        try:
            data = json_lib.loads(request.FILES['json_file'].read().decode('utf-8-sig'))
        except Exception:
            messages.error(request, 'Invalid JSON file.')
            return redirect('question_browser')

        count = 0
        for ch_data in data.get('chapters', []):
            chapter, _ = Chapter.objects.update_or_create(
                number=ch_data['number'],
                defaults={'title': ch_data['title'], 'textbook': ch_data.get('textbook', 'Corporate Finance 6e')},
            )
            for sec_data in ch_data.get('sections', []):
                section, _ = Section.objects.update_or_create(
                    chapter=chapter, number=sec_data['number'],
                    defaults={'title': sec_data['title'], 'sort_order': sec_data.get('sort_order', 0)},
                )
                for q_data in sec_data.get('questions', []):
                    # Handle context
                    context_group = None
                    if q_data.get('context'):
                        from .models import ContextGroup
                        context_group, _ = ContextGroup.objects.get_or_create(
                            text=q_data['context']['text'][:200],
                            defaults={'text': q_data['context']['text'], 'image': q_data['context'].get('image', ''), 'section': section},
                        )

                    q, created = Question.objects.update_or_create(
                        section=section, question_number=q_data['question_number'],
                        defaults={
                            'global_number': q_data.get('global_number', 0),
                            'question_type': q_data['question_type'],
                            'text': q_data['text'],
                            'difficulty': q_data['difficulty'],
                            'skill': q_data['skill'],
                            'explanation': q_data.get('explanation', ''),
                            'answer_raw_text': q_data.get('answer_raw_text', ''),
                            'image': q_data.get('image', ''),
                            'context_group': context_group,
                        },
                    )
                    if q_data.get('choices'):
                        q.choices.all().delete()
                        for c in q_data['choices']:
                            MCChoice.objects.create(question=q, letter=c['letter'], text=c['text'], is_correct=c['is_correct'])
                    if q_data.get('numeric_answer'):
                        NumericAnswer.objects.update_or_create(
                            question=q,
                            defaults={'value': Decimal(q_data['numeric_answer']['value']),
                                      'tolerance_percent': Decimal(q_data['numeric_answer'].get('tolerance_percent', '1.0'))},
                        )
                    count += 1

        messages.success(request, f'Imported {count} questions from JSON.')
        return redirect('question_browser')

    return render(request, 'questions/restore.html')


@login_required
def database_backup(request):
    """Download full database backup."""
    if not request.user.is_instructor:
        return redirect('student_dashboard')

    import sqlite3 as sqlite3_lib
    db_path = str(settings.DATABASES['default']['NAME'])
    backup_path = tempfile.mktemp(suffix='.sqlite3')

    src = sqlite3_lib.connect(db_path)
    dst = sqlite3_lib.connect(backup_path)
    src.backup(dst)
    dst.close()
    src.close()

    response = FileResponse(open(backup_path, 'rb'), content_type='application/x-sqlite3')
    response['Content-Disposition'] = 'attachment; filename="testbank_full_backup.sqlite3"'
    return response


@login_required
def database_restore(request):
    """Restore full database from backup."""
    if not request.user.is_instructor:
        return redirect('student_dashboard')

    if request.method == 'POST' and request.FILES.get('backup_file'):
        backup_file = request.FILES['backup_file']

        with tempfile.NamedTemporaryFile(delete=False, suffix='.sqlite3') as tmp:
            for chunk in backup_file.chunks():
                tmp.write(chunk)
            tmp_path = tmp.name

        import sqlite3 as sqlite3_lib
        try:
            conn = sqlite3_lib.connect(tmp_path)
            cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = {row[0] for row in cursor.fetchall()}
            conn.close()
            required = {'questions_question', 'accounts_user', 'assignments_assignment'}
            if not required.issubset(tables):
                os.unlink(tmp_path)
                messages.error(request, 'Invalid backup file — missing required tables.')
                return redirect('home')
        except Exception:
            os.unlink(tmp_path)
            messages.error(request, 'Invalid file — not a valid SQLite database.')
            return redirect('home')

        from django.db import connections
        for conn_name in connections:
            connections[conn_name].close()

        db_path = str(settings.DATABASES['default']['NAME'])
        shutil.copy2(tmp_path, db_path)
        os.unlink(tmp_path)

        for ext in ['-wal', '-shm']:
            wal_path = db_path + ext
            if os.path.exists(wal_path):
                os.unlink(wal_path)

        messages.success(request, 'Database restored from backup. Please log in again.')
        return redirect('login')

    return render(request, 'questions/restore_full.html')


@login_required
def sections_for_chapter(request, chapter_id):
    sections = Section.objects.filter(chapter_id=chapter_id).order_by('sort_order')
    html = '<option value="">All Sections</option>'
    for sec in sections:
        html += f'<option value="{sec.id}">{sec.number} {sec.title}</option>'
    return JsonResponse({'html': html})
