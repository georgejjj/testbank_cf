from django.contrib import admin
from .models import Assignment, StudentAssignment, StudentAnswer, MistakeEntry


@admin.register(Assignment)
class AssignmentAdmin(admin.ModelAdmin):
    list_display = ['title', 'mode', 'is_published', 'num_questions', 'due_date', 'created_by']
    list_filter = ['mode', 'is_published']


@admin.register(StudentAssignment)
class StudentAssignmentAdmin(admin.ModelAdmin):
    list_display = ['student', 'assignment', 'status', 'score', 'max_score']
    list_filter = ['status']
