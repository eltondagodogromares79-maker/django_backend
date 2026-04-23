from django import forms
from django.urls import path, reverse
from django.http import JsonResponse
from django.contrib import admin
from django.db.models import Q
from django.utils import timezone
from django.utils.html import format_html, format_html_join
from .models import Section, Enrollment, StudentSubject
from programs.models import Program
from year_levels.models import YearLevel
from school_levels.models import Term, SchoolYear
from subjects.models import Subject, SectionSubject


class EnrollmentInline(admin.TabularInline):
    model = Enrollment
    extra = 0
    fields = ('student', 'term', 'status', 'enrolled_at')
    readonly_fields = ('enrolled_at',)
    autocomplete_fields = ('student', 'term')


@admin.register(Section)
class SectionAdmin(admin.ModelAdmin):
    class SectionAdminForm(forms.ModelForm):
        program = forms.ModelChoiceField(
            queryset=Program.objects.all(),
            required=True,
            label="Program/Strand/Grade"
        )

        class Meta:
            model = Section
            fields = '__all__'

        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            program_id = None
            if self.data.get('program'):
                program_id = self.data.get('program')
            elif self.instance and self.instance.year_level_id:
                program_id = self.instance.year_level.program_id
                self.fields['program'].initial = self.instance.year_level.program

            if program_id:
                self.fields['year_level'].queryset = YearLevel.objects.filter(
                    program_id=program_id
                ).order_by('order_number')
            else:
                self.fields['year_level'].queryset = YearLevel.objects.none()

            self.fields['program'].widget.attrs['data-year-levels-url'] = reverse(
                'admin:sections_section_year_levels'
            )

        def clean(self):
            cleaned = super().clean()
            program = cleaned.get('program')
            year_level = cleaned.get('year_level')
            if program and year_level and year_level.program_id != program.id:
                raise forms.ValidationError("Selected year level does not belong to the chosen program/strand/grade.")
            return cleaned

    form = SectionAdminForm

    class Media:
        js = ('sections/admin/enrollment_form.js',)

    def get_urls(self):
        urls = super().get_urls()
        custom = [
            path(
                'year-levels/',
                self.admin_site.admin_view(self.year_levels_view),
                name='sections_section_year_levels'
            ),
        ]
        return custom + urls

    def year_levels_view(self, request):
        program_id = request.GET.get('program_id')
        if not program_id:
            return JsonResponse({'results': []})
        qs = YearLevel.objects.filter(program_id=program_id).order_by('order_number')
        data = [{'id': str(yl.id), 'name': yl.name} for yl in qs]
        return JsonResponse({'results': data})

    list_display = ('name', 'year_level', 'adviser', 'capacity', 'created_at')
    list_filter = ('year_level',)
    search_fields = ('name',)
    ordering = ('year_level', 'name')
    list_per_page = 20
    inlines = [EnrollmentInline]
    autocomplete_fields = ()

    fieldsets = (
        ('Section', {'fields': ('name', 'program', 'year_level', 'school_year', 'capacity')}),
    )
    readonly_fields = ('created_at',)


