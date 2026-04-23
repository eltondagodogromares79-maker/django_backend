import uuid
from django.db import models
from django.core.exceptions import ValidationError
from year_levels.models import YearLevel
from school_levels.models import Term, SchoolYear
from users.models import Student


class Section(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=50)
    year_level = models.ForeignKey(YearLevel, on_delete=models.CASCADE, related_name='sections')
    school_year = models.ForeignKey(
        SchoolYear,
        on_delete=models.PROTECT,
        related_name='sections',
        null=True,
        blank=True
    )
    # Adviser assigned to this section (high school) — optional for college
    adviser = models.ForeignKey(
        'users.Adviser', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='sections'
    )
    capacity = models.PositiveIntegerField(default=40)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['year_level', 'name']
        indexes = [models.Index(fields=['year_level', 'name'])]

    def __str__(self):
        return f"{self.name} ({self.year_level.name})"

    @property
    def school_level(self):
        return self.year_level.program.department.school_level

    @property
    def is_high_school(self):
        if self.school_level:
            return self.school_level.is_high_school
        program_type = (self.year_level.program.type or '').strip().lower() if self.year_level and self.year_level.program_id else ''
        return program_type in ['strand', 'grade']

    def clean(self):
        if not self.adviser_id:
            return

        if not self.is_high_school:
            raise ValidationError("Only high school sections can have an adviser assigned.")

        if not self.adviser.program_id:
            raise ValidationError("Adviser must be assigned to a strand or grade.")

        if self.year_level.program_id != self.adviser.program_id:
            raise ValidationError("Adviser must match the section's strand/grade.")


class Enrollment(models.Model):
    """
    Enrolls a student into a section for a term.
    - College: student then picks subjects via StudentSubject.
    - High school: all subjects in the year level are auto-assigned on save.
    """
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('enrolled', 'Enrolled'),
        ('dropped', 'Dropped'),
        ('completed', 'Completed'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='enrollments')
    year_level = models.ForeignKey(
        YearLevel,
        on_delete=models.SET_NULL,
        related_name='enrollments',
        null=True,
        blank=True,
    )
    section = models.ForeignKey(
        Section,
        on_delete=models.SET_NULL,
        related_name='enrollments',
        null=True,
        blank=True,
    )
    term = models.ForeignKey(Term, on_delete=models.CASCADE, related_name='enrollments')
    school_year = models.ForeignKey(
        SchoolYear,
        on_delete=models.PROTECT,
        related_name='enrollments',
        null=True,
        blank=True
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    is_current = models.BooleanField(default=False, db_index=True)
    enrolled_at = models.DateTimeField(auto_now_add=True)
    subjects = models.ManyToManyField(
        'subjects.SectionSubject',
        through='StudentSubject',
        related_name='enrollments',
        blank=True,
    )

    class Meta:
        ordering = ['-enrolled_at']
        unique_together = ('student', 'section', 'term')

    def __str__(self):
        if self.section_id:
            return f"{self.student.user.get_full_name()} — {self.section.name} ({self.term})"
        return f"{self.student.user.get_full_name()} — (No Section) ({self.term})"

    def save(self, *args, **kwargs):
        is_new = self._state.adding
        if self.term_id and not self.school_year_id:
            self.school_year = self.term.school_year
        if self.section_id and not self.year_level_id:
            self.year_level = self.section.year_level
        if self.student_id:
            if not self.is_current:
                if not Enrollment.objects.filter(student_id=self.student_id, is_current=True).exists():
                    self.is_current = True
            else:
                Enrollment.objects.filter(student_id=self.student_id, is_current=True).exclude(pk=self.pk).update(is_current=False)
        super().save(*args, **kwargs)
        # Auto-assign all subjects for high school enrollments
        if is_new and self.section_id and self.section.is_high_school:
            self._auto_assign_highschool_subjects()

    def _auto_assign_highschool_subjects(self):
        from subjects.models import SectionSubject
        section_subjects = SectionSubject.objects.filter(
            section=self.section, term=self.term
        )
        StudentSubject.objects.bulk_create([
            StudentSubject(enrollment=self, section_subject=ss)
            for ss in section_subjects
        ], ignore_conflicts=True)


class StudentSubject(models.Model):
    """
    Links a student enrollment to a specific section-subject (with teacher).
    - High school: auto-populated on enrollment.
    - College: student selects which subjects to take.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    enrollment = models.ForeignKey(Enrollment, on_delete=models.CASCADE, related_name='student_subjects')
    section_subject = models.ForeignKey(
        'subjects.SectionSubject', on_delete=models.CASCADE,
        related_name='student_subjects'
    )
    school_year = models.ForeignKey(
        SchoolYear,
        on_delete=models.PROTECT,
        related_name='student_subjects',
        null=True,
        blank=True
    )

    class Meta:
        unique_together = ('enrollment', 'section_subject')

    def clean(self):
        # Ensure the section_subject belongs to the same section as the enrollment
        if self.section_subject.section_id != self.enrollment.section_id:
            raise ValidationError("Subject does not belong to the enrolled section.")

    def __str__(self):
        return f"{self.enrollment.student.user.get_full_name()} — {self.section_subject.subject.code}"

    def save(self, *args, **kwargs):
        if self.section_subject_id and not self.school_year_id:
            self.school_year = self.section_subject.school_year
        super().save(*args, **kwargs)
