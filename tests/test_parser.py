import os
from django.test import TestCase
from services.parser import extract_text_and_images, parse_docx

SAMPLE_DOCX = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'chapter 4.docx')


class TextExtractionTest(TestCase):
    def test_extract_text_runs(self):
        text_runs, images = extract_text_and_images(SAMPLE_DOCX)
        self.assertGreater(len(text_runs), 100)
        full_text = ' '.join(text_runs)
        self.assertIn('Corporate Finance', full_text)
        self.assertIn('Chapter 4', full_text)

    def test_extract_images(self):
        text_runs, images = extract_text_and_images(SAMPLE_DOCX)
        self.assertGreater(len(images), 0)
        for name, data in images.items():
            self.assertIsInstance(data, bytes)


class QuestionParsingTest(TestCase):
    def test_parse_chapter4(self):
        result = parse_docx(SAMPLE_DOCX)
        self.assertEqual(result['chapter_number'], 4)
        self.assertIn('Time Value of Money', result['chapter_title'])
        questions = result['questions']
        self.assertGreater(len(questions), 80)

    def test_mc_question_structure(self):
        result = parse_docx(SAMPLE_DOCX)
        q1 = result['questions'][0]
        self.assertEqual(q1['question_number'], 1)
        self.assertEqual(q1['question_type'], 'MC')
        self.assertIn('timeline', q1['text'].lower())
        self.assertEqual(len(q1['choices']), 4)
        self.assertEqual(q1['correct_answer'], 'C')
        self.assertEqual(q1['difficulty'], 1)

    def test_section_detection(self):
        result = parse_docx(SAMPLE_DOCX)
        q1 = result['questions'][0]
        self.assertIn('4.1', q1['section_number'])

    def test_question_type_detection(self):
        result = parse_docx(SAMPLE_DOCX)
        types = set(q['question_type'] for q in result['questions'])
        self.assertIn('MC', types)
        self.assertTrue(types - {'MC'})
