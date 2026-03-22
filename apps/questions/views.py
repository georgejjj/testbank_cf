import os
import shutil
import tempfile

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import FileResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render

from .models import Chapter, ContextGroup, Section, Question, MCChoice, NumericAnswer
from services.parser import parse_docx


@login_required
def question_browser(request):
    if not request.user.is_instructor:
        return redirect('student_dashboard')

    from django.core.paginator import Paginator

    chapters = Chapter.objects.prefetch_related('sections')
    selected_chapter = request.GET.get('chapter')
    selected_section = request.GET.get('section')
    selected_difficulty = request.GET.get('difficulty')
    selected_skill = request.GET.get('skill')
    selected_type = request.GET.get('qtype')
    search = request.GET.get('q', '')
    sort_by = request.GET.get('sort', 'default')
    per_page = request.GET.get('per_page', '20')

    try:
        per_page = int(per_page)
        if per_page not in (20, 50, 100):
            per_page = 20
    except ValueError:
        per_page = 20

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

    # Sorting
    sort_options = {
        'default': ('section__chapter__number', 'global_number'),
        'difficulty': ('difficulty', 'section__chapter__number', 'global_number'),
        'difficulty_desc': ('-difficulty', 'section__chapter__number', 'global_number'),
        'section': ('section__number', 'global_number'),
        'type': ('question_type', 'section__chapter__number', 'global_number'),
        'newest': ('-created_at',),
    }
    questions = questions.order_by(*sort_options.get(sort_by, sort_options['default']))

    # Pagination
    paginator = Paginator(questions, per_page)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)

    # Build sections list for selected chapter
    sections = []
    if selected_chapter:
        sections = Section.objects.filter(chapter_id=selected_chapter).order_by('sort_order')

    filters = {
        'chapter': selected_chapter,
        'section': selected_section,
        'difficulty': selected_difficulty,
        'skill': selected_skill,
        'qtype': selected_type,
        'q': search,
        'sort': sort_by,
        'per_page': str(per_page),
    }

    if request.headers.get('HX-Request'):
        return render(request, 'questions/_question_list.html', {
            'page_obj': page_obj, 'filters': filters, 'total_count': paginator.count,
        })

    return render(request, 'questions/browser.html', {
        'chapters': chapters,
        'sections': sections,
        'page_obj': page_obj,
        'filters': filters,
        'total_count': paginator.count,
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
        context_action = request.POST.get('context_action', 'keep')
        if context_action == 'remove':
            question.context_group = None
        elif context_action == 'existing':
            cg_id = request.POST.get('context_group_id')
            if cg_id:
                question.context_group = ContextGroup.objects.filter(id=cg_id).first()
            else:
                question.context_group = None
        elif context_action == 'new':
            context_text = request.POST.get('context_text_new', '').strip()
            if context_text:
                context_text = context_text.replace('\r\n', '\n').replace('\n', '<br>')
                cg = ContextGroup.objects.create(text=context_text, section=question.section)
                question.context_group = cg
        elif context_action == 'edit':
            context_text = request.POST.get('context_text', '').strip()
            if context_text and question.context_group:
                context_text = context_text.replace('\r\n', '\n').replace('\n', '<br>')
                question.context_group.text = context_text
                question.context_group.save()

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
        return redirect(request.POST.get('return_url') or 'question_browser')

    choices = list(question.choices.all()) if question.question_type == 'MC' else []
    numeric_answer = None
    if question.question_type == 'NUMERIC':
        try:
            numeric_answer = question.numeric_answer
        except NumericAnswer.DoesNotExist:
            pass

    # Get context groups from the same chapter for the dropdown
    chapter = question.section.chapter
    context_groups = ContextGroup.objects.filter(
        section__chapter=chapter
    ).order_by('section__number', 'id')

    return render(request, 'questions/edit.html', {
        'question': question,
        'choices': choices,
        'numeric_answer': numeric_answer,
        'context_groups': context_groups,
    })


@login_required
def question_delete(request, pk):
    """Delete a single question."""
    if not request.user.is_instructor or request.method != 'POST':
        return redirect('question_browser')

    question = get_object_or_404(Question, pk=pk)
    uid = question.uid
    question.delete()
    messages.success(request, f'Question {uid} deleted.')
    return redirect('question_browser')


@login_required
def questions_clean(request):
    """Delete ALL questions, sections, chapters, and context groups."""
    if not request.user.is_instructor:
        return redirect('student_dashboard')

    if request.method == 'POST' and request.POST.get('confirm') == 'DELETE ALL':
        from .models import ContextGroup
        count = Question.objects.count()
        Question.objects.all().delete()
        MCChoice.objects.all().delete()
        NumericAnswer.objects.all().delete()
        ContextGroup.objects.all().delete()
        Section.objects.all().delete()
        Chapter.objects.all().delete()

        # Also clean media/questions/
        questions_media = os.path.join(str(settings.MEDIA_ROOT), 'questions')
        if os.path.exists(questions_media):
            shutil.rmtree(questions_media)
            os.makedirs(questions_media)

        messages.success(request, f'Deleted {count} questions and all related data. Question database is now empty.')
        return redirect('question_browser')

    return render(request, 'questions/clean.html', {
        'total_questions': Question.objects.count(),
        'total_chapters': Chapter.objects.count(),
    })


@login_required
def questions_export(request):
    """Export all questions as ZIP (JSON + media images)."""
    if not request.user.is_instructor:
        return redirect('student_dashboard')

    import json as json_lib
    import zipfile as zipfile_lib
    from django.http import HttpResponse

    # Build JSON data
    image_paths = set()
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
                if q.image:
                    image_paths.add(q.image)
                if q.context_group:
                    q_data['context'] = {'text': q.context_group.text, 'image': q.context_group.image}
                    if q.context_group.image:
                        image_paths.add(q.context_group.image)
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

    # Create ZIP in memory
    zip_path = tempfile.mktemp(suffix='.zip')
    with zipfile_lib.ZipFile(zip_path, 'w', zipfile_lib.ZIP_DEFLATED) as zf:
        # Add JSON
        zf.writestr('questions.json', json_lib.dumps(data, ensure_ascii=False, indent=2))
        # Add media images
        media_root = str(settings.MEDIA_ROOT)
        for img_path in image_paths:
            full_path = os.path.join(media_root, img_path)
            if os.path.exists(full_path):
                zf.write(full_path, os.path.join('media', img_path))

    response = FileResponse(open(zip_path, 'rb'), content_type='application/zip')
    response['Content-Disposition'] = 'attachment; filename="testbank_questions.zip"'
    return response


@login_required
def questions_import_json(request):
    """Import questions from a previously exported ZIP (JSON + media)."""
    if not request.user.is_instructor:
        return redirect('student_dashboard')

    if request.method == 'POST' and request.FILES.get('import_file'):
        import json as json_lib
        import zipfile as zipfile_lib
        from decimal import Decimal

        upload = request.FILES['import_file']

        # Save to temp
        with tempfile.NamedTemporaryFile(delete=False, suffix=upload.name[-4:]) as tmp:
            for chunk in upload.chunks():
                tmp.write(chunk)
            tmp_path = tmp.name

        try:
            # Handle both ZIP and plain JSON
            if zipfile_lib.is_zipfile(tmp_path):
                with zipfile_lib.ZipFile(tmp_path, 'r') as zf:
                    data = json_lib.loads(zf.read('questions.json').decode('utf-8'))
                    # Extract media files
                    media_root = str(settings.MEDIA_ROOT)
                    for name in zf.namelist():
                        if name.startswith('media/') and name != 'media/':
                            # Strip 'media/' prefix to get relative path
                            rel_path = name[len('media/'):]
                            dest = os.path.join(media_root, rel_path)
                            os.makedirs(os.path.dirname(dest), exist_ok=True)
                            with open(dest, 'wb') as f:
                                f.write(zf.read(name))
            else:
                # Plain JSON fallback
                with open(tmp_path, 'r', encoding='utf-8-sig') as f:
                    data = json_lib.loads(f.read())
        except Exception as e:
            os.unlink(tmp_path)
            messages.error(request, f'Failed to read file: {e}')
            return redirect('question_browser')

        os.unlink(tmp_path)

        # Import questions from JSON data
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
                    context_group = None
                    if q_data.get('context'):
                        from .models import ContextGroup
                        ctx_text = q_data['context']['text']
                        existing = ContextGroup.objects.filter(text__startswith=ctx_text[:80]).first()
                        if existing:
                            context_group = existing
                        else:
                            context_group = ContextGroup.objects.create(
                                text=ctx_text, image=q_data['context'].get('image', ''), section=section,
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

        messages.success(request, f'Imported {count} questions with media files.')
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
