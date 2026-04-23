from django import forms
from django.urls import path, reverse
from django.http import JsonResponse
from django.contrib import admin
from year_levels.models import YearLevel
from .models import Subject, SectionSubject, Grade

DAYS_OF_WEEK = [
    ('Mon', 'Monday'),
    ('Tue', 'Tuesday'),
    ('Wed', 'Wednesday'),
    ('Thu', 'Thursday'),
    ('Fri', 'Friday'),
    ('Sat', 'Saturday'),
    ('Sun', 'Sunday'),
]


class SectionSubjectAdminForm(forms.ModelForm):
    schedule_days_select = forms.MultipleChoiceField(
        choices=DAYS_OF_WEEK,
        widget=forms.CheckboxSelectMultiple,
        required=False,
        label='Schedule days',
    )

    class Meta:
        model = SectionSubject
        fields = '__all__'
        exclude = ['schedule_days']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.schedule_days:
            self.fields['schedule_days_select'].initial = [
                d.strip() for d in self.instance.schedule_days.split(',')
            ]

    def save(self, commit=True):
        instance = super().save(commit=False)
        selected = self.cleaned_data.get('schedule_days_select', [])
        instance.schedule_days = ', '.join(selected) if selected else ''
        if commit:
            instance.save()
        return instance


@admin.register(Subject)
class SubjectAdmin(admin.ModelAdmin):
    class SubjectAdminForm(forms.ModelForm):
        class Meta:
            model = Subject
            fields = '__all__'

        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            program_id = None
            if self.data.get('program'):
                program_id = self.data.get('program')
            elif self.instance and self.instance.program_id:
                program_id = self.instance.program_id

            if program_id:
                self.fields['year_level'].queryset = YearLevel.objects.filter(
                    program_id=program_id
                ).order_by('order_number')
            else:
                self.fields['year_level'].queryset = YearLevel.objects.none()

            self.fields['program'].widget.attrs['data-year-levels-url'] = reverse(
                'admin:subjects_subject_year_levels'
            )

        def clean(self):
            cleaned = super().clean()
            program = cleaned.get('program')
            year_level = cleaned.get('year_level')
            if program and year_level and year_level.program_id != program.id:
                raise forms.ValidationError("Selected year level does not belong to the chosen program/strand/grade.")
            return cleaned

    form = SubjectAdminForm

    class Media:
        js = ('sections/admin/enrollment_form.js',)

    def get_urls(self):
        urls = super().get_urls()
        custom = [
            path(
                'year-levels/',
                self.admin_site.admin_view(self.year_levels_view),
                name='subjects_subject_year_levels'
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

    def get_teachers(self, obj):
        return obj.instructor.user.get_full_name() if obj.instructor else '-'
    get_teachers.short_description = 'Instructor'

    list_display = ('code', 'name', 'program', 'year_level', 'units', 'get_teachers')
    list_filter = ('program', 'year_level')
    search_fields = ('name', 'code')
    ordering = ('year_level', 'name')
    list_per_page = 25

    fieldsets = (
        ('Subject', {'fields': ('name', 'code', 'description', 'units', 'instructor')}),
        ('Placement', {'fields': ('program', 'year_level')}),
    )


@admin.register(SectionSubject)
class SectionSubjectAdmin(admin.ModelAdmin):
    form = SectionSubjectAdminForm
    list_display = ('section', 'subject', 'term', 'instructor', 'adviser_display', 'schedule_days', 'schedule_time', 'created_at')
    list_filter = ('term', 'section')
    search_fields = ('section__name', 'subject__code', 'subject__name',
                     'instructor__user__email', 'adviser__user__email')
    ordering = ('-created_at',)
    list_per_page = 30
    autocomplete_fields = ('section', 'subject', 'term', 'instructor', 'adviser')

    fieldsets = (
        ('Assignment', {'fields': ('section', 'subject', 'term', 'school_year', 'instructor', 'adviser')}),
        ('Schedule', {'fields': ('schedule_days_select', 'schedule_time')}),
    )

    @admin.display(description='Adviser')
    def adviser_display(self, obj):
        adviser = obj.adviser or (obj.section.adviser if obj.section_id else None)
        return adviser.user.get_full_name() if adviser else None


@admin.register(Grade)
class GradeAdmin(admin.ModelAdmin):
    list_display = ('student', 'section_subject', 'final_score', 'grade')
    list_filter = ('section_subject',)
    search_fields = ('student__user__first_name', 'student__user__last_name', 'section_subject__subject__code')
    list_per_page = 30
    autocomplete_fields = ('student', 'section_subject')
