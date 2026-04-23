from django.contrib import admin, messages
from django import forms
from django.http import JsonResponse
from django.urls import path
from django.utils import timezone
from .models import Assignment, AssignmentSubmission
from .ai import grade_assignment_with_gemini, generate_assignment_with_gemini, RateLimitError


class AssignmentSubmissionInline(admin.TabularInline):
    model = AssignmentSubmission
    extra = 0
    fields = ('student', 'score', 'submitted_at')
    readonly_fields = ('submitted_at',)
    autocomplete_fields = ('student',)


@admin.register(Assignment)
class AssignmentAdmin(admin.ModelAdmin):
    class AIAssignmentForm(forms.ModelForm):
        ai_prompt = forms.CharField(
            required=False,
            widget=forms.Textarea(attrs={'rows': 4}),
            label='AI prompt (optional)',
            help_text='Describe the assignment you want to generate.'
        )
        ai_total_points = forms.FloatField(
            required=False,
            initial=100.0,
            label='AI total points',
            help_text='Target points for the AI assignment.'
        )
        ai_generated = forms.CharField(
            required=False,
            widget=forms.HiddenInput(),
            label='',
        )
        ai_content = forms.CharField(
            required=False,
            widget=forms.HiddenInput(),
            label='',
        )

        class Meta:
            model = Assignment
            fields = '__all__'

        def clean(self):
            cleaned = super().clean()
            description = cleaned.get('description') or ''
            ai_prompt = cleaned.get('ai_prompt') or ''
            ai_generated = cleaned.get('ai_generated') or ''
            ai_content = cleaned.get('ai_content') or ''

            if not description.strip() and ai_content.strip():
                cleaned['description'] = ai_content.strip()
                description = cleaned['description']

            if ai_prompt and len(description.strip()) < 80 and ai_generated != '1':
                raise forms.ValidationError("AI draft is too short. Click 'Generate AI Draft' to create a full assignment.")

            return cleaned

    form = AIAssignmentForm
    list_display = ('title', 'section_subject', 'created_by', 'due_date', 'allow_late_submission')
    list_filter = ('section_subject', 'due_date', 'allow_late_submission')
    search_fields = ('title', 'section_subject__subject__code')
    ordering = ('-due_date',)
    list_per_page = 25
    inlines = [AssignmentSubmissionInline]
    autocomplete_fields = ('section_subject', 'created_by')
    
    fieldsets = (
        ('AI Generator', {'fields': ('ai_prompt', 'ai_total_points', 'ai_generated', 'ai_content')}),
        ('Assignment', {
            'fields': ('section_subject', 'created_by', 'title', 'description')
        }),
        ('Settings', {
            'fields': ('total_points', 'due_date', 'allow_late_submission')
        }),
    )
    
    readonly_fields = ('created_at',)

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path('ai-generate/', self.admin_site.admin_view(self.ai_generate_view), name='assignment-ai-generate'),
        ]
        return custom_urls + urls

    def ai_generate_view(self, request):
        if request.method != 'POST':
            return JsonResponse({'error': 'Method not allowed'}, status=405)

        section_subject_id = request.POST.get('section_subject')
        prompt = request.POST.get('prompt')
        total_points_raw = request.POST.get('total_points')

        if not section_subject_id or not prompt:
            return JsonResponse({'error': 'section_subject and prompt are required.'}, status=400)

        from subjects.models import SectionSubject

        try:
            section_subject = SectionSubject.objects.select_related('subject').get(id=section_subject_id)
        except SectionSubject.DoesNotExist:
            return JsonResponse({'error': 'Section subject not found.'}, status=404)

        try:
            total_points = float(total_points_raw) if total_points_raw is not None else 100.0
        except Exception:
            total_points = 100.0

        try:
            title, description, final_points = generate_assignment_with_gemini(
                prompt=prompt,
                subject_name=section_subject.subject.name,
                subject_code=section_subject.subject.code,
                total_points=total_points,
            )
        except RateLimitError as exc:
            return JsonResponse(
                {'error': 'Rate limited — try again in 60s.', 'detail': str(exc), 'retry_after': exc.retry_after},
                status=429
            )
        except Exception as exc:
            return JsonResponse(
                {'error': 'AI assignment generation failed.', 'detail': str(exc)},
                status=502
            )

        return JsonResponse({
            'title': title,
            'description': description,
            'total_points': final_points,
        })

    class Media:
        js = ('assignments/ai_assignment_admin.js',)


@admin.register(AssignmentSubmission)
class AssignmentSubmissionAdmin(admin.ModelAdmin):
    list_display = ('assignment', 'student', 'submitted_at', 'score')
    list_filter = ('assignment', 'student', 'submitted_at')
    search_fields = ('student__user__first_name', 'student__user__last_name', 'assignment__title')
    ordering = ('-submitted_at',)
    list_per_page = 30
    autocomplete_fields = ('assignment', 'student')
    
    fieldsets = (
        ('Submission Information', {
            'fields': ('assignment', 'student')
        }),
        ('Content', {
            'fields': ('file_url', 'text_answer')
        }),
        ('Grading', {
            'fields': ('score', 'feedback'),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('submitted_at', 'graded_at'),
            'classes': ('collapse',)
        }),
    )
    
    readonly_fields = ('submitted_at', 'graded_at')
    actions = ['ai_grade_selected']

    @admin.action(description='AI grade selected submissions')
    def ai_grade_selected(self, request, queryset):
        success_count = 0
        error_count = 0
        for submission in queryset.select_related('assignment'):
            try:
                assignment = submission.assignment
                answer_parts = []
                if submission.text_answer:
                    answer_parts.append(submission.text_answer)
                if submission.file_url:
                    answer_parts.append(f"Attachment link: {submission.file_url}")
                student_answer = "\n\n".join(answer_parts).strip()
                if not student_answer:
                    raise RuntimeError("No student answer found.")

                score, feedback = grade_assignment_with_gemini(
                    assignment_title=assignment.title,
                    assignment_description=assignment.description,
                    total_points=assignment.total_points,
                    student_answer=student_answer,
                )

                submission.score = score
                submission.feedback = feedback
                submission.graded_at = timezone.now()
                submission.save(update_fields=['score', 'feedback', 'graded_at'])
                success_count += 1
            except RateLimitError as exc:
                error_count += 1
                messages.error(request, f"AI rate limited. Try again in {exc.retry_after}s.")
            except Exception as exc:
                error_count += 1
                messages.error(request, f"AI grading failed for {submission.id}: {exc}")

        if success_count:
            messages.success(request, f"AI grading completed for {success_count} submission(s).")
        if error_count and not success_count:
            messages.warning(request, "No submissions were graded. Check errors above.")
