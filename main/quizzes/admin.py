from django.contrib import admin, messages
from django import forms
from django.http import JsonResponse
from django.urls import path
import json
from .models import Quiz, Question, Choice, QuizAttempt, QuizAnswer
from .ai import generate_quiz_with_gemini, grade_quiz_answer_with_gemini, RateLimitError


@admin.register(Quiz)
class QuizAdmin(admin.ModelAdmin):
    class AIQuizForm(forms.ModelForm):
        ai_prompt = forms.CharField(
            required=False,
            widget=forms.Textarea(attrs={'rows': 4}),
            label='AI prompt (optional)',
            help_text='Describe the quiz you want to generate.'
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
        ai_questions = forms.CharField(
            required=False,
            widget=forms.HiddenInput(),
            label='',
        )
        ai_preview = forms.CharField(
            required=False,
            widget=forms.Textarea(attrs={'rows': 6, 'readonly': 'readonly'}),
            label='AI question preview',
            help_text='Preview generated questions before saving.'
        )

        class Meta:
            model = Quiz
            fields = '__all__'

        def clean(self):
            cleaned = super().clean()
            description = cleaned.get('description') or ''
            ai_prompt = cleaned.get('ai_prompt') or ''
            ai_generated = cleaned.get('ai_generated') or ''
            ai_content = cleaned.get('ai_content') or ''
            ai_questions = cleaned.get('ai_questions') or ''

            if not description.strip() and ai_content.strip():
                cleaned['description'] = ai_content.strip()
                description = cleaned['description']

            if ai_prompt and len(description.strip()) < 80 and ai_generated != '1':
                raise forms.ValidationError("AI draft is too short. Click 'Generate AI Draft' to create a full quiz.")

            if ai_prompt and ai_generated == '1' and not ai_questions.strip():
                raise forms.ValidationError("AI quiz questions are missing. Click 'Generate AI Draft' again.")

            return cleaned

    form = AIQuizForm
    list_display = ('title', 'section_subject', 'due_date')
    list_filter = ('section_subject',)
    search_fields = ('title', 'section_subject__subject__code')
    ordering = ('-due_date',)
    list_per_page = 25
    autocomplete_fields = ('section_subject',)
    fieldsets = (
        ('AI Generator', {'fields': ('ai_prompt', 'ai_preview', 'ai_generated', 'ai_content', 'ai_questions')}),
        ('Quiz', {'fields': ('title', 'section_subject')}),
        ('Details', {'fields': ('description', 'total_points', 'time_limit_minutes', 'attempt_limit')}),
        ('Schedule', {'fields': ('due_date',)}),
    )
    readonly_fields = ('created_at',)

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path('ai-generate/', self.admin_site.admin_view(self.ai_generate_view), name='quiz-ai-generate'),
        ]
        return custom_urls + urls

    def ai_generate_view(self, request):
        if request.method != 'POST':
            return JsonResponse({'error': 'Method not allowed'}, status=405)

        section_subject_id = request.POST.get('section_subject')
        prompt = request.POST.get('prompt')

        if not section_subject_id or not prompt:
            return JsonResponse({'error': 'section_subject and prompt are required.'}, status=400)

        from subjects.models import SectionSubject

        try:
            section_subject = SectionSubject.objects.select_related('subject').get(id=section_subject_id)
        except SectionSubject.DoesNotExist:
            return JsonResponse({'error': 'Section subject not found.'}, status=404)

        try:
            payload = generate_quiz_with_gemini(
                prompt=prompt,
                subject_name=section_subject.subject.name,
                subject_code=section_subject.subject.code,
            )
        except RateLimitError as exc:
            return JsonResponse(
                {'error': 'Rate limited — try again in 60s.', 'detail': str(exc), 'retry_after': exc.retry_after},
                status=429
            )
        except Exception as exc:
            return JsonResponse(
                {'error': 'AI quiz generation failed.', 'detail': str(exc)},
                status=502
            )

        questions = payload.get('questions') or []
        total_points = 0.0
        for item in questions:
            try:
                total_points += float(item.get('points') or 1.0)
            except Exception:
                total_points += 1.0

        return JsonResponse({
            'title': payload.get('title') or f"{section_subject.subject.name} Quiz",
            'description': payload.get('description') or '',
            'questions': questions,
            'total_points': total_points,
        })

    class Media:
        js = ('quizzes/ai_quiz_admin.js',)

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)

        ai_questions = form.cleaned_data.get('ai_questions') or ''
        ai_generated = form.cleaned_data.get('ai_generated') or ''
        if ai_generated != '1' or not ai_questions:
            return

        if obj.questions.exists():
            return

        try:
            questions = json.loads(ai_questions)
        except Exception:
            return

        total_points = 0.0
        for item in questions:
            q_text = item.get('question_text') or ''
            q_type = item.get('question_type') or 'multiple_choice'
            if q_type == 'mcq':
                q_type = 'multiple_choice'
            points = float(item.get('points') or 1.0)
            question = Question.objects.create(
                quiz=obj,
                question_text=q_text,
                question_type=q_type,
                points=points,
            )
            total_points += points
            choices = item.get('choices') or []
            if q_type in ['multiple_choice', 'true_false']:
                if not choices and q_type == 'true_false':
                    choices = [
                        {"text": "True", "is_correct": bool(item.get("correct"))},
                        {"text": "False", "is_correct": not bool(item.get("correct"))},
                    ]
                for choice in choices:
                    Choice.objects.create(
                        question=question,
                        choice_text=str(choice.get('text') or ''),
                        is_correct=bool(choice.get('is_correct')),
                    )

        if total_points:
            obj.total_points = total_points
            obj.save(update_fields=['total_points'])