@admin.register(Enrollment)
class EnrollmentAdmin(admin.ModelAdmin):
    class EnrollmentAdminForm(forms.ModelForm):
        program = forms.ModelChoiceField(
            queryset=Program.objects.all(),
            required=True,
            label="Program/Strand/Grade"
        )
        year_level = forms.ModelChoiceField(
            queryset=YearLevel.objects.select_related('program'),
            required=True,
            label="Year Level (Grade)"
        )
        section_name = forms.CharField(
            required=False,
            label="Section",
            widget=forms.TextInput(attrs={
                'readonly': 'readonly',
            })
        )
        school_year = forms.ModelChoiceField(
            queryset=SchoolYear.objects.all().order_by('-start_date'),
            required=False,
            label="School Year",
            disabled=True
        )
        subject_choices = forms.ModelMultipleChoiceField(
            queryset=Subject.objects.none(),
            required=False,
            label="Subjects",
            widget=forms.CheckboxSelectMultiple
        )
        section = forms.ModelChoiceField(
            queryset=Section.objects.all().order_by('name'),
            required=True,
            label="Section"
        )

        class Meta:
            model = Enrollment
            fields = (
                'student',
                'program',
                'year_level',
                'term',
                'school_year',
                'section',
                'section_name',
                'subject_choices',
                'status',
            )

        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            today = timezone.localdate()
            program_id = None
            if self.data.get('program'):
                program_id = self.data.get('program')
            elif self.instance and self.instance.section_id:
                program_id = self.instance.section.year_level.program_id
                self.fields['program'].initial = self.instance.section.year_level.program
                self.fields['year_level'].initial = self.instance.section.year_level
            elif self.instance and self.instance.year_level_id:
                program_id = self.instance.year_level.program_id
                self.fields['program'].initial = self.instance.year_level.program
                self.fields['year_level'].initial = self.instance.year_level

            self.fields['year_level'].queryset = YearLevel.objects.all().order_by('order_number')

            active_terms = Term.objects.filter(
                start_date__lte=today,
                end_date__gte=today
            )
            selected_term_id = self.data.get('term') or getattr(self.instance, 'term_id', None)
            if selected_term_id:
                self.fields['term'].queryset = Term.objects.filter(
                    Q(id=selected_term_id) | Q(id__in=active_terms.values('id'))
                ).distinct()
            else:
                self.fields['term'].queryset = active_terms

            if selected_term_id:
                term = Term.objects.filter(id=selected_term_id).select_related('school_year').first()
                if term and term.school_year_id:
                    self.fields['school_year'].initial = term.school_year

            year_level_id = self.data.get('year_level') or getattr(self.instance, 'year_level_id', None)
            term_id = self.data.get('term') or getattr(self.instance, 'term_id', None)

            section = None
            if year_level_id:
                self.fields['section'].queryset = Section.objects.filter(
                    year_level_id=year_level_id
                ).order_by('name')
            else:
                self.fields['section'].queryset = Section.objects.all().order_by('name')

            section_id = self.data.get('section') or getattr(self.instance, 'section_id', None)
            if section_id:
                section = Section.objects.filter(id=section_id).first()
                if section:
                    self.fields['section_name'].initial = section.name

            if section:
                subject_qs = Subject.objects.filter(
                    program_id=section.year_level.program_id,
                    year_level_id=section.year_level_id
                ).select_related('instructor__user').order_by('code')
                self.fields['subject_choices'].queryset = subject_qs
                if section.is_high_school:
                    self.fields['subject_choices'].initial = subject_qs.values_list('id', flat=True)
                    self.fields['subject_choices'].disabled = True
            else:
                self.fields['subject_choices'].queryset = Subject.objects.none()

            if self.instance and self.instance.pk:
                self.fields['subject_choices'].initial = Subject.objects.filter(
                    section_subjects__student_subjects__enrollment=self.instance
                ).distinct().values_list('id', flat=True)

            def label_from_instance(subject):
                teacher = subject.instructor.user.get_full_name() if subject.instructor else 'Unassigned'
                return f"{subject.code} - {subject.name} (Teacher: {teacher})"

            self.fields['subject_choices'].label_from_instance = label_from_instance
            self.fields['subject_choices'].help_text = (
                "Select the subjects for this enrollment. "
                "Section subjects will be created for the chosen term using the subject instructor "
                "or the section adviser (high school). "
                "If you change Program/Year Level/Term, save and continue editing to refresh this list."
            )
            if section and section.is_high_school:
                self.fields['subject_choices'].help_text = (
                    "High school enrollments auto-assign all subjects for the selected term."
                )
            self.fields['section_name'].help_text = "Shows the selected section name."

        def _sync_student_subjects(self, enrollment, selected_subjects):
            section = enrollment.section
            term = enrollment.term
            if not section or not term:
                return

            subject_to_section_subject = {}
            for subject in selected_subjects:
                section_subject, created = SectionSubject.objects.get_or_create(
                    section=section,
                    term=term,
                    subject=subject,
                    defaults={
                        'instructor': subject.instructor if not section.is_high_school else None,
                        'adviser': section.adviser if section.is_high_school else None,
                        'school_year': term.school_year,
                    }
                )
                subject_to_section_subject[subject.id] = section_subject

            selected_section_subject_ids = {ss.id for ss in subject_to_section_subject.values()}
            existing_ids = set(
                enrollment.student_subjects.values_list('section_subject_id', flat=True)
            )
            to_remove = existing_ids - selected_section_subject_ids
            if to_remove:
                StudentSubject.objects.filter(
                    enrollment=enrollment,
                    section_subject_id__in=to_remove
                ).delete()
            to_add = [
                StudentSubject(enrollment=enrollment, section_subject=ss)
                for ss in subject_to_section_subject.values()
                if ss.id not in existing_ids
            ]
            if to_add:
                StudentSubject.objects.bulk_create(to_add, ignore_conflicts=True)

        def clean(self):
            cleaned = super().clean()
            program = cleaned.get('program')
            year_level = cleaned.get('year_level')
            section = cleaned.get('section')
            if not program or not year_level:
                return cleaned
            if year_level.program_id != program.id:
                raise forms.ValidationError("Selected year level does not belong to the chosen program/strand/grade.")

            if section and section.year_level_id != year_level.id:
                raise forms.ValidationError("Selected section does not belong to the chosen year level.")
            if not section:
                raise forms.ValidationError("Please select a section for this enrollment.")

            term = cleaned.get('term')
            if cleaned.get('section') and term:
                if term and not cleaned.get('school_year'):
                    cleaned['school_year'] = term.school_year
                subject_qs = Subject.objects.filter(
                    program_id=cleaned['section'].year_level.program_id,
                    year_level_id=cleaned['section'].year_level_id
                )
                if not subject_qs.exists():
                    raise forms.ValidationError(
                        "No subjects found for the selected program/year level."
                    )
                if not cleaned['section'].is_high_school:
                    selected_subjects = cleaned.get('subject_choices')
                    if not selected_subjects:
                        raise forms.ValidationError(
                            "Please select at least one subject for this enrollment."
                        )
                else:
                    pass
            return cleaned

    form = EnrollmentAdminForm

    def get_urls(self):
        urls = super().get_urls()
        custom = [
            path(
                'year-levels/',
                self.admin_site.admin_view(self.year_levels_view),
                name='sections_enrollment_year_levels'
            ),
        ]
        return custom + urls

    def year_levels_view(self, request):
        program_id = request.GET.get('program_id')
        if not program_id:
            return JsonResponse({'results': []})
        qs = YearLevel.objects.filter(
            program_id=program_id
        ).order_by('order_number')
        data = [{'id': str(yl.id), 'name': yl.name} for yl in qs]
        return JsonResponse({'results': data})

    list_display = ('student', 'program_name', 'program_type', 'year_level_name', 'school_year_name', 'term', 'status', 'enrolled_at')
    list_filter = ('status', 'term', 'enrolled_at', 'section__year_level__program__type')
    search_fields = (
        'student__user__first_name',
        'student__user__last_name',
        'section__year_level__name',
        'section__year_level__program__name',
    )
    ordering = ('-enrolled_at',)
    list_per_page = 30
    autocomplete_fields = ('student', 'term')
    readonly_fields = ('enrolled_at', 'subjects_summary')

    actions = ('mark_enrolled', 'mark_dropped', 'mark_completed')

    fieldsets = (
        ('Enrollment', {'fields': ('student', 'program', 'year_level', 'term', 'school_year', 'section', 'section_name', 'status', 'is_current')}),
        ('Subjects', {'fields': ('subject_choices', 'subjects_summary')}),
    )

    @admin.action(description='Mark as Enrolled')
    def mark_enrolled(self, request, queryset):
        queryset.update(status='enrolled')

    @admin.action(description='Mark as Dropped')
    def mark_dropped(self, request, queryset):
        queryset.update(status='dropped')

    @admin.action(description='Mark as Completed')
    def mark_completed(self, request, queryset):
        queryset.update(status='completed')

    @admin.display(description='Program/Strand/Grade')
    def program_name(self, obj):
        year_level = obj.section.year_level if obj.section_id else obj.year_level
        return year_level.program.name if year_level and year_level.program_id else None

    @admin.display(description='Type')
    def program_type(self, obj):
        year_level = obj.section.year_level if obj.section_id else obj.year_level
        return year_level.program.type if year_level and year_level.program_id else None

    @admin.display(description='Year Level')
    def year_level_name(self, obj):
        year_level = obj.section.year_level if obj.section_id else obj.year_level
        return year_level.name if year_level else None

    @admin.display(description='School Year')
    def school_year_name(self, obj):
        return obj.school_year.name if obj.school_year_id else None

    @admin.display(description='Subjects (Read-only)')
    def subjects_summary(self, obj):
        if not obj.section_id or not obj.term_id:
            return "No section/term selected."
        section_subjects = SectionSubject.objects.filter(
            section=obj.section,
            term=obj.term
        ).select_related('subject', 'instructor__user', 'adviser__user').order_by('subject__code')
        if not section_subjects.exists():
            return "No subjects for this term."
        rows = []
        for ss in section_subjects:
            teacher = ss.teacher.user.get_full_name() if ss.teacher else 'Unassigned'
            rows.append(f"{ss.subject.code} - {ss.subject.name} (Teacher: {teacher})")
        return format_html(
            "Section: {}<br>{}",
            obj.section.name,
            format_html_join('<br>', "{}", ((row,) for row in rows))
        )

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        selected = form.cleaned_data.get('subject_choices', None)
        if selected is None:
            return
        form._sync_student_subjects(form.instance, selected)


