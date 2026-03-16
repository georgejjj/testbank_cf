from django.urls import path
from . import views

urlpatterns = [
    path('browser/', views.question_browser, name='question_browser'),
    path('import/', views.question_import, name='question_import'),
    path('sections/<int:chapter_id>/', views.sections_for_chapter, name='sections_for_chapter'),
]
