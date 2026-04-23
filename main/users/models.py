import uuid
from django.db import models
from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin, BaseUserManager
from django.utils import timezone


class CustomUserManager(BaseUserManager):
    def create_user(self, email, first_name, last_name, password=None, role='student', **extra_fields):
        if not email:
            raise ValueError("Email is required")
        email = self.normalize_email(email)
        if 'must_change_password' not in extra_fields:
            extra_fields['must_change_password'] = role in ['student', 'instructor', 'adviser']
        user = self.model(email=email, first_name=first_name, last_name=last_name, role=role, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, first_name, last_name, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('role', 'admin')
        extra_fields.setdefault('must_change_password', False)
        return self.create_user(email, first_name, last_name, password, **extra_fields)


class CustomUser(AbstractBaseUser, PermissionsMixin):
    class Role(models.TextChoices):
        STUDENT = "student", "Student"
        INSTRUCTOR = "instructor", "Instructor"
        ADVISER = "adviser", "Adviser"
        PRINCIPAL = "principal", "Principal"
        DEAN = "dean", "Dean"
        ADMIN = "admin", "Admin"
    class Gender(models.TextChoices):
        MALE = "male", "Male"
        FEMALE = "female", "Female"
        UNSPECIFIED = "unspecified", "Unspecified"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    middle_name = models.CharField(max_length=100, blank=True, null=True)
    email = models.EmailField(unique=True)
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.STUDENT)
    phone_number = models.CharField(max_length=20, blank=True, null=True)
    address = models.TextField(blank=True, null=True)
    date_of_birth = models.DateField(blank=True, null=True)
    gender = models.CharField(max_length=20, choices=Gender.choices, default=Gender.UNSPECIFIED)
    profile_picture = models.ImageField(upload_to='profiles/', blank=True, null=True, max_length=500)
    must_change_password = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    date_joined = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    objects = CustomUserManager()

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['first_name', 'last_name']

    class Meta:
        indexes = [models.Index(fields=['role', 'is_active'])]

    def __str__(self):
        return f"{self.email} ({self.role})"

    def get_full_name(self):
        if self.middle_name:
            return f"{self.first_name} {self.middle_name} {self.last_name}"
        return f"{self.first_name} {self.last_name}"


class PasswordResetCode(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='password_reset_codes')
    code_hash = models.CharField(max_length=128)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    is_used = models.BooleanField(default=False)

    class Meta:
        indexes = [models.Index(fields=['user', 'is_used', 'expires_at'])]

    def __str__(self):
        return f"PasswordResetCode({self.user.email})"


class Student(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(
        CustomUser, on_delete=models.CASCADE,
        related_name='student_profile',
        limit_choices_to={'role': 'student'}
    )
    student_number = models.CharField(max_length=50, unique=True)
    admission_date = models.DateField()
    emergency_contact_name = models.CharField(max_length=100, blank=True, null=True)
    emergency_contact_phone = models.CharField(max_length=20, blank=True, null=True)
    emergency_contact_relationship = models.CharField(max_length=50, blank=True, null=True)

    def __str__(self):
        return f"{self.user.get_full_name()} ({self.student_number})"


class Instructor(models.Model):
    """College instructor — teaches subjects in a section."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(
        CustomUser, on_delete=models.CASCADE,
        related_name='instructor_profile',
        limit_choices_to={'role': 'instructor'}
    )
    department = models.ForeignKey(
        'departments.Department', on_delete=models.CASCADE,
        related_name='instructors'
    )
    hire_date = models.DateField()

    def __str__(self):
        return f"{self.user.get_full_name()} ({self.department.name})"


class Adviser(models.Model):
    """High school adviser — handles a section/class."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(
        CustomUser, on_delete=models.CASCADE,
        related_name='adviser_profile',
        limit_choices_to={'role': 'adviser'}
    )
    program = models.OneToOneField(
        'programs.Program',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='adviser',
        limit_choices_to={
            'type__in': ['Strand', 'Grade'],
        },
    )
    department = models.ForeignKey(
        'departments.Department', on_delete=models.CASCADE,
        related_name='advisers'
    )
    hire_date = models.DateField()

    def __str__(self):
        return f"{self.user.get_full_name()} ({self.department.name})"

    def clean(self):
        from django.core.exceptions import ValidationError

        if not self.program_id:
            raise ValidationError("Adviser must be assigned to a strand or grade (high school).")

        program_type = (self.program.type or "").strip().lower()
        if program_type not in ['strand', 'grade']:
            raise ValidationError("Adviser program must be a strand or grade.")

        if self.department_id and self.department_id != self.program.department_id:
            raise ValidationError("Adviser department must match the program's department.")

    def save(self, *args, **kwargs):
        if self.program_id and not self.department_id:
            self.department = self.program.department
        self.full_clean()
        super().save(*args, **kwargs)


class Principal(models.Model):
    """Manages high school level."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(
        CustomUser, on_delete=models.CASCADE,
        related_name='principal_profile',
        limit_choices_to={'role': 'principal'}
    )
    school_level = models.ForeignKey(
        'school_levels.SchoolLevel', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='principals'
    )
    department = models.ForeignKey(
        'departments.Department', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='principals'
    )
    appointed_date = models.DateField()

    def __str__(self):
        return f"Principal {self.user.get_full_name()}"


class Dean(models.Model):
    """Manages a college department."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(
        CustomUser, on_delete=models.CASCADE,
        related_name='dean_profile',
        limit_choices_to={'role': 'dean'}
    )
    department = models.ForeignKey(
        'departments.Department', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='deans'
    )
    appointed_date = models.DateField()

    def __str__(self):
        return f"Dean {self.user.get_full_name()}"


class AdminProfile(models.Model):
    """System administrator profile."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(
        CustomUser, on_delete=models.CASCADE,
        related_name='admin_profile',
        limit_choices_to={'role': 'admin'}
    )
    employee_id = models.CharField(max_length=50, unique=True)

    def __str__(self):
        return f"Admin {self.user.get_full_name()}"
