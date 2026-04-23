import uuid
from django.db import models
from django.core.validators import MinValueValidator
from django.conf import settings
from subjects.models import SectionSubject
from users.models import Student


class Quiz(models.Model):
    SECURITY_CHOICES = [
        ('normal', 'Normal'),
        ('strict', 'Strict'),
    ]
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    section_subject = models.ForeignKey(
        SectionSubject,
        on_delete=models.CASCADE,
        related_name='quizzes'
    )
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    total_points = models.FloatField(default=0.0, validators=[MinValueValidator(0.0)])
    time_limit_minutes = models.PositiveIntegerField(null=True, blank=True)
    attempt_limit = models.PositiveIntegerField(default=1)
    due_date = models.DateTimeField()
    ai_grade_on_submit = models.BooleanField(default=True)
    security_level = models.CharField(max_length=12, choices=SECURITY_CHOICES, default='normal')
    is_available = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['due_date']

    def __str__(self):
        return f"{self.title} ({self.section_subject.subject.code})"


class Question(models.Model):
    QUESTION_TYPE_CHOICES = [
        ('multiple_choice', 'Multiple Choice'),
        ('true_false', 'True/False'),
        ('essay', 'Essay'),
        ('identification', 'Identification'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    quiz = models.ForeignKey(Quiz, on_delete=models.CASCADE, related_name='questions')
    question_text = models.TextField()
    question_type = models.CharField(max_length=20, choices=QUESTION_TYPE_CHOICES, default='mcq')
    points = models.FloatField(default=1.0, validators=[MinValueValidator(0.0)])

    class Meta:
        ordering = ['quiz', 'id']

    def __str__(self):
        return f"{self.question_text[:50]}..."


class Choice(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name='choices')
    choice_text = models.CharField(max_length=255)
    is_correct = models.BooleanField(default=False)

    class Meta:
        ordering = ['question', 'id']

    def __str__(self):
        return self.choice_text


class QuizAttempt(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    quiz = models.ForeignKey(
        Quiz,
        on_delete=models.CASCADE,
        related_name='attempts'
    )
    
    student = models.ForeignKey(
        Student,
        on_delete=models.CASCADE,
        related_name='quiz_attempts'
    )
    started_at = models.DateTimeField(auto_now_add=True)
    submitted_at = models.DateTimeField(blank=True, null=True)
    score = models.FloatField(default=0.0, validators=[MinValueValidator(0.0)])
    raw_score = models.FloatField(default=0.0, validators=[MinValueValidator(0.0)])
    penalty_percent = models.PositiveIntegerField(default=0)
    feedback = models.TextField(blank=True, null=True)
    ai_grade_applied = models.BooleanField(default=False)
    ai_grade_failed = models.BooleanField(default=False)

    class Meta:
        ordering = ['-started_at']
        unique_together = ('quiz', 'student', 'started_at')

    def __str__(self):
        return f"{self.quiz.title} - {self.student.user.email}"


class QuizAnswer(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    attempt = models.ForeignKey(
        QuizAttempt,
        on_delete=models.CASCADE,
        related_name='answers'
    )
    
    question = models.ForeignKey(
        Question,
        on_delete=models.CASCADE,
        related_name='answers'
    )
    
    selected_choice = models.ForeignKey(
        Choice,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='selected_by'
    )
    
    text_answer = models.TextField(blank=True, null=True)
    points_earned = models.FloatField(default=0.0, validators=[MinValueValidator(0.0)])
    is_correct = models.BooleanField(default=False)
    feedback = models.TextField(blank=True, null=True)

    class Meta:
        unique_together = ('attempt', 'question')

    def __str__(self):
        return f"Answer to {self.question.question_text[:30]}..."


class QuizProctorSession(models.Model):
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('terminated', 'Terminated'),
        ('ended', 'Ended'),
        ('blocked', 'Blocked'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    quiz = models.ForeignKey(Quiz, on_delete=models.CASCADE, related_name='proctor_sessions')
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='quiz_proctor_sessions')
    attempt = models.ForeignKey(
        'QuizAttempt',
        on_delete=models.SET_NULL,
        related_name='proctor_sessions',
        null=True,
        blank=True,
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    warnings_count = models.PositiveIntegerField(default=0)
    terminations_count = models.PositiveIntegerField(default=0)
    penalty_percent = models.PositiveIntegerField(default=0)
    device_id = models.CharField(max_length=128, blank=True, null=True)
    started_at = models.DateTimeField(auto_now_add=True)
    ended_at = models.DateTimeField(blank=True, null=True)
    last_heartbeat = models.DateTimeField(blank=True, null=True)
    last_violation_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        ordering = ['-started_at']
        indexes = [
            models.Index(fields=['quiz', 'student', 'status']),
            models.Index(fields=['student', 'status']),
        ]

    def __str__(self):
        return f"ProctorSession({self.quiz.title} - {self.student.user.email})"


class QuizProctorEvent(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    session = models.ForeignKey(QuizProctorSession, on_delete=models.CASCADE, related_name='events')
    event_type = models.CharField(max_length=50)
    detail = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [models.Index(fields=['session', 'event_type'])]

    def __str__(self):
        return f"{self.event_type} @ {self.created_at}"


class QuizProctorSnapshot(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    session = models.ForeignKey(QuizProctorSession, on_delete=models.CASCADE, related_name='snapshots')
    image_url = models.URLField()
    reason = models.CharField(max_length=100, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [models.Index(fields=['session', 'created_at'])]

    def __str__(self):
        return f"Snapshot({self.reason})"


class QuizFilterPreference(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='quiz_filter_preferences'
    )
    quiz = models.ForeignKey(
        Quiz,
        on_delete=models.CASCADE,
        related_name='filter_preferences'
    )
    submitted_only = models.BooleanField(default=True)
    needs_manual_only = models.BooleanField(default=False)
    score_only = models.BooleanField(default=False)
    feedback_only = models.BooleanField(default=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('user', 'quiz')

    def __str__(self):
        return f"FilterPreference({self.user_id} - {self.quiz_id})"
