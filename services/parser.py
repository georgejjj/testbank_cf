"""
Parser for textbook testbank .docx files.

Extracts questions, choices, answers, metadata, images, and tables
from Word documents in the Pearson testbank format.
"""
import re
import zipfile
from xml.etree import ElementTree as ET


# XML namespaces used in .docx
NS = {
    'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main',
    'r': 'http://schemas.openxmlformats.org/officeDocument/2006/relationships',
    'wp': 'http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing',
    'a': 'http://schemas.openxmlformats.org/drawingml/2006/main',
    'pic': 'http://schemas.openxmlformats.org/drawingml/2006/picture',
    'rel': 'http://schemas.openxmlformats.org/package/2006/relationships',
}


def extract_text_and_images(docx_path):
    """
    Extract ordered text runs and images from a .docx file.

    Returns:
        text_runs: list of strings (each text run in document order)
        images: dict of {filename: bytes} for all images in word/media/
    """
    text_runs = []
    images = {}

    with zipfile.ZipFile(docx_path, 'r') as z:
        # Extract images
        for name in z.namelist():
            if name.startswith('word/media/'):
                images[name.split('/')[-1]] = z.read(name)

        # Parse document.xml
        xml_content = z.read('word/document.xml')
        root = ET.fromstring(xml_content)

        # Build relationship map (rId -> target) for image references
        rels = {}
        if 'word/_rels/document.xml.rels' in z.namelist():
            rels_xml = z.read('word/_rels/document.xml.rels')
            rels_root = ET.fromstring(rels_xml)
            for rel in rels_root.findall('{http://schemas.openxmlformats.org/package/2006/relationships}Relationship'):
                rels[rel.get('Id')] = rel.get('Target')

        # Walk body elements in order (paragraphs and tables)
        body = root.find('w:body', NS)
        for element in body:
            tag = element.tag.split('}')[-1] if '}' in element.tag else element.tag
            if tag == 'p':
                _extract_paragraph_text(element, text_runs, rels)
            elif tag == 'tbl':
                _extract_table_text(element, text_runs)

    return text_runs, images


def _extract_paragraph_text(para, text_runs, rels):
    """Extract text and image markers from a paragraph element."""
    para_texts = []
    for run in para.findall('.//w:r', NS):
        # Check for image
        drawing = run.find('.//w:drawing', NS)
        if drawing is not None:
            # Check for formula alt text (descr attribute on wp:docPr)
            doc_pr = drawing.find('.//wp:docPr', NS)
            descr = doc_pr.get('descr', '').strip() if doc_pr is not None else ''

            blip = drawing.find('.//' + '{http://schemas.openxmlformats.org/drawingml/2006/main}blip')
            if blip is not None:
                embed_id = blip.get('{http://schemas.openxmlformats.org/officeDocument/2006/relationships}embed')
                if embed_id and embed_id in rels:
                    target = rels[embed_id]
                    img_name = target.split('/')[-1]
                    if descr:
                        # Formula image — use alt text as formula marker
                        para_texts.append(f'[FORMULA:{descr}]')
                    else:
                        para_texts.append(f'[IMAGE:{img_name}]')

        # Extract text
        for t in run.findall('w:t', NS):
            if t.text:
                para_texts.append(t.text)

    if para_texts:
        text_runs.append(''.join(para_texts))


def _extract_table_text(table, text_runs):
    """Extract table content as [TABLE_START]...[TABLE_END] markers with cell text."""
    text_runs.append('[TABLE_START]')
    for row in table.findall('.//w:tr', NS):
        row_texts = []
        for cell in row.findall('w:tc', NS):
            cell_text = []
            for t in cell.findall('.//w:t', NS):
                if t.text:
                    cell_text.append(t.text)
            row_texts.append(''.join(cell_text))
        text_runs.append('\t'.join(row_texts))
    text_runs.append('[TABLE_END]')


