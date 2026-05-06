import os
import re
from django.db import models
from django.core.management.base import BaseCommand
from django.conf import settings
from questions.models import Chapter, Section, ContextGroup, Question, MCChoice, NumericAnswer
from services.parser import parse_docx, extract_numeric_value


def _inline_images(text, chapter_number):
    """Convert [IMAGE:filename] markers in text to <img> tags."""
    return re.sub(
        r'\[IMAGE:([^\]]+)\]',
        rf'<img src="/media/questions/ch{chapter_number}/\1" class="img-fluid" style="max-height:2em;vertical-align:middle;">',
        text,
    )


_GREEK = [
    ('β', r'\beta '),
    ('α', r'\alpha '),
    ('σ', r'\sigma '),
    ('Σ', r'\Sigma '),
    ('μ', r'\mu '),
    ('ρ', r'\rho '),
    ('δ', r'\delta '),
    ('Δ', r'\Delta '),
    ('γ', r'\gamma '),
    ('θ', r'\theta '),
    ('π', r'\pi '),
    ('Ṝ', r'\bar{R}'),
]


def _find_matching_close(s, open_pos):
    """Given '(' at open_pos in s, return index of matching ')', or -1."""
    if open_pos >= len(s) or s[open_pos] != '(':
        return -1
    depth = 0
    for i in range(open_pos, len(s)):
        if s[i] == '(':
            depth += 1
        elif s[i] == ')':
            depth -= 1
            if depth == 0:
                return i
    return -1


def _find_top_level_slash(s):
    """Position of the first '/' at paren/brace depth 0, else None."""
    depth_p = depth_b = 0
    for i, c in enumerate(s):
        if c == '(': depth_p += 1
        elif c == ')': depth_p -= 1
        elif c == '{': depth_b += 1
        elif c == '}': depth_b -= 1
        elif c == '/' and depth_p == 0 and depth_b == 0:
            return i
    return None


def _is_balanced_outer_parens(s):
    if not (s.startswith('(') and s.endswith(')')):
        return False
    depth = 0
    for i, c in enumerate(s):
        if c == '(': depth += 1
        elif c == ')': depth -= 1
        if depth == 0 and i < len(s) - 1:
            return False
        if depth < 0:
            return False
    return depth == 0


def _strip_redundant_outer_parens(s):
    while _is_balanced_outer_parens(s):
        s = s[1:-1].strip()
    return s


def _convert_fractions(s):
    """If s (after stripping redundant outer parens) has a top-level /, return \\frac{NUM}{DEN}."""
    s = s.strip()
    inner = _strip_redundant_outer_parens(s)
    slash = _find_top_level_slash(inner)
    if slash is not None:
        num = inner[:slash].strip()
        den = inner[slash + 1:].strip()
        return r'\frac{' + _maybe_recurse_frac(num) + r'}{' + _maybe_recurse_frac(den) + r'}'
    return s


def _maybe_recurse_frac(s):
    s = s.strip()
    inner = _strip_redundant_outer_parens(s)
    if _find_top_level_slash(inner) is not None:
        return _convert_fractions(s)
    return inner


def _convert_with_sub_sup(s):
    """Find " with subscript (Y)" / " with superscript (Y)" and convert, with balanced base."""
    pat = re.compile(r'\s+with\s+(subscript|superscript)\s+\(')
    while True:
        m = pat.search(s)
        if not m:
            break
        # Locate balanced (Y) starting at the '(' captured at m.end()-1
        y_open = m.end() - 1
        y_close = _find_matching_close(s, y_open)
        # The base must end with ')' immediately before m.start()
        if y_close < 0 or m.start() == 0 or s[m.start() - 1] != ')':
            # Malformed; skip by neutralizing this occurrence
            s = s[:m.start()] + '\x00WITH\x00' + s[m.end():]
            continue
        x_close = m.start() - 1
        # Find matching '(' for that ')'
        depth = 0
        x_open = -1
        for i in range(x_close, -1, -1):
            if s[i] == ')':
                depth += 1
            elif s[i] == '(':
                depth -= 1
                if depth == 0:
                    x_open = i
                    break
        if x_open < 0:
            s = s[:m.start()] + '\x00WITH\x00' + s[m.end():]
            continue
        x = s[x_open + 1:x_close]
        y = s[y_open + 1:y_close]
        op = '_' if m.group(1) == 'subscript' else '^'
        # Recursively convert nested constructs in x and y first
        x = _convert_with_sub_sup(x)
        y = _convert_with_sub_sup(y)
        # Preserve parens around base if it contains an operator or nested parens
        if any(c in x for c in '+-*/(),') or x != x.strip():
            base = '(' + x + ')'
        else:
            base = x
        repl = base + op + '{' + y + '}'
        s = s[:x_open] + repl + s[y_close + 1:]
    return s.replace('\x00WITH\x00', ' with ')


