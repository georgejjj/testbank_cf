"""
Auto-grading service for MC and numeric questions.
"""
import re
from decimal import Decimal, InvalidOperation


def grade_mc(selected_choice):
    """Grade a multiple choice answer. Returns True if correct."""
    return selected_choice.is_correct


def grade_numeric(numeric_answer, student_value):
    """
    Grade a numeric answer with tolerance.

    If correct value is zero: use absolute_tolerance.
    Otherwise: use tolerance_percent (stored as human-readable, e.g. 1.0 = 1%).
    """
    correct = numeric_answer.value

    if abs(correct) > 0:
        tolerance = numeric_answer.tolerance_percent / Decimal('100')
        return abs(student_value - correct) / abs(correct) <= tolerance
    else:
        return abs(student_value - correct) <= numeric_answer.absolute_tolerance


def parse_numeric_input(raw_input):
    """
    Parse student's numeric input string into Decimal.

    Strips: $, commas, spaces, % signs.
    Returns None if parsing fails.
    """
    if not raw_input:
        return None
    cleaned = re.sub(r'[\$,% ]', '', str(raw_input).strip())
    try:
        return Decimal(cleaned)
    except (InvalidOperation, ValueError):
        return None


def grade_answer(student_answer):
    """
    Grade a StudentAnswer object based on question type.

    Returns bool or None (for FREE_RESPONSE).
    Updates student_answer.is_correct in place (does not save).
    """
    question = student_answer.question

    if question.question_type == 'MC':
        if student_answer.selected_choice:
            student_answer.is_correct = grade_mc(student_answer.selected_choice)
        else:
            student_answer.is_correct = False

    elif question.question_type == 'NUMERIC':
        try:
            numeric_answer = question.numeric_answer
        except Exception:
            student_answer.is_correct = None
            return student_answer.is_correct

        student_value = parse_numeric_input(student_answer.numeric_answer)
        if student_value is not None:
            student_answer.is_correct = grade_numeric(numeric_answer, student_value)
        else:
            student_answer.is_correct = False

    else:  # FREE_RESPONSE
        student_answer.is_correct = None

    return student_answer.is_correct


def recompute_score(student_assignment):
    """
    Recompute score for a StudentAssignment.

    Score = count of answers where is_correct is True.
    Updates and saves the StudentAssignment.
    """
    correct_count = student_assignment.answers.filter(is_correct=True).count()
    student_assignment.score = correct_count
    student_assignment.save(update_fields=['score', 'updated_at'])
    return correct_count
