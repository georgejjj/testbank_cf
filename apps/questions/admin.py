from django.contrib import admin
from .models import Chapter, Section, ContextGroup, Question, MCChoice, NumericAnswer


class MCChoiceInline(admin.TabularInline):
    model = MCChoice
    extra = 0


class NumericAnswerInline(admin.StackedInline):
    model = NumericAnswer
    extra = 0


@admin.register(Chapter)
class ChapterAdmin(admin.ModelAdmin):
    list_display = ['number', 'title', 'textbook']


@admin.register(Section)
class SectionAdmin(admin.ModelAdmin):
    list_display = ['number', 'title', 'chapter', 'sort_order']
    list_filter = ['chapter']


@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    list_display = ['question_number', 'question_type', 'difficulty', 'skill', 'section']
    list_filter = ['question_type', 'difficulty', 'skill', 'section__chapter']
    search_fields = ['text']
    inlines = [MCChoiceInline, NumericAnswerInline]
