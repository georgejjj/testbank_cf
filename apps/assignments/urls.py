from django.urls import path
from . import views

urlpatterns = [
    # Instructor
    path('instructor/', views.instructor_dashboard, name='instructor_dashboard'),
    path('create/', views.assignment_create, name='assignment_create'),
    path('<int:pk>/edit/', views.assignment_edit, name='assignment_edit'),
    path('<int:pk>/delete/', views.assignment_delete, name='assignment_delete'),
    path('<int:pk>/publish/', views.assignment_publish, name='assignment_publish'),
    path('<int:pk>/preview/', views.assignment_preview, name='assignment_preview'),
    path('<int:pk>/detail/', views.assignment_detail, name='assignment_detail'),
    path('<int:pk>/deadline/', views.assignment_update_deadline, name='assignment_update_deadline'),
    path('student/<int:sa_pk>/', views.student_detail, name='student_detail'),
    path('grade/', views.grade_free_response, name='grade_free_response'),
    path('export-grades/', views.export_grades, name='export_grades'),

    # Student
    path('dashboard/', views.student_dashboard, name='student_dashboard'),
    path('list/', views.assignment_list, name='assignment_list'),
    path('take/<int:sa_pk>/', views.take_assignment, name='take_assignment'),
    path('take/<int:sa_pk>/submit/', views.submit_answer, name='submit_answer'),
    path('take/<int:sa_pk>/complete/', views.complete_assignment, name='complete_assignment'),
    path('result/<int:sa_pk>/', views.assignment_result, name='assignment_result'),

    # Mistakes
    path('mistakes/', views.mistake_collection, name='mistake_collection'),
    path('mistakes/<int:pk>/mastered/', views.mark_mastered, name='mark_mastered'),
    path('mistakes/practice/', views.practice_mistakes, name='practice_mistakes'),

    # Analytics
    path('analytics/', views.student_analytics, name='student_analytics'),

    # Messages
    path('messages/', views.student_messages, name='student_messages'),
    path('messages/inbox/', views.instructor_messages, name='instructor_messages'),
]
