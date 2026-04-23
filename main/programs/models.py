import uuid
from django.db import models
from departments.models import Department


class Program(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=150)
    type = models.CharField(max_length=20, help_text="program | strand | grade")
    
    department = models.ForeignKey(
        Department,
        on_delete=models.CASCADE,
        related_name='programs'
    )
    
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['department', 'name']
        indexes = [
            models.Index(fields=['department', 'name']),
        ]

    def __str__(self):
        return self.name
