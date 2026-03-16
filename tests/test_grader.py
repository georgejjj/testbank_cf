from decimal import Decimal
from django.test import TestCase
from accounts.models import User
from questions.models import Chapter, Section, Question, MCChoice, NumericAnswer
from assignments.models import Assignment, StudentAssignment, AssignedQuestion, StudentAnswer
from services.grader import grade_mc, grade_numeric, parse_numeric_input, recompute_score


class GradeMCTest(TestCase):
    def setUp(self):
        ch = Chapter.objects.create(number=4, title="TVM")
        sec = Section.objects.create(chapter=ch, number="4.1", title="Timeline", sort_order=1)
        self.q = Question.objects.create(section=sec, question_type='MC', text='Q1', difficulty=1, skill='Conceptual', question_number=1)
        self.correct = MCChoice.objects.create(question=self.q, letter='C', text='Correct', is_correct=True)
        self.wrong = MCChoice.objects.create(question=self.q, letter='A', text='Wrong', is_correct=False)

    def test_correct_mc(self):
        self.assertTrue(grade_mc(self.correct))

    def test_wrong_mc(self):
        self.assertFalse(grade_mc(self.wrong))


class GradeNumericTest(TestCase):
    def setUp(self):
        ch = Chapter.objects.create(number=4, title="TVM")
        sec = Section.objects.create(chapter=ch, number="4.1", title="Timeline", sort_order=1)
        self.q = Question.objects.create(section=sec, question_type='NUMERIC', text='Calc', difficulty=2, skill='Analytical', question_number=50)
        self.na = NumericAnswer.objects.create(question=self.q, value=Decimal('254641'), tolerance_percent=Decimal('1.0'))

    def test_exact_answer(self):
        self.assertTrue(grade_numeric(self.na, Decimal('254641')))

    def test_within_tolerance(self):
        self.assertTrue(grade_numeric(self.na, Decimal('256641')))

    def test_outside_tolerance(self):
        self.assertFalse(grade_numeric(self.na, Decimal('257641')))

    def test_zero_correct_value(self):
        q2 = Question.objects.create(
            section=self.q.section, question_type='NUMERIC', text='Zero',
            difficulty=1, skill='Analytical', question_number=99,
        )
        na_zero = NumericAnswer.objects.create(question=q2, value=Decimal('0'), absolute_tolerance=Decimal('0.01'))
        self.assertTrue(grade_numeric(na_zero, Decimal('0.005')))
        self.assertFalse(grade_numeric(na_zero, Decimal('0.02')))

    def test_parse_student_input(self):
        self.assertEqual(parse_numeric_input('$254,641'), Decimal('254641'))
        self.assertEqual(parse_numeric_input(' -1,234.56 '), Decimal('-1234.56'))
        self.assertIsNone(parse_numeric_input('not a number'))


class RecomputeScoreTest(TestCase):
    def setUp(self):
        self.instructor = User.objects.create_user(username='prof', password='t', role='INSTRUCTOR')
        self.student = User.objects.create_user(username='stu', password='t', role='STUDENT')
        ch = Chapter.objects.create(number=4, title="TVM")
        sec = Section.objects.create(chapter=ch, number="4.1", title="Timeline", sort_order=1)
        self.q1 = Question.objects.create(section=sec, question_type='MC', text='Q1', difficulty=1, skill='Conceptual', question_number=1)
        self.q2 = Question.objects.create(section=sec, question_type='MC', text='Q2', difficulty=1, skill='Conceptual', question_number=2)
        a = Assignment.objects.create(title='HW1', created_by=self.instructor, num_questions=2, mode='ASSIGNMENT')
        self.sa = StudentAssignment.objects.create(student=self.student, assignment=a, max_score=2)
        AssignedQuestion.objects.create(student_assignment=self.sa, question=self.q1, position=0)
        AssignedQuestion.objects.create(student_assignment=self.sa, question=self.q2, position=1)

    def test_recompute_score(self):
        StudentAnswer.objects.create(
            student_assignment=self.sa, question=self.q1, is_correct=True,
            time_spent_seconds=10, question_text_snapshot='Q1',
        )
        StudentAnswer.objects.create(
            student_assignment=self.sa, question=self.q2, is_correct=False,
            time_spent_seconds=10, question_text_snapshot='Q2',
        )
        score = recompute_score(self.sa)
        self.assertEqual(score, 1)
        self.sa.refresh_from_db()
        self.assertEqual(self.sa.score, 1)