@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    list_display = ('question_text', 'quiz', 'question_type', 'points')
    list_filter = ('quiz', 'question_type')
    search_fields = ('question_text', 'quiz__title')
    autocomplete_fields = ('quiz',)
    
@admin.register(Choice)
class ChoiceAdmin(admin.ModelAdmin):
    list_display = ('choice_text', 'question', 'is_correct')
    list_filter = ('is_correct',)
    search_fields = ('choice_text', 'question__question_text')
    autocomplete_fields = ('question',)

@admin.register(QuizAttempt)
class QuizAttemptAdmin(admin.ModelAdmin):
    list_display = ('quiz', 'student', 'score', 'submitted_at')
    list_filter = ('quiz', 'student')
    search_fields = ('quiz__title', 'student__user__first_name', 'student__user__last_name')
    ordering = ('-submitted_at',)
    list_per_page = 30
    autocomplete_fields = ('quiz', 'student')
    actions = ['ai_grade_selected']

    @admin.action(description='AI grade selected attempts')
    def ai_grade_selected(self, request, queryset):
        success_count = 0
        error_count = 0
        for attempt in queryset.select_related('quiz', 'student'):
            try:
                total = 0.0
                for answer in attempt.answers.select_related('question', 'selected_choice'):
                    question = answer.question
                    points = question.points or 0.0
                    if question.question_type in ['multiple_choice', 'true_false']:
                        is_correct = bool(answer.selected_choice and answer.selected_choice.is_correct)
                        answer.is_correct = is_correct
                        answer.points_earned = points if is_correct else 0.0
                    elif question.question_type in ['essay', 'identification']:
                        if answer.text_answer:
                            score, _feedback = grade_quiz_answer_with_gemini(
                                question_text=question.question_text,
                                student_answer=answer.text_answer,
                                points=points,
                            )
                            answer.points_earned = score
                            answer.is_correct = score >= points * 0.7
                        else:
                            answer.points_earned = 0.0
                            answer.is_correct = False
                    else:
                        answer.points_earned = 0.0
                        answer.is_correct = False
                    total += float(answer.points_earned or 0.0)
                    answer.save(update_fields=['points_earned', 'is_correct'])

                attempt.score = total
                if not attempt.submitted_at:
                    attempt.submitted_at = timezone.now()
                attempt.save(update_fields=['score', 'submitted_at'])
                success_count += 1
            except RateLimitError as exc:
                error_count += 1
                messages.error(request, f"AI rate limited. Try again in {exc.retry_after}s.")
            except Exception as exc:
                error_count += 1
                messages.error(request, f"AI grading failed for {attempt.id}: {exc}")

        if success_count:
            messages.success(request, f"AI grading completed for {success_count} attempt(s).")
        if error_count and not success_count:
            messages.warning(request, "No attempts were graded. Check errors above.")

@admin.register(QuizAnswer)
class QuizAnswerAdmin(admin.ModelAdmin):
    list_display = ('attempt', 'question', 'selected_choice', 'points_earned')
    list_filter = ('is_correct',)
    search_fields = ('question__question_text', 'attempt__quiz__title')
    autocomplete_fields = ('attempt', 'question', 'selected_choice')
