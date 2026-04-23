import uuid
from django.db import models
from django.conf import settings
from subjects.models import SectionSubject


class Notification(models.Model):
    KIND_CHOICES = [
        ('lesson', 'Learning Material'),
        ('assignment', 'Assignment'),
        ('quiz', 'Quiz'),
        ('assignment_submission', 'Assignment Submission'),
        ('quiz_submission', 'Quiz Submission'),
        ('attendance', 'Attendance'),
        ('online_class', 'Online Class'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='notifications',
    )
    kind = models.CharField(max_length=32, choices=KIND_CHOICES)
    title = models.CharField(max_length=255)
    body = models.TextField(blank=True, null=True)
    target_id = models.UUIDField()
    section_subject = models.ForeignKey(
        SectionSubject,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='notifications',
    )
    is_read = models.BooleanField(default=False)
    read_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', 'is_read'], name='notif_user_read_idx'),
            models.Index(fields=['user', 'created_at'], name='notif_user_created_idx'),
        ]

    def __str__(self):
        return f"{self.get_kind_display()} - {self.title} ({self.user})"
