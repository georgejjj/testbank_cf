import os
from django.db import models
from django.core.management.base import BaseCommand
from django.conf import settings
from questions.models import Chapter, Section, ContextGroup, Question, MCChoice, NumericAnswer
from services.parser import parse_docx, extract_numeric_value


class Command(BaseCommand):
    help = 'Import questions from a testbank .docx file'

    def add_arguments(self, parser):
        parser.add_argument('path', help='Path to .docx file or directory of .docx files')
        parser.add_argument('--dir', action='store_true', help='Treat path as directory, import all .docx files')

    def handle(self, *args, **options):
        path = options['path']

        if options['dir'] or os.path.isdir(path):
            files = sorted(
                os.path.join(path, f) for f in os.listdir(path)
                if f.endswith('.docx') and not f.startswith('~')
            )
        else:
            files = [path]

        for filepath in files:
            self.stdout.write(f'Importing {filepath}...')
            self._import_file(filepath)

    def _import_file(self, filepath):
        result = parse_docx(filepath)

        if not result['chapter_number']:
            self.stderr.write(f'  Could not detect chapter number in {filepath}')
            return

        # Create or update chapter
        chapter, _ = Chapter.objects.update_or_create(
            number=result['chapter_number'],
            defaults={'title': result['chapter_title']},
        )

        # Create sections
        section_map = {}
        for i, sec_data in enumerate(result['sections']):
            section, _ = Section.objects.update_or_create(
                chapter=chapter,
                number=sec_data['number'],
                defaults={
                    'title': sec_data['title'],
                    'sort_order': i,
                },
            )
            section_map[sec_data['number']] = section

        # Extract images to media
        media_dir = os.path.join(settings.MEDIA_ROOT, 'questions', f'ch{chapter.number}')
        os.makedirs(media_dir, exist_ok=True)
        for img_name, img_data in result['images'].items():
            img_path = os.path.join(media_dir, img_name)
            with open(img_path, 'wb') as f:
                f.write(img_data)

        # Import questions
        # Determine starting global_number (for appending to existing chapters)
        existing_max = Question.objects.filter(section__chapter=chapter).aggregate(
            max_gn=models.Max('global_number')
        )['max_gn'] or 0
        global_counter = existing_max  # Will increment before assigning

        counts = {'MC': 0, 'NUMERIC': 0, 'FREE_RESPONSE': 0}
        warnings = 0
        context_cache = {}

        for q_data in result['questions']:
            # Find section
            sec_num = q_data.get('section_number', '')
            section = section_map.get(sec_num)
            if not section:
                # Try prefix match
                for key in section_map:
                    if sec_num and sec_num.startswith(key[:3]):
                        section = section_map[key]
                        break
            if not section:
                section = Section.objects.filter(chapter=chapter).first()
                if not section:
                    self.stderr.write(f'  Warning: No section for Q{q_data["question_number"]}, skipping')
                    warnings += 1
                    continue

            # Handle context group
            context_group = None
            if q_data.get('context'):
                ctx_text = q_data['context']['text']
                ctx_key = ctx_text[:500]
                if ctx_key not in context_cache:
                    ctx_image = q_data['context'].get('image', '')
                    if ctx_image:
                        ctx_image = f'questions/ch{chapter.number}/{ctx_image}'
                    context_group = ContextGroup.objects.create(
                        text=ctx_text,
                        image=ctx_image,
                        section=section,
                    )
                    context_cache[ctx_key] = context_group
                else:
                    context_group = context_cache[ctx_key]

            # Image path
            image_path = ''
            if q_data.get('image'):
                image_path = f'questions/ch{chapter.number}/{q_data["image"]}'

            # Create or update question
            q_type = q_data.get('question_type') or 'FREE_RESPONSE'
            defaults = {
                'question_type': q_type,
                'text': q_data['text'],
                'difficulty': q_data.get('difficulty', 1),
                'skill': q_data.get('skill', 'Conceptual'),
                'explanation': q_data.get('explanation', ''),
                'image': image_path,
                'context_group': context_group,
                'answer_raw_text': q_data.get('answer_raw_text', ''),
            }
            # Only assign global_number for new questions — preserve existing UIDs
            existing_q = Question.objects.filter(
                section=section, question_number=q_data['question_number']
            ).first()
            if existing_q is None:
                global_counter += 1
                defaults['global_number'] = global_counter
            question, created = Question.objects.update_or_create(
                section=section,
                question_number=q_data['question_number'],
                defaults=defaults,
            )

            # Create MC choices
            if q_type == 'MC' and q_data.get('choices'):
                if not created:
                    question.choices.all().delete()
                correct_letter = q_data.get('correct_answer', '')
                for choice_data in q_data['choices']:
                    MCChoice.objects.create(
                        question=question,
                        letter=choice_data['letter'],
                        text=choice_data['text'],
                        is_correct=(choice_data['letter'] == correct_letter),
                    )

            # Create numeric answer
            elif q_type == 'NUMERIC':
                numeric_val = extract_numeric_value(q_data.get('answer_raw_text', ''))
                if numeric_val is not None:
                    NumericAnswer.objects.update_or_create(
                        question=question,
                        defaults={'value': numeric_val},
                    )
                else:
                    question.question_type = 'FREE_RESPONSE'
                    question.save()
                    q_type = 'FREE_RESPONSE'

            counts[q_type] = counts.get(q_type, 0) + 1

        total = sum(counts.values())
        self.stdout.write(self.style.SUCCESS(
            f'  Chapter {chapter.number}: {total} questions imported '
            f'({counts["MC"]} MC, {counts["NUMERIC"]} NUMERIC, {counts["FREE_RESPONSE"]} FREE_RESPONSE), '
            f'{len(result["images"])} images extracted'
            + (f', {warnings} warnings' if warnings else '')
        ))
