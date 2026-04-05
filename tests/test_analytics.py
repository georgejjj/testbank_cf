from django.test import TestCase
from accounts.models import User
from questions.models import Chapter, Section, Question, MCChoice
from assignments.models import Assignment, StudentAssignment, StudentAnswer, AssignedQuestion
from services.analytics import compute_analytics


class AnalyticsServiceTest(TestCase):
    def setUp(self):
        self.instructor = User.objects.create_user(
            username='prof', password='pass', role='INSTRUCTOR',
            first_name='Prof', last_name='Smith',
        )
        self.ch = Chapter.objects.create(number=4, title='Time Value of Money')
        self.sec1 = Section.objects.create(chapter=self.ch, number='4.1', title='The Timeline', sort_order=1)
        self.sec2 = Section.objects.create(chapter=self.ch, number='4.2', title='Three Rules', sort_order=2)

        self.questions = []
        for i, sec in enumerate([self.sec1, self.sec1, self.sec2, self.sec2], start=1):
            q = Question.objects.create(
                section=sec, question_type='MC', text=f'Question {i}',
                difficulty=1, skill='Conceptual', question_number=i, global_number=i,
            )
            MCChoice.objects.create(question=q, letter='A', text='Right', is_correct=True)
            MCChoice.objects.create(question=q, letter='B', text='Wrong', is_correct=False)
            self.questions.append(q)

        self.a1 = Assignment.objects.create(
            title='HW1', created_by=self.instructor, num_questions=4, mode='ASSIGNMENT', is_published=True,
        )

        # Student A: scores 3/4 (75%)
        self.student_a = User.objects.create_user(
            username='alice', password='pass', role='STUDENT',
            first_name='Alice', last_name='Adams',
        )
        sa_a = StudentAssignment.objects.create(
            student=self.student_a, assignment=self.a1,
            status='COMPLETED', score=3, max_score=4, total_time_seconds=600,
        )
        for i, q in enumerate(self.questions):
            AssignedQuestion.objects.create(student_assignment=sa_a, question=q, position=i)
            StudentAnswer.objects.create(
                student_assignment=sa_a, question=q,
                is_correct=(i < 3),
            )

        # Student B: scores 1/4 (25%)
        self.student_b = User.objects.create_user(
            username='bob', password='pass', role='STUDENT',
            first_name='Bob', last_name='Brown',
        )
        sa_b = StudentAssignment.objects.create(
            student=self.student_b, assignment=self.a1,
            status='COMPLETED', score=1, max_score=4, total_time_seconds=1200,
        )
        for i, q in enumerate(self.questions):
            AssignedQuestion.objects.create(student_assignment=sa_b, question=q, position=i)
            StudentAnswer.objects.create(
                student_assignment=sa_b, question=q,
                is_correct=(i == 0),
            )

    def test_summary_stats(self):
        result = compute_analytics([self.a1.pk], [self.student_a.pk, self.student_b.pk])
        stats = result['summary']
        self.assertAlmostEqual(stats['mean'], 50.0)
        self.assertAlmostEqual(stats['median'], 50.0)
        self.assertAlmostEqual(stats['stdev'], 35.36, places=1)
        self.assertAlmostEqual(stats['pass_rate'], 50.0)
        self.assertAlmostEqual(stats['avg_time_min'], 15.0)
        self.assertEqual(stats['highest']['name'], 'Alice Adams')
        self.assertAlmostEqual(stats['highest']['score'], 75.0)
        self.assertEqual(stats['lowest']['name'], 'Bob Brown')
        self.assertAlmostEqual(stats['lowest']['score'], 25.0)

    def test_score_distribution(self):
        result = compute_analytics([self.a1.pk], [self.student_a.pk, self.student_b.pk])
        dist = result['distribution']
        self.assertEqual(len(dist), 11)
        self.assertEqual(dist[7], 1)  # Alice 75% -> bucket 7
        self.assertEqual(dist[2], 1)  # Bob 25% -> bucket 2

    def test_student_breakdown(self):
        result = compute_analytics([self.a1.pk], [self.student_a.pk, self.student_b.pk])
        breakdown = result['student_breakdown']
        self.assertEqual(len(breakdown), 2)
        self.assertEqual(breakdown[0]['name'], 'Alice Adams')
        self.assertAlmostEqual(breakdown[0]['avg_score'], 75.0)
        self.assertEqual(breakdown[0]['completed'], 1)
        self.assertEqual(breakdown[0]['total_assignments'], 1)
        self.assertEqual(breakdown[1]['name'], 'Bob Brown')

    def test_weakest_sections(self):
        # Need 3rd student to push attempts above min threshold of 5
        student_c = User.objects.create_user(
            username='carol', password='pass', role='STUDENT',
            first_name='Carol', last_name='Clark',
        )
        sa_c = StudentAssignment.objects.create(
            student=student_c, assignment=self.a1,
            status='COMPLETED', score=2, max_score=4, total_time_seconds=900,
        )
        for i, q in enumerate(self.questions):
            AssignedQuestion.objects.create(student_assignment=sa_c, question=q, position=i)
            StudentAnswer.objects.create(
                student_assignment=sa_c, question=q,
                is_correct=(i < 2),
            )

        result = compute_analytics(
            [self.a1.pk], [self.student_a.pk, self.student_b.pk, student_c.pk]
        )
        sections = result['weakest_sections']
        self.assertGreaterEqual(len(sections), 2)
        self.assertEqual(sections[0]['section_number'], '4.2')
        self.assertAlmostEqual(sections[0]['accuracy'], 16.7, places=1)

    def test_most_missed_questions(self):
        # Need 3rd student to push attempts above min threshold of 3
        student_c = User.objects.create_user(
            username='carol2', password='pass', role='STUDENT',
            first_name='Carol', last_name='Clark',
        )
        sa_c = StudentAssignment.objects.create(
            student=student_c, assignment=self.a1,
            status='COMPLETED', score=2, max_score=4, total_time_seconds=900,
        )
        for i, q in enumerate(self.questions):
            AssignedQuestion.objects.create(student_assignment=sa_c, question=q, position=i)
            StudentAnswer.objects.create(
                student_assignment=sa_c, question=q,
                is_correct=(i < 2),
            )

        result = compute_analytics(
            [self.a1.pk], [self.student_a.pk, self.student_b.pk, student_c.pk]
        )
        questions = result['most_missed']
        # q3 (idx 3): 0/3 correct = 100% error rate
        self.assertEqual(questions[0]['uid'], 'CH4-004')
        self.assertAlmostEqual(questions[0]['error_rate'], 100.0)

    def test_filter_by_student(self):
        result = compute_analytics([self.a1.pk], [self.student_a.pk])
        self.assertAlmostEqual(result['summary']['mean'], 75.0)
        self.assertEqual(len(result['student_breakdown']), 1)

    def test_empty_selection(self):
        result = compute_analytics([], [self.student_a.pk])
        self.assertAlmostEqual(result['summary']['mean'], 0)
        self.assertEqual(result['distribution'], [0] * 11)