def parse_docx(docx_path):
    """
    Parse a testbank .docx file into structured question data.

    Returns dict with:
        chapter_number: int
        chapter_title: str
        sections: list of {number, title}
        questions: list of question dicts
        images: dict of {filename: bytes}
    """
    text_runs, images = extract_text_and_images(docx_path)

    result = {
        'chapter_number': None,
        'chapter_title': '',
        'sections': [],
        'questions': [],
        'images': images,
    }

    # Parser state
    current_section = {'number': '', 'title': ''}
    current_context = None
    current_question = None
    context_is_fresh = False  # True while inside a context question group
    context_question_numbers = set()  # Track which question numbers belong to current context
    context_ending = False  # Set True at Skill:, cleared if next line is a question (keeps group going)
    state = 'IDLE'
    pre_table_state = 'IDLE'
    table_lines = []

    for line in text_runs:
        line_stripped = line.strip()
        if not line_stripped:
            continue

        # --- Chapter header ---
        ch_match = re.match(r'Chapter\s+(\d+)\s+(.*)', line_stripped)
        if ch_match and result['chapter_number'] is None:
            result['chapter_number'] = int(ch_match.group(1))
            result['chapter_title'] = ch_match.group(2).strip()
            continue

        # If context_ending is set and this line is NOT a question number,
        # the context group has ended (a gap between Skill: and next question)
        if context_ending and not re.match(r'^\d+\)\s+', line_stripped):
            context_is_fresh = False
            context_ending = False

        # --- Section header (e.g., "4.1   The Timeline") ---
        sec_match = re.match(r'^(\d+\.\d+)\s+(.*)', line_stripped)
        if sec_match and state in ('IDLE', 'METADATA'):
            sec_num = sec_match.group(1)
            sec_title = sec_match.group(2).strip()
            if sec_num.startswith(str(result.get('chapter_number', ''))):
                current_section = {'number': sec_num, 'title': sec_title}
                if not any(s['number'] == sec_num for s in result['sections']):
                    result['sections'].append(current_section.copy())
                # Clear context when entering a new section
                current_context = None
                context_is_fresh = False
                context_ending = False
                state = 'IDLE'
                continue

        # --- Context block ---
        if re.match(r'^Use the (following |figure|information|table)', line_stripped, re.IGNORECASE):
            _save_question(current_question, result)
            current_question = None
            current_context = {'text': line_stripped, 'image': ''}
            context_is_fresh = True
            context_question_numbers = set()
            state = 'CONTEXT'
            continue

        # --- Context continuation (non-question text following a context header) ---
        if state == 'CONTEXT' and current_context and not re.match(r'^\d+\)', line_stripped):
            # Append text that's part of the context scenario (not a question)
            img_match = re.search(r'\[IMAGE:([^\]]+)\]', line_stripped)
            if img_match:
                current_context['image'] = img_match.group(1)
                continue
            if line_stripped not in ('[TABLE_START]', '[TABLE_END]'):
                current_context['text'] += ' ' + line_stripped
            # Fall through to handle TABLE markers below

        # --- Image marker ---
        img_match = re.search(r'\[IMAGE:([^\]]+)\]', line_stripped)
        if img_match:
            img_name = img_match.group(1)
            # Standalone image line (only the marker, no surrounding text)
            text_without_marker = re.sub(r'\[IMAGE:[^\]]+\]', '', line_stripped).strip()
            if not text_without_marker:
                if current_context and state == 'CONTEXT':
                    current_context['image'] = img_name
                elif current_question and state in ('ANSWER', 'EXPLANATION'):
                    # Image after Answer: or Explanation: is part of the answer/explanation
                    current_question['answer_image'] = img_name
                elif current_question:
                    current_question['image'] = img_name
                continue
            # Inline image — keep marker in text, will be converted to <img>
            # during import when chapter number is known. Fall through to
            # handle as normal text (explanation, question continuation, etc.)

        # --- Table marker ---
        if line_stripped == '[TABLE_START]':
            pre_table_state = state
            state = 'TABLE'
            table_lines = []
            continue
        if line_stripped == '[TABLE_END]':
            table_html = _table_lines_to_html(table_lines)
            if pre_table_state == 'CONTEXT' and current_context and context_is_fresh:
                current_context['text'] += '\n' + table_html
                state = 'CONTEXT'
            elif pre_table_state in ('ANSWER', 'QUESTION') and current_question:
                if pre_table_state == 'ANSWER':
                    current_question['answer_raw_text'] += '\n' + table_html
                else:
                    current_question['text'] += '\n' + table_html
                state = pre_table_state
            else:
                state = 'IDLE'
            continue
        if state == 'TABLE':
            table_lines.append(line_stripped)
            continue

        # --- Question number ---
        q_match = re.match(r'^(\d+)\)\s+(.*)', line_stripped)
        if q_match:
            _save_question(current_question, result)
            q_num = int(q_match.group(1))
            # If context_ending is set, the previous question's Skill: was the last metadata.
            # A new question immediately following keeps the context group alive.
            if context_ending:
                context_ending = False
            # Only attach context if it's fresh
            attach_context = current_context if context_is_fresh else None
            if attach_context:
                context_question_numbers.add(q_num)
            current_question = {
                'question_number': q_num,
                'text': q_match.group(2),
                'question_type': None,
                'choices': [],
                'correct_answer': '',
                'answer_raw_text': '',
                'explanation': '',
                'difficulty': None,
                'skill': '',
                'section_number': current_section.get('number', ''),
                'section_title': current_section.get('title', ''),
                'image': '',
                'context': attach_context.copy() if attach_context else None,
            }
            state = 'QUESTION'
            continue

        # --- MC choice ---
        choice_match = re.match(r'^([A-E])\)\s+(.*)', line_stripped)
        if choice_match and state in ('QUESTION', 'CHOICES'):
            if current_question:
                current_question['choices'].append({
                    'letter': choice_match.group(1),
                    'text': choice_match.group(2),
                })
                state = 'CHOICES'
            continue

        # --- Answer line ---
        ans_match = re.match(r'^Answer:\s*(.*)', line_stripped)
        if ans_match:
            if current_question:
                raw_answer = ans_match.group(1).strip()
                current_question['answer_raw_text'] = raw_answer
                current_question['correct_answer'] = raw_answer
                current_question['question_type'] = _detect_question_type(raw_answer, current_question['choices'])
            state = 'ANSWER'
            continue

        # --- Explanation ---
        exp_match = re.match(r'^Explanation:\s*(.*)', line_stripped)
        if exp_match and current_question:
            current_question['explanation'] = exp_match.group(1).strip()
            continue

        # --- Metadata: Diff ---
        diff_match = re.match(r'^Diff:\s*(\d)', line_stripped)
        if diff_match and current_question:
            current_question['difficulty'] = int(diff_match.group(1))
            continue

        # --- Metadata: Section ---
        sec_meta_match = re.match(r'^Section:\s*(.*)', line_stripped)
        if sec_meta_match and current_question:
            sec_text = sec_meta_match.group(1).strip()
            sec_num_match = re.match(r'^(\d+\.\d+)\s*(.*)', sec_text)
            if sec_num_match:
                current_question['section_number'] = sec_num_match.group(1)
                current_question['section_title'] = sec_num_match.group(2).strip()
            continue

        # --- Metadata: Skill ---
        skill_match = re.match(r'^Skill:\s*(\w+)', line_stripped)
        if skill_match and current_question:
            skill = skill_match.group(1)
            if skill.startswith('Anal'):
                skill = 'Analytical'
            elif skill.startswith('Concept'):
                skill = 'Conceptual'
            elif skill.startswith('Def'):
                skill = 'Definition'
            current_question['skill'] = skill
            # Mark that this question's metadata is done — context may end
            # unless the very next numbered item continues the group
            context_ending = True
            state = 'METADATA'
            continue

        # --- Continuation text ---
        if state == 'QUESTION' and current_question:
            current_question['text'] += ' ' + line_stripped
        elif state == 'ANSWER' and current_question:
            if not current_question.get('explanation'):
                current_question['explanation'] = line_stripped
            else:
                current_question['explanation'] += ' ' + line_stripped

    # Save last question
    _save_question(current_question, result)

    return result


