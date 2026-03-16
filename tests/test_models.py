from django.test import TestCase
from accounts.models import User
from questions.models import Chapter, Section, ContextGroup, Question, MCChoice, NumericAnswer
from assignments.models import Assignment, StudentAssignment, AssignedQuestion, StudentAnswer, MistakeEntry


class ChapterModelTest(TestCase):
    def test_create_chapter(self):
        ch = Chapter.objects.create(number=4, title="The Time Value of Money", textbook="Corporate Finance 6e")
        self.assertEqual(ch.number, 4)
        self.assertEqual(str(ch), "Chapter 4: The Time Value of Money")

    def test_create_section(self):
        ch = Chapter.objects.create(number=4, title="The Time Value of Money", textbook="Corporate Finance 6e")
        sec = Section.objects.create(chapter=ch, number="4.1", title="The Timeline", sort_order=1)
        self.assertEqual(sec.chapter, ch)
        self.assertEqual(str(sec), "4.1 The Timeline")


class QuestionModelTest(TestCase):
    def setUp(self):
        self.ch = Chapter.objects.create(number=4, title="The Time Value of Money")
        self.sec = Section.objects.create(chapter=self.ch, number="4.1", title="The Timeline", sort_order=1)

    def test_create_mc_question(self):
        q = Question.objects.create(
            section=self.sec, question_type='MC', text='Which statement is FALSE?',
            difficulty=1, skill='Conceptual', question_number=1,
        )
        MCChoice.objects.create(question=q, letter='A', text='Option A', is_correct=False)
        MCChoice.objects.create(question=q, letter='B', text='Option B', is_correct=False)
        MCChoice.objects.create(question=q, letter='C', text='Option C', is_correct=True)
        MCChoice.objects.create(question=q, letter='D', text='Option D', is_correct=False)
        self.assertEqual(q.choices.count(), 4)
        self.assertEqual(q.choices.filter(is_correct=True).first().letter, 'C')

    def test_create_numeric_question(self):
        q = Question.objects.create(
            section=self.sec, question_type='NUMERIC', text='Calculate PV',
            difficulty=2, skill='Analytical', question_number=50,
            answer_raw_text='PV = $254,641',
        )
        na = NumericAnswer.objects.create(question=q, value=254641, tolerance_percent=1.0)
        self.assertEqual(na.value, 254641)
        self.assertEqual(na.tolerance_percent, 1.0)
        self.assertEqual(na.absolute_tolerance, 0.01)

    def test_context_group(self):
        ctx = ContextGroup.objects.create(text='Use the figure below.', section=self.sec)
        q = Question.objects.create(
            section=self.sec, question_type='MC', text='Based on the figure...',
            difficulty=1, skill='Conceptual', question_number=2, context_group=ctx,
        )
        self.assertEqual(q.context_group.text, 'Use the figure below.')

    def test_question_unique_constraint(self):
        Question.objects.create(
            section=self.sec, question_type='MC', text='Q1',
            difficulty=1, skill='Conceptual', question_number=1,
        )
        with self.assertRaises(Exception):
            Question.objects.create(
                section=self.sec, question_type='MC', text='Q1 duplicate',
                difficulty=1, skill='Conceptual', question_number=1,
            )


class UserModelTest(TestCase):
    def test_create_instructor(self):
        user = User.objects.create_user(username='prof', password='test123', role='INSTRUCTOR')
        self.assertEqual(user.role, 'INSTRUCTOR')
        self.assertTrue(user.is_instructor)
        self.assertFalse(user.is_student)

    def test_create_student(self):
        user = User.objects.create_user(username='student1', password='test123', role='STUDENT', student_id='S001')
        self.assertEqual(user.role, 'STUDENT')
        self.assertTrue(user.is_student)
        self.assertEqual(user.student_id, 'S001')
        self.assertTrue(user.must_change_password)


class AssignmentModelTest(TestCase):
    def setUp(self):
        self.instructor = User.objects.create_user(username='prof', password='test', role='INSTRUCTOR')
        self.student = User.objects.create_user(username='stu1', password='test', role='STUDENT')
        self.ch = Chapter.objects.create(number=4, title="TVM")
        self.sec = Section.objects.create(chapter=self.ch, number="4.1", title="Timeline", sort_order=1)
        self.q1 = Question.objects.create(section=self.sec, question_type='MC', text='Q1', difficulty=1, skill='Conceptual', question_number=1)
        self.q2 = Question.objects.create(section=self.sec, question_type='MC', text='Q2', difficulty=2, skill='Conceptual', question_number=2)
        MCChoice.objects.create(question=self.q1, letter='A', text='Opt A', is_correct=True)
        MCChoice.objects.create(question=self.q1, letter='B', text='Opt B', is_correct=False)

    def test_create_assignment(self):
        a = Assignment.objects.create(title='HW1', created_by=self.instructor, num_questions=2, mode='ASSIGNMENT')
        a.chapters.add(self.ch)
        self.assertEqual(a.chapters.count(), 1)
        self.assertFalse(a.is_published)

    def test_student_assignment_unique(self):
        a = Assignment.objects.create(title='HW1', created_by=self.instructor, num_questions=2, mode='ASSIGNMENT')
        StudentAssignment.objects.create(student=self.student, assignment=a, max_score=2)
        with self.assertRaises(Exception):
            StudentAssignment.objects.create(student=self.student, assignment=a, max_score=2)

    def test_assigned_question_with_position(self):
        a = Assignment.objects.create(title='HW1', created_by=self.instructor, num_questions=2, mode='ASSIGNMENT')
        sa = StudentAssignment.objects.create(student=self.student, assignment=a, max_score=2)
        AssignedQuestion.objects.create(student_assignment=sa, question=self.q1, position=0)
        AssignedQuestion.objects.create(student_assignment=sa, question=self.q2, position=1)
        questions = sa.assigned_questions.order_by('assignedquestion__position')
        self.assertEqual(list(questions), [self.q1, self.q2])

    def test_student_answer(self):
        a = Assignment.objects.create(title='HW1', created_by=self.instructor, num_questions=1, mode='ASSIGNMENT')
        sa = StudentAssignment.objects.create(student=self.student, assignment=a, max_score=1)
        correct_choice = self.q1.choices.get(is_correct=True)
        ans = StudentAnswer.objects.create(
            student_assignment=sa, question=self.q1,
            selected_choice=correct_choice, is_correct=True,
            time_spent_seconds=30, server_elapsed_seconds=32,
            question_text_snapshot=self.q1.text,
        )
        self.assertTrue(ans.is_correct)

    def test_mistake_entry(self):
        me = MistakeEntry.objects.create(student=self.student, question=self.q1)
        self.assertFalse(me.is_mastered)
        self.assertEqual(me.times_practiced, 0)
