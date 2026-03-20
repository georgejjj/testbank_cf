from django.db import models


class Chapter(models.Model):
    number = models.IntegerField()
    title = models.CharField(max_length=200)
    textbook = models.CharField(max_length=200, default="Corporate Finance 6e")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['number']
        unique_together = [['textbook', 'number']]

    def __str__(self):
        return f"Chapter {self.number}: {self.title}"


class Section(models.Model):
    chapter = models.ForeignKey(Chapter, on_delete=models.CASCADE, related_name='sections')
    number = models.CharField(max_length=20)
    title = models.CharField(max_length=200)
    sort_order = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['sort_order']
        unique_together = [['chapter', 'number']]

    def __str__(self):
        return f"{self.number} {self.title}"


class ContextGroup(models.Model):
    text = models.TextField()
    image = models.CharField(max_length=500, blank=True, default='')
    section = models.ForeignKey(Section, on_delete=models.CASCADE, related_name='context_groups', null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.text[:80]


class Question(models.Model):
    QUESTION_TYPES = [('MC', 'Multiple Choice'), ('NUMERIC', 'Numeric'), ('FREE_RESPONSE', 'Free Response')]
    SKILL_CHOICES = [('Conceptual', 'Conceptual'), ('Definition', 'Definition'), ('Analytical', 'Analytical')]

    section = models.ForeignKey(Section, on_delete=models.CASCADE, related_name='questions')
    question_type = models.CharField(max_length=15, choices=QUESTION_TYPES)
    text = models.TextField()
    difficulty = models.IntegerField(choices=[(1, '1'), (2, '2'), (3, '3')])
    skill = models.CharField(max_length=20, choices=SKILL_CHOICES)
    explanation = models.TextField(blank=True, default='')
    image = models.CharField(max_length=500, blank=True, default='')
    context_group = models.ForeignKey(ContextGroup, on_delete=models.SET_NULL, null=True, blank=True, related_name='questions')
    question_number = models.IntegerField()  # Original number from Word file (per-section, not unique across chapters)
    global_number = models.IntegerField(default=0)  # Unique sequential number within a chapter (set during import)
    answer_raw_text = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [['section', 'question_number']]
        ordering = ['global_number']

    @property
    def uid(self):
        """Unique human-readable ID like CH4-037."""
        ch_num = self.section.chapter.number
        return f"CH{ch_num}-{self.global_number:03d}"

    def __str__(self):
        return f"{self.uid}: {self.text[:60]}"


class MCChoice(models.Model):
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name='choices')
    letter = models.CharField(max_length=1)
    text = models.TextField()
    is_correct = models.BooleanField(default=False)

    class Meta:
        ordering = ['letter']

    def __str__(self):
        return f"{self.letter}) {self.text[:40]}"


class NumericAnswer(models.Model):
    question = models.OneToOneField(Question, on_delete=models.CASCADE, related_name='numeric_answer')
    value = models.DecimalField(max_digits=20, decimal_places=4)
    tolerance_percent = models.DecimalField(max_digits=5, decimal_places=2, default=1.0)
    absolute_tolerance = models.DecimalField(max_digits=10, decimal_places=4, default=0.01)

    def __str__(self):
        return f"{self.value} (±{self.tolerance_percent}%)"
