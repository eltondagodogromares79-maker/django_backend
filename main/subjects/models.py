import uuid
from django.db import models
from programs.models import Program
from year_levels.models import YearLevel
from school_levels.models import Term, SchoolYear


class Subject(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=20, unique=True)
    name = models.CharField(max_length=255)
    program = models.ForeignKey(
        Program, on_delete=models.CASCADE,
        related_name='subjects',
        help_text="Program/Course/Strand this subject belongs to"
    )
    year_level = models.ForeignKey(YearLevel, on_delete=models.CASCADE, related_name='subjects')
    units = models.PositiveIntegerField(default=3, help_text="Credit units")
    description = models.TextField(blank=True, null=True)
    instructor = models.ForeignKey(
        'users.Instructor', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='subjects'
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('program', 'year_level', 'code')
        ordering = ['year_level', 'name']
        indexes = [models.Index(fields=['program', 'year_level'])]

    def __str__(self):
        return f"{self.code} - {self.name}"


class SectionSubject(models.Model):
    """
    Assigns a teacher to a subject within a section for a term.
    This is the 'class schedule' record — both college and high school use this.
    - College instructor → Instructor model
    - High school adviser/teacher → Adviser model (adviser can also teach subjects)
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    section = models.ForeignKey(
        'sections.Section', on_delete=models.CASCADE,
        related_name='section_subjects'
    )
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE, related_name='section_subjects')
    term = models.ForeignKey(Term, on_delete=models.CASCADE, related_name='section_subjects')
    school_year = models.ForeignKey(
        SchoolYear,
        on_delete=models.PROTECT,
        related_name='section_subjects',
        null=True,
        blank=True
    )

    # Teacher assignment — one of these must be set
    instructor = models.ForeignKey(
        'users.Instructor', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='section_subjects'
    )
    adviser = models.ForeignKey(
        'users.Adviser', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='section_subjects'
    )

    schedule_days = models.CharField(
        max_length=50, blank=True, null=True,
        help_text="e.g. Mon, Wed, Fri"
    )
    schedule_time = models.CharField(
        max_length=50, blank=True, null=True,
        help_text="e.g. 8:00 AM - 9:30 AM"
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('section', 'subject', 'term')

    def clean(self):
        from django.core.exceptions import ValidationError
        if not self.instructor and not self.adviser:
            if self.section_id and self.section.is_high_school and self.section.adviser_id:
                return
            raise ValidationError("A subject must have either an instructor or an adviser assigned.")
        if self.instructor and self.adviser:
            raise ValidationError("Assign either an instructor or an adviser, not both.")

    def save(self, *args, **kwargs):
        # Auto-assign adviser for high school sections if no teacher provided
        if not self.instructor_id and not self.adviser_id and self.section_id:
            try:
                if self.section.is_high_school and self.section.adviser_id:
                    self.adviser = self.section.adviser
            except Exception:
                pass
        if self.term_id and not self.school_year_id:
            self.school_year = self.term.school_year
        super().save(*args, **kwargs)

    def __str__(self):
        teacher = self.instructor or self.adviser
        return f"{self.section.name} — {self.subject.code} ({self.term}) [{teacher}]"

    @property
    def teacher(self):
        return self.instructor or self.adviser

    # NOTE: save() implemented above to avoid overriding behavior.


class Grade(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    student = models.ForeignKey('users.Student', on_delete=models.CASCADE, related_name='grades')
    section_subject = models.ForeignKey(SectionSubject, on_delete=models.CASCADE, related_name='grades')
    school_year = models.ForeignKey(
        SchoolYear,
        on_delete=models.PROTECT,
        related_name='grades',
        null=True,
        blank=True
    )
    final_score = models.FloatField()
    grade = models.CharField(max_length=20)
    remarks = models.TextField(blank=True, null=True)

    class Meta:
        unique_together = ('student', 'section_subject')

    def __str__(self):
        return f"{self.student.user.get_full_name()} — {self.section_subject.subject.code}"

    def save(self, *args, **kwargs):
        if self.section_subject_id and not self.school_year_id:
            self.school_year = self.section_subject.school_year
        super().save(*args, **kwargs)