@admin.register(StudentSubject)
class StudentSubjectAdmin(admin.ModelAdmin):
    class StudentSubjectAdminForm(forms.ModelForm):
        subject = forms.ModelChoiceField(
            queryset=Subject.objects.all(),
            required=True,
            label="Subject"
        )

        class Meta:
            model = StudentSubject
            fields = ('enrollment', 'subject', 'section_subject')
            widgets = {'section_subject': forms.HiddenInput()}

        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            if self.instance and self.instance.section_subject_id:
                self.fields['subject'].initial = self.instance.section_subject.subject

            enrollment_id = self.data.get('enrollment') or getattr(self.instance, 'enrollment_id', None)
            if enrollment_id:
                enrollment = Enrollment.objects.select_related(
                    'section__year_level__program', 'year_level__program'
                ).filter(id=enrollment_id).first()
                if enrollment:
                    if enrollment.section_id:
                        year_level = enrollment.section.year_level
                    else:
                        year_level = enrollment.year_level
                    if year_level and year_level.program_id:
                        self.fields['subject'].queryset = Subject.objects.filter(
                            program_id=year_level.program_id,
                            year_level_id=year_level.id
                        ).order_by('code')
                    else:
                        self.fields['subject'].queryset = Subject.objects.none()
            else:
                self.fields['subject'].queryset = Subject.objects.none()

        def clean(self):
            cleaned = super().clean()
            enrollment = cleaned.get('enrollment')
            subject = cleaned.get('subject')
            if not enrollment or not subject:
                return cleaned
            if not enrollment.section_id:
                raise forms.ValidationError("Enrollment has no section yet.")
            section_subject = SectionSubject.objects.filter(
                section=enrollment.section,
                term=enrollment.term,
                subject=subject
            ).first()
            if not section_subject:
                raise forms.ValidationError("Selected subject is not offered for this section/term.")
            cleaned['section_subject'] = section_subject
            return cleaned

    form = StudentSubjectAdminForm

    list_display = ('enrollment', 'subject_code', 'subject_name', 'term_name', 'teacher_name')
    search_fields = ('enrollment__student__user__first_name', 'section_subject__subject__code', 'section_subject__term__school_year__name')
    autocomplete_fields = ('enrollment',)

    @admin.display(description='Code')
    def subject_code(self, obj):
        return obj.section_subject.subject.code

    @admin.display(description='Subject')
    def subject_name(self, obj):
        return obj.section_subject.subject.name

    @admin.display(description='Teacher')
    def teacher_name(self, obj):
        teacher = obj.section_subject.teacher
        return teacher.user.get_full_name() if teacher else None

    @admin.display(description='Term')
    def term_name(self, obj):
        return obj.section_subject.term
