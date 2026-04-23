import uuid
from django.db import models
from django.core.validators import MinValueValidator
from subjects.models import SectionSubject
from users.models import Student, CustomUser


class Assignment(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    section_subject = models.ForeignKey(
        SectionSubject,
        on_delete=models.CASCADE,
        related_name='assignments'
    )
    created_by = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='assignments_created',
        limit_choices_to={'role__in': ['instructor', 'adviser', 'admin']},
        help_text="User who created this assignment."
    )
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    total_points = models.FloatField(default=100.0, validators=[MinValueValidator(0.0)])
    due_date = models.DateTimeField()
    allow_late_submission = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['due_date']

    def __str__(self):
        return f"{self.title} ({self.section_subject.subject.code})"


class AssignmentSubmission(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    assignment = models.ForeignKey(
        Assignment,
        on_delete=models.CASCADE,
        related_name='submissions'
    )
    
    student = models.ForeignKey(
        Student,
        on_delete=models.CASCADE,
        related_name='assignment_submissions'
    )
    
    file_url = models.URLField(blank=True, null=True)
    text_answer = models.TextField(blank=True, null=True)
    score = models.FloatField(blank=True, null=True, validators=[MinValueValidator(0.0)])
    feedback = models.TextField(blank=True, null=True)
    
    submitted_at = models.DateTimeField(auto_now_add=True)
    graded_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        unique_together = ('assignment', 'student')
        ordering = ['-submitted_at']

    def __str__(self):
        return f"{self.assignment.title} - {self.student.user.email}"