def _convert_sqrt(s):
    """square root of (X) with balanced X -> \\sqrt{X}."""
    pat = re.compile(r'square\s+root\s+of\s+\(')
    out = []
    i = 0
    while i < len(s):
        m = pat.match(s, i)
        if m:
            open_pos = m.end() - 1
            close_pos = _find_matching_close(s, open_pos)
            if close_pos > 0:
                inner = s[open_pos + 1:close_pos]
                inner = _strip_redundant_outer_parens(inner)
                inner = _convert_fractions(inner)
                out.append(r'\sqrt{' + inner + '}')
                i = close_pos + 1
                continue
        out.append(s[i])
        i += 1
    return ''.join(out)


def _convert_sum(s):
    """sum of (X) from (a) to (b) -> \\sum_{a}^{b} X (X balanced)."""
    pat = re.compile(r'sum\s+of\s+\(')
    out = []
    i = 0
    while i < len(s):
        m = pat.match(s, i)
        if m:
            open_pos = m.end() - 1
            close_pos = _find_matching_close(s, open_pos)
            if close_pos > 0:
                body = s[open_pos + 1:close_pos]
                rest = s[close_pos + 1:]
                fm = re.match(r'\s+from\s+\(([^()]+)\)\s+to\s+\(([^()]+)\)', rest)
                if fm:
                    a = fm.group(1)
                    b = fm.group(2)
                    body_s = _strip_redundant_outer_parens(body)
                    body_s = _convert_fractions(body_s)
                    out.append(r'\sum_{' + a + r'}^{' + b + r'} ' + body_s)
                    i = close_pos + 1 + fm.end()
                    continue
                # Bare "sum of (X)"
                body_s = _strip_redundant_outer_parens(body)
                body_s = _convert_fractions(body_s)
                out.append(r'\sum ' + body_s)
                i = close_pos + 1
                continue
        out.append(s[i])
        i += 1
    return ''.join(out)


def _convert_to_root(s):
    """(X) to the (N) root -> \\sqrt[N]{X} (X balanced)."""
    out = []
    i = 0
    while i < len(s):
        if s[i] == '(':
            close = _find_matching_close(s, i)
            if close > 0:
                rest = s[close + 1:]
                m = re.match(r'\s+to\s+the\s+\(([^()]+)\)\s+root', rest)
                if m:
                    x = s[i + 1:close]
                    n = m.group(1)
                    out.append(r'\sqrt[' + n + r']{' + x + '}')
                    i = close + 1 + m.end()
                    continue
        out.append(s[i])
        i += 1
    return ''.join(out)


