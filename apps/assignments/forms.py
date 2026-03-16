from django import forms
from .models import Assignment
from questions.models import Chapter


class AssignmentForm(forms.ModelForm):
    class Meta:
        model = Assignment
        fields = ['title', 'mode', 'num_questions', 'is_randomized', 'due_date']
        widgets = {
            'title': forms.TextInput(attrs={'class': 'form-control'}),
            'mode': forms.Select(attrs={'class': 'form-select'}),
            'num_questions': forms.NumberInput(attrs={'class': 'form-control', 'min': 1}),
            'is_randomized': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'due_date': forms.DateTimeInput(attrs={'class': 'form-control', 'type': 'datetime-local'}),
        }
