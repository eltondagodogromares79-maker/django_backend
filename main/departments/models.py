import uuid
from django.db import models
from school_levels.models import SchoolLevel


class Department(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255, unique=True)

    
    school_level = models.ForeignKey(
        SchoolLevel,
        on_delete=models.CASCADE,
        related_name="departments"
    )
    
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['school_level', 'name']
        indexes = [
            models.Index(fields=['school_level', 'name']),
        ]

    def __str__(self):
        return f"{self.name} ({self.school_level.name})"
