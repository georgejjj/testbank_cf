from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    ROLE_CHOICES = [('INSTRUCTOR', 'Instructor'), ('STUDENT', 'Student')]

    role = models.CharField(max_length=10, choices=ROLE_CHOICES, default='STUDENT')
    student_id = models.CharField(max_length=50, blank=True, default='')
    must_change_password = models.BooleanField(default=True)

    @property
    def is_instructor(self):
        return self.role == 'INSTRUCTOR'

    @property
    def is_student(self):
        return self.role == 'STUDENT'

    def __str__(self):
        if self.student_id:
            return f"{self.get_full_name() or self.username} ({self.student_id})"
        return self.get_full_name() or self.username
