from django.db import models
from django.conf import settings
from questions.models import Chapter, Section, Question, MCChoice


class Assignment(models.Model):
    MODE_CHOICES = [('PRACTICE', 'Practice'), ('ASSIGNMENT', 'Assignment')]

    title = models.CharField(max_length=200)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='created_assignments')
    chapters = models.ManyToManyField(Chapter, blank=True)
    sections = models.ManyToManyField(Section, blank=True)
    difficulty_filter = models.JSONField(default=list, blank=True)
    skill_filter = models.JSONField(default=list, blank=True)
    type_filter = models.JSONField(default=list, blank=True)
    num_questions = models.IntegerField()
    mode = models.CharField(max_length=10, choices=MODE_CHOICES)
    is_randomized = models.BooleanField(default=True)
    is_published = models.BooleanField(default=False)
    due_date = models.DateTimeField(null=True, blank=True)
    time_limit_minutes = models.IntegerField(null=True, blank=True)
    manually_selected_questions = models.ManyToManyField(Question, blank=True, related_name='manual_assignments')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.title


class StudentAssignment(models.Model):
    STATUS_CHOICES = [
        ('NOT_STARTED', 'Not Started'),
        ('IN_PROGRESS', 'In Progress'),
        ('COMPLETED', 'Completed'),
    ]

    student = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='student_assignments')
    assignment = models.ForeignKey(Assignment, on_delete=models.CASCADE, related_name='student_assignments')
    assigned_questions = models.ManyToManyField(Question, through='AssignedQuestion', related_name='student_assignments_assigned')
    choice_shuffle_map = models.JSONField(default=dict, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    score = models.IntegerField(null=True, blank=True)
    max_score = models.IntegerField(default=0)
    total_time_seconds = models.IntegerField(default=0)  # Accumulated time across all sessions
    is_late = models.BooleanField(default=False)
    status = models.CharField(max_length=15, choices=STATUS_CHOICES, default='NOT_STARTED')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [['student', 'assignment']]
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.student} - {self.assignment}"


class AssignedQuestion(models.Model):
    student_assignment = models.ForeignKey(StudentAssignment, on_delete=models.CASCADE)
    question = models.ForeignKey(Question, on_delete=models.CASCADE)
    position = models.IntegerField()

    class Meta:
        unique_together = [['student_assignment', 'question']]
        ordering = ['position']


class StudentAnswer(models.Model):
    student_assignment = models.ForeignKey(StudentAssignment, on_delete=models.CASCADE, related_name='answers')
    question = models.ForeignKey(Question, on_delete=models.CASCADE)
    selected_choice = models.ForeignKey(MCChoice, on_delete=models.SET_NULL, null=True, blank=True)
    numeric_answer = models.DecimalField(max_digits=20, decimal_places=4, null=True, blank=True)
    text_answer = models.TextField(max_length=5000, blank=True, default='')
    is_correct = models.BooleanField(null=True)
    time_spent_seconds = models.IntegerField(default=0)
    server_elapsed_seconds = models.IntegerField(default=0)
    answered_at = models.DateTimeField(auto_now=True)
    instructor_feedback = models.TextField(blank=True, default='')
    question_text_snapshot = models.TextField(default='')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [['student_assignment', 'question']]

    def __str__(self):
        return f"Answer by {self.student_assignment.student} for Q{self.question.question_number}"


class MistakeEntry(models.Model):
    student = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='mistakes')
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name='mistake_entries')
    added_at = models.DateTimeField(auto_now_add=True)
    last_practiced_at = models.DateTimeField(null=True, blank=True)
    times_practiced = models.IntegerField(default=0)
    is_mastered = models.BooleanField(default=False)

    class Meta:
        unique_together = [['student', 'question']]
        ordering = ['-added_at']


class Message(models.Model):
    TYPE_CHOICES = [('DM', 'Direct Message'), ('REPLY', 'Reply'), ('ANNOUNCEMENT', 'Announcement')]

    sender = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='sent_messages')
    recipient = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='received_messages', null=True, blank=True)
    message_type = models.CharField(max_length=12, choices=TYPE_CHOICES, default='DM')
    subject = models.CharField(max_length=200)
    body = models.TextField()
    parent = models.ForeignKey('self', on_delete=models.CASCADE, null=True, blank=True, related_name='replies')
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.sender}: {self.subject[:40]}"
