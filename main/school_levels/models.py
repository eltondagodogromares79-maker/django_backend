import uuid
from django.db import models


class SchoolLevel(models.Model):
    class LevelType(models.TextChoices):
        COLLEGE = 'college', 'College'
        JUNIOR_HIGH = 'junior_high', 'Junior High School'
        SENIOR_HIGH = 'senior_high', 'Senior High School'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100, unique=True)
    level_type = models.CharField(
        max_length=20,
        choices=LevelType.choices,
        default=LevelType.COLLEGE
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name

    @property
    def is_high_school(self):
        return self.level_type in [self.LevelType.JUNIOR_HIGH, self.LevelType.SENIOR_HIGH]

    @property
    def is_college(self):
        return self.level_type == self.LevelType.COLLEGE


class SchoolYear(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=50, unique=True, help_text="e.g., 2025-2026")
    start_date = models.DateField()
    end_date = models.DateField()
    is_active = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-start_date']

    def __str__(self):
        return self.name


class Term(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    semester = models.CharField(max_length=10, help_text="1st | 2nd | summer")
    school_year = models.ForeignKey(
        SchoolYear,
        on_delete=models.PROTECT,
        related_name='terms',
        null=True,
        blank=True
    )
    start_date = models.DateField()
    end_date = models.DateField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['school_year', 'semester']
        unique_together = ('school_year', 'semester')

    def __str__(self):
        return f"{self.semester} {self.school_year.name}"
