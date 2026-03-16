from django.test import TestCase
from accounts.models import User
from questions.models import Chapter, Section, Question, MCChoice
from assignments.models import Assignment, StudentAssignment, AssignedQuestion
from services.randomizer import assign_questions_to_student, generate_choice_shuffle_map


class RandomizerTest(TestCase):
    def setUp(self):
        self.instructor = User.objects.create_user(username='prof', password='t', role='INSTRUCTOR')
        self.student = User.objects.create_user(username='stu', password='t', role='STUDENT')
        self.ch = Chapter.objects.create(number=4, title="TVM")
        self.sec = Section.objects.create(chapter=self.ch, number="4.1", title="Timeline", sort_order=1)
        self.questions = []
        for i in range(1, 11):
            q = Question.objects.create(
                section=self.sec, question_type='MC', text=f'Q{i}',
                difficulty=(i % 3) + 1, skill='Conceptual', question_number=i,
            )
            for letter in 'ABCD':
                MCChoice.objects.create(question=q, letter=letter, text=f'Opt {letter}', is_correct=(letter == 'A'))
            self.questions.append(q)

    def test_assign_manual_selection(self):
        a = Assignment.objects.create(title='HW1', created_by=self.instructor, num_questions=3, mode='ASSIGNMENT')
        a.manually_selected_questions.set(self.questions[:3])
        sa = assign_questions_to_student(a, self.student)
        self.assertEqual(sa.assigned_questions.count(), 3)
        self.assertEqual(sa.max_score, 3)

    def test_assign_auto_generate(self):
        a = Assignment.objects.create(title='HW2', created_by=self.instructor, num_questions=5, mode='ASSIGNMENT')
        a.chapters.add(self.ch)
        sa = assign_questions_to_student(a, self.student)
        self.assertEqual(sa.assigned_questions.count(), 5)

    def test_assign_with_difficulty_filter(self):
        a = Assignment.objects.create(
            title='HW3', created_by=self.instructor, num_questions=10, mode='ASSIGNMENT',
            difficulty_filter=[1],
        )
        a.chapters.add(self.ch)
        sa = assign_questions_to_student(a, self.student)
        for aq in AssignedQuestion.objects.filter(student_assignment=sa):
            self.assertEqual(aq.question.difficulty, 1)

    def test_choice_shuffle_map(self):
        shuffle_map = generate_choice_shuffle_map([self.questions[0]])
        q_id = str(self.questions[0].id)
        self.assertIn(q_id, shuffle_map)
        mapping = shuffle_map[q_id]
        self.assertEqual(len(mapping), 4)
        self.assertEqual(set(mapping.keys()), {'A', 'B', 'C', 'D'})
        self.assertEqual(set(mapping.values()), {'A', 'B', 'C', 'D'})

    def test_frozen_assignment(self):
        a = Assignment.objects.create(title='HW5', created_by=self.instructor, num_questions=5, mode='ASSIGNMENT')
        a.chapters.add(self.ch)
        sa1 = assign_questions_to_student(a, self.student)
        sa2 = assign_questions_to_student(a, self.student)
        self.assertEqual(sa1.id, sa2.id)