def _formula_to_latex(descr):
    """Convert Word formula alt-text to LaTeX for MathJax.

    Handles:
      (X) with subscript (Y)            -> X_{Y}
      (X) with superscript (Y)          -> X^{Y}
      ((X)) with subscript (Y)          -> (X)_{Y}    (preserves outer parens)
      ((X)) with superscript (Y)        -> (X)^{Y}
      (X) superscript (Y) subscript (Z) -> X^{Y}_{Z}  (no "with")
      square root of (X)                -> \\sqrt{X}
      (X) to the (N) root               -> \\sqrt[N]{X}
      Σ is over i                        -> \\sum_{i}
      sum of (X) from (a) to (b)        -> \\sum_{a}^{b} X
      (NUM/DEN)                         -> \\frac{NUM}{DEN} (recursive)
      Greek glyphs (β, Σ, σ, ...)        -> \\beta, \\Sigma, \\sigma, ...
    """
    s = descr.strip()

    # 1) Convert (X) with subscript/superscript (Y) using balanced-paren matching.
    s = _convert_with_sub_sup(s)

    # 2) Convert "(X) superscript (Y) subscript (Z)" forms (no "with"). Iterative regex
    #    suffices here because in practice these have plain bases.
    prev = None
    while prev != s:
        prev = s
        s = re.sub(
            r'\(([^()]*)\)\s+superscript\s+\(([^()]*)\)\s+subscript\s+\(([^()]*)\)',
            r'\1^{\2}_{\3}', s)
        s = re.sub(
            r'\(([^()]*)\)\s+subscript\s+\(([^()]*)\)\s+superscript\s+\(([^()]*)\)',
            r'\1_{\2}^{\3}', s)
        s = re.sub(r'\(([^()]*)\)\s+subscript\s+\(([^()]*)\)', r'\1_{\2}', s)
        s = re.sub(r'\(([^()]*)\)\s+superscript\s+\(([^()]*)\)', r'\1^{\2}', s)

    # 3) Trailing-digit exponent: ")2020" -> ")^{2020}". Run after sub/sup conversion
    #    so structure is settled; safe because all word/letter exponent cases were
    #    already expressed as "with superscript".
    s = re.sub(r'\)(\d+)\b', r')^{\1}', s)

    # 4) square root of (X) — balanced parens.
    s = _convert_sqrt(s)

    # 5) (X) to the (N) root -> \sqrt[N]{X}
    s = _convert_to_root(s)

    # 6) sum of (X) from (a) to (b) -> \sum_{a}^{b} X
    s = _convert_sum(s)
    # Σ is over i -> \sum_{i}
    s = re.sub(r'(?:Σ|\\Sigma\s*)\s*is\s+over\s+(\w+)', r'\\sum_{\1}', s)

    # Top-level fraction: (NUM/DEN) → \frac{NUM}{DEN}
    s = _convert_fractions(s)

    # Greek glyph substitutions
    for ch, latex in _GREEK:
        s = s.replace(ch, latex)
    s = re.sub(r'  +', ' ', s)
    s = re.sub(r'\{\s+', '{', s)
    s = re.sub(r'\s+\}', '}', s)
    # Tight spacing for Greek before sub/sup
    s = re.sub(r'\\(beta|alpha|sigma|Sigma|mu|rho|delta|Delta)\s+([\^_])', r'\\\1\2', s)

    # × → \times
    s = s.replace('×', r'\times ')
    s = re.sub(r'\\times\s+', r'\\times ', s)

    # Simplify ((X))^{N} → (X)^{N} and ((X))_{N} → (X)_{N}
    prev = None
    while prev != s:
        prev = s
        s = re.sub(r'\(\(([^()]*)\)\)\^\{([^{}]*)\}', r'(\1)^{\2}', s)
        s = re.sub(r'\(\(([^()]*)\)\)_\{([^{}]*)\}', r'(\1)_{\2}', s)

    return s


def _inline_formulas(text):
    """Convert [FORMULA:...] markers in text to MathJax spans."""
    def replace_formula(m):
        latex = _formula_to_latex(m.group(1))
        return f'\\({latex}\\)'
    return re.sub(r'\[FORMULA:([^\]]+)\]', replace_formula, text)


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
                        text=_inline_formulas(ctx_text),
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
            ch_num = chapter.number
            defaults = {
                'question_type': q_type,
                'text': _inline_formulas(_inline_images(q_data['text'], ch_num)),
                'difficulty': q_data.get('difficulty', 1),
                'skill': q_data.get('skill', 'Conceptual'),
                'explanation': _inline_formulas(_inline_images(q_data.get('explanation', ''), ch_num)),
                'image': image_path,
                'context_group': context_group,
                'answer_raw_text': _inline_formulas(_inline_images(q_data.get('answer_raw_text', ''), ch_num)),
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
                        text=_inline_formulas(_inline_images(choice_data['text'], ch_num)),
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
