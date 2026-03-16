"""
Question selection and randomization service.
"""
import random
from questions.models import Question
from assignments.models import StudentAssignment, AssignedQuestion


def assign_questions_to_student(assignment, student):
    """
    Assign questions to a student for a given assignment.

    If already assigned, returns the existing StudentAssignment.
    Otherwise, draws questions from the pool, shuffles order and choices,
    and creates a frozen StudentAssignment.
    """
    existing = StudentAssignment.objects.filter(
        student=student, assignment=assignment,
    ).first()
    if existing:
        return existing

    # Determine question pool
    manual = list(assignment.manually_selected_questions.all())

    if manual:
        pool = manual
    else:
        pool = _build_question_pool(assignment)

    # Draw questions
    num = min(assignment.num_questions, len(pool))
    if num == 0:
        # Create empty assignment
        sa = StudentAssignment.objects.create(
            student=student, assignment=assignment,
            max_score=0, status='NOT_STARTED',
        )
        return sa

    if assignment.is_randomized:
        drawn = random.sample(pool, num)
    else:
        drawn = pool[:num]

    # Generate choice shuffle map for MC questions
    mc_questions = [q for q in drawn if q.question_type == 'MC']
    shuffle_map = generate_choice_shuffle_map(mc_questions)

    # Create StudentAssignment
    sa = StudentAssignment.objects.create(
        student=student,
        assignment=assignment,
        choice_shuffle_map=shuffle_map,
        max_score=len(drawn),
        status='NOT_STARTED',
    )

    # Create AssignedQuestion entries with positions
    if assignment.is_randomized:
        random.shuffle(drawn)
    for i, question in enumerate(drawn):
        AssignedQuestion.objects.create(
            student_assignment=sa,
            question=question,
            position=i,
        )

    return sa


def _build_question_pool(assignment):
    """Build the question pool based on assignment filters."""
    qs = Question.objects.all()

    chapters = assignment.chapters.all()
    if chapters.exists():
        qs = qs.filter(section__chapter__in=chapters)

    sections = assignment.sections.all()
    if sections.exists():
        qs = qs.filter(section__in=sections)

    if assignment.difficulty_filter:
        qs = qs.filter(difficulty__in=assignment.difficulty_filter)

    if assignment.skill_filter:
        qs = qs.filter(skill__in=assignment.skill_filter)

    return list(qs)


def generate_choice_shuffle_map(mc_questions):
    """
    Generate a shuffle map for MC choice display order.

    Returns dict: {question_id_str: {original_letter: displayed_letter}}
    """
    shuffle_map = {}
    for q in mc_questions:
        choices = list(q.choices.values_list('letter', flat=True))
        shuffled = choices.copy()
        random.shuffle(shuffled)
        mapping = dict(zip(choices, shuffled))
        shuffle_map[str(q.id)] = mapping
    return shuffle_map
