from django import forms
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import CustomUser, Student, Instructor, Adviser, Principal, Dean, AdminProfile
from programs.models import Program
from sections.models import Section
from departments.models import Department
from django.db.models import Q


@admin.register(CustomUser)
class CustomUserAdmin(UserAdmin):
    model = CustomUser
    list_display = ('email', 'get_full_name', 'role', 'gender', 'is_active', 'date_joined')
    list_filter = ('role', 'gender', 'is_active', 'date_joined', 'is_staff')
    search_fields = ('email', 'first_name', 'last_name')
    ordering = ('-date_joined',)
    list_per_page = 25

    fieldsets = (
        (None, {'fields': ('email', 'password')}),
        ('Personal Info', {
            'fields': ('first_name', 'last_name', 'middle_name', 'phone_number', 'address', 'date_of_birth', 'gender', 'profile_picture')
        }),
        ('Role', {'fields': ('role',)}),
        ('Permissions', {
            'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions'),
            'classes': ('collapse',)
        }),
        ('Important Dates', {
            'fields': ('last_login', 'date_joined'),
            'classes': ('collapse',)
        }),
    )

    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('email', 'first_name', 'last_name', 'gender', 'role', 'password1', 'password2', 'is_staff', 'is_superuser'),
        }),
    )

    readonly_fields = ('date_joined', 'last_login')

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.role in ['principal', 'dean']:
            return qs.exclude(role='admin')
        return qs


@admin.register(Student)
class StudentAdmin(admin.ModelAdmin):
    list_display = ('user', 'student_number', 'admission_date')
    search_fields = ('user__email', 'user__first_name', 'user__last_name', 'student_number')
    list_filter = ('admission_date',)
    autocomplete_fields = ('user',)


@admin.register(Instructor)
class InstructorAdmin(admin.ModelAdmin):
    list_display = ('user', 'department', 'hire_date')
    search_fields = ('user__email', 'user__first_name', 'user__last_name', 'department__name')
    list_filter = ('department', 'hire_date')
    autocomplete_fields = ('user',)


class GroupedProgramField(forms.ModelChoiceField):
    """ModelChoiceField that renders options grouped by department."""
    def _get_choices(self):
        if not self.queryset:
            return []
        choices = [('', '---------')]
        by_dept = {}
        for p in self.queryset.select_related('department'):
            by_dept.setdefault(p.department.name, []).append((str(p.id), p.name))
        for dept_name in sorted(by_dept):
            choices.append((dept_name, by_dept[dept_name]))
        return choices

    choices = property(_get_choices, forms.ModelChoiceField.choices.fset)


@admin.register(Adviser)
class AdviserAdmin(admin.ModelAdmin):
    class AdviserAdminForm(forms.ModelForm):
        program = GroupedProgramField(
            queryset=Program.objects.none(),
            label='Strand/Grade',
            help_text='Options are grouped by department.',
            required=True,
        )
        section = forms.ModelChoiceField(
            queryset=Section.objects.none(),
            required=False,
            label='Section',
            help_text='Optional. Assign this adviser to a section.'
        )

        class Meta:
            model = Adviser
            fields = '__all__'

        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.fields['program'].queryset = Program.objects.filter(
                type__in=['Strand', 'Grade']
            ).select_related('department').order_by('department__name', 'name')
            self.fields['section'].queryset = Section.objects.select_related(
                'year_level__program'
            ).order_by('year_level__order_number', 'name')

        def clean(self):
            cleaned = super().clean()
            program = cleaned.get('program')
            department = cleaned.get('department')
            section = cleaned.get('section')
            if program:
                program_type = (program.type or "").strip().lower()
                if program_type not in ['strand', 'grade']:
                    raise forms.ValidationError("Program must be a Strand or Grade.")
            if program and department and program.department_id != department.id:
                raise forms.ValidationError("Selected Strand/Grade does not belong to the chosen department.")
            if section and program and section.year_level.program_id != program.id:
                raise forms.ValidationError("Selected section does not belong to the chosen strand/grade.")
            return cleaned

    form = AdviserAdminForm
    list_display = ('user', 'program', 'department', 'assigned_section', 'hire_date')
    search_fields = (
        'user__email', 'user__first_name', 'user__last_name',
        'department__name', 'program__name'
    )
    list_filter = ('department', 'hire_date', 'program')
    autocomplete_fields = ('user',)
    fieldsets = (
        (None, {'fields': ('user', 'department', 'program', 'section', 'hire_date')}),
    )

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        section = form.cleaned_data.get('section')
        if section:
            Section.objects.filter(adviser=obj).exclude(id=section.id).update(adviser=None)
            section.adviser = obj
            section.save()

    @admin.display(description='Section')
    def assigned_section(self, obj):
        section = Section.objects.filter(adviser=obj).first()
        return section.name if section else None


@admin.register(Principal)
class PrincipalAdmin(admin.ModelAdmin):
    class PrincipalAdminForm(forms.ModelForm):
        department = forms.ModelChoiceField(
            queryset=Department.objects.none(),
            required=False,
        )
        class Meta:
            model = Principal
            fields = '__all__'

        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.fields['department'].queryset = Department.objects.filter(
                school_level__name__in=['Primary', 'Secondary']
            ).order_by('name')

    form = PrincipalAdminForm
    list_display = ('user', 'department', 'appointed_date')
    search_fields = ('user__email', 'user__first_name', 'user__last_name')
    list_filter = ('department', 'appointed_date')
    autocomplete_fields = ('user',)
    fieldsets = (
        (None, {'fields': ('user', 'department', 'appointed_date')}),
    )


@admin.register(Dean)
class DeanAdmin(admin.ModelAdmin):
    list_display = ('user', 'department', 'appointed_date')
    search_fields = ('user__email', 'user__first_name', 'user__last_name', 'department__name')
    list_filter = ('department', 'appointed_date')
    autocomplete_fields = ('user',)


@admin.register(AdminProfile)
class AdminProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'employee_id')
    search_fields = ('user__email', 'user__first_name', 'user__last_name', 'employee_id')
    autocomplete_fields = ('user',)
