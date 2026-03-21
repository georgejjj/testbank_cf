from django.urls import path
from . import views

urlpatterns = [
    path('browser/', views.question_browser, name='question_browser'),
    path('import/', views.question_import, name='question_import'),
    path('<int:pk>/edit/', views.question_edit, name='question_edit'),
    path('<int:pk>/delete/', views.question_delete, name='question_delete'),
    path('clean/', views.questions_clean, name='questions_clean'),
    path('export/', views.questions_export, name='questions_export'),
    path('import-json/', views.questions_import_json, name='questions_import_json'),
    path('backup/', views.database_backup, name='database_backup'),
    path('restore/', views.database_restore, name='database_restore'),
    path('sections/<int:chapter_id>/', views.sections_for_chapter, name='sections_for_chapter'),
]