def _detect_question_type(answer_text, choices):
    """
    Detect question type from answer text.

    Heuristic (in order):
    1. Single letter A-E with choices present -> MC
    2. Single number (with $, commas, %) -> NUMERIC
    3. Contains = followed by trailing number -> NUMERIC
    4. Otherwise -> FREE_RESPONSE
    """
    answer_text = answer_text.strip()

    # 1. Single letter A-E
    if re.match(r'^[A-E]$', answer_text) and choices:
        return 'MC'

    # 2. Single number
    cleaned = re.sub(r'[\$,% ]', '', answer_text)
    try:
        float(cleaned)
        return 'NUMERIC'
    except ValueError:
        pass

    # 3. Contains = with trailing number
    trailing_match = re.search(r'=\s*[\$]?[\-]?[\d,]+\.?\d*\s*$', answer_text)
    if trailing_match:
        return 'NUMERIC'

    # 4. Otherwise
    return 'FREE_RESPONSE'


def extract_numeric_value(answer_text):
    """
    Extract the numeric value from an answer string.

    Tries:
    1. Parse the whole string as a number
    2. Extract the number after the last '='
    """
    cleaned = re.sub(r'[\$,% ]', '', answer_text.strip())
    try:
        return float(cleaned)
    except ValueError:
        pass

    # Try after last '='
    eq_match = re.search(r'=\s*[\$]?[\-]?([\d,]+\.?\d*)\s*$', answer_text)
    if eq_match:
        cleaned = re.sub(r'[\$, ]', '', eq_match.group(1))
        try:
            return float(cleaned)
        except ValueError:
            pass

    return None


def _save_question(question, result):
    """Save a completed question dict to the result list."""
    if question and question.get('question_number'):
        if question['difficulty'] is None:
            question['difficulty'] = 1
        # If answer has an image, append it to answer_raw_text
        if question.get('answer_image'):
            img_tag = f'[IMAGE:{question["answer_image"]}]'
            if question['answer_raw_text']:
                question['answer_raw_text'] += ' ' + img_tag
            else:
                question['answer_raw_text'] = img_tag
        result['questions'].append(question)


def _table_lines_to_html(table_lines):
    """Convert tab-separated table lines to HTML table."""
    if not table_lines:
        return ''
    html = '<table class="table table-sm table-bordered">'
    for i, line in enumerate(table_lines):
        cells = line.split('\t')
        tag = 'th' if i == 0 else 'td'
        html += '<tr>'
        for cell in cells:
            html += f'<{tag}>{cell}</{tag}>'
        html += '</tr>'
    html += '</table>'
    return html
