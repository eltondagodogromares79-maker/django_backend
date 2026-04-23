import uuid
from django.db import models
from programs.models import Program


class YearLevel(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=50)
    order_number = models.PositiveIntegerField()
    
    program = models.ForeignKey(
        Program,
        on_delete=models.CASCADE,
        related_name='year_levels',
        null=True,
        blank=True
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['order_number']
        indexes = [
            models.Index(fields=['program', 'order_number']),
        ]

    def __str__(self):
        if self.program_id:
            return f"{self.name} ({self.program.name})"
        return self.name

    def clean(self):
        from django.core.exceptions import ValidationError

        if not self.program_id:
            raise ValidationError("Year Level must belong to a program/strand/grade.")

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)
