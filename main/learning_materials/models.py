import uuid
from django.db import models
from subjects.models import SectionSubject
from .storage import LearningMaterialStorage


class LearningMaterial(models.Model):
    MATERIAL_TYPE_CHOICES = [
        ('pdf', 'PDF'),
        ('image', 'Image'),
        ('text', 'Text'),
        ('link', 'Link'),
        ('video', 'Video'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    section_subject = models.ForeignKey(
        SectionSubject,
        on_delete=models.CASCADE,
        related_name='learning_materials'
    )
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    type = models.CharField(max_length=10, choices=MATERIAL_TYPE_CHOICES)
    attachment = models.FileField(
        upload_to='learning_materials/',
        storage=LearningMaterialStorage(),
        blank=True,
        null=True,
        max_length=500,
    )
    file_url = models.URLField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.title} ({self.section_subject.subject.code})"


class FavoriteMaterial(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    student = models.ForeignKey(
        'users.CustomUser', on_delete=models.CASCADE, related_name='favorite_materials'
    )
    material = models.ForeignKey(
        LearningMaterial, on_delete=models.CASCADE, related_name='favorited_by'
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('student', 'material')
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.student.email} ♥ {self.material.title}"
