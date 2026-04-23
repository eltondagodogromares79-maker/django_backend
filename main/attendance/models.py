import uuid
from django.db import models
from django.conf import settings
from django.utils import timezone
from sections.models import Section
from subjects.models import SectionSubject
from announcements.models import Announcement
from users.models import Student


class AttendanceSession(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    section = models.ForeignKey(Section, on_delete=models.CASCADE, related_name='attendance_sessions')
    section_subject = models.ForeignKey(
        SectionSubject,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='attendance_sessions',
    )
    announcement = models.ForeignKey(
        Announcement,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='attendance_sessions',
    )
    title = models.CharField(max_length=255, blank=True)
    scheduled_at = models.DateTimeField(default=timezone.now)
    is_online_class = models.BooleanField(default=False)
    is_live = models.BooleanField(default=False)
    provider = models.CharField(max_length=30, blank=True, default='jitsi')
    room_key = models.CharField(max_length=120, blank=True)
    join_url = models.URLField(blank=True)
    ended_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='attendance_sessions',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-scheduled_at']
        indexes = [
            models.Index(fields=['section', 'scheduled_at']),
            models.Index(fields=['section_subject', 'scheduled_at']),
        ]

    def __str__(self):
        return f"Attendance {self.section.name} @ {self.scheduled_at}"


class AttendanceRecord(models.Model):
    STATUS_CHOICES = [
        ('present', 'Present'),
        ('absent', 'Absent'),
        ('late', 'Late'),
        ('excused', 'Excused'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    session = models.ForeignKey(AttendanceSession, on_delete=models.CASCADE, related_name='records')
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='attendance_records')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='absent')
    marked_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='attendance_marks',
    )
    marked_at = models.DateTimeField(null=True, blank=True)
    note = models.TextField(blank=True, null=True)

    class Meta:
        unique_together = ('session', 'student')
        indexes = [
            models.Index(fields=['session', 'status']),
            models.Index(fields=['student', 'status']),
        ]

    def __str__(self):
        return f"{self.student.user.get_full_name()} - {self.status}"
