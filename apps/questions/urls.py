from django.urls import path
from . import views

urlpatterns = [
    path('browser/', views.question_browser, name='question_browser'),
    path('import/', views.question_import, name='question_import'),
    path('<int:pk>/edit/', views.question_edit, name='question_edit'),
    path('backup/', views.database_backup, name='database_backup'),
    path('restore/', views.database_restore, name='database_restore'),
    path('sections/<int:chapter_id>/', views.sections_for_chapter, name='sections_for_chapter'),
]
