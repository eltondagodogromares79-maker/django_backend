from django import forms
from django.contrib import admin, messages
from django.utils.html import format_html
from django.core.exceptions import ValidationError
from django.http import JsonResponse
from django.urls import path, reverse
from .models import LearningMaterial
from .ai import generate_lesson_with_gemini, RateLimitError
from .pdf_utils import generate_pdf_bytes, generate_pdf_filename, clean_lesson_body
from django.core.files.base import ContentFile


@admin.register(LearningMaterial)
class LearningMaterialAdmin(admin.ModelAdmin):
    class AILessonForm(forms.ModelForm):
        ai_prompt = forms.CharField(
            required=False,
            widget=forms.Textarea(attrs={'rows': 4}),
            label='AI prompt (optional)',
            help_text='Describe the learning material you want to generate.'
        )
        ai_type = forms.ChoiceField(
            required=False,
            choices=[
                ('text', 'Text'),
                ('pdf', 'PDF'),
            ],
            label='AI material type',
            help_text='Choose the format for the learning material.'
        )
        ai_link = forms.URLField(
            required=False,
            label='Resource link (optional)',
            help_text='If the AI does not return a link, provide one here.'
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
            model = LearningMaterial
            fields = '__all__'

        def clean(self):
            cleaned = super().clean()
            lesson_type = cleaned.get('type')
            description = cleaned.get('description') or ''
            section_subject = cleaned.get('section_subject')
            file_url = cleaned.get('file_url')
            ai_prompt = cleaned.get('ai_prompt') or ''
            ai_generated = cleaned.get('ai_generated') or ''
            ai_content = cleaned.get('ai_content') or ''

            if not description.strip() and ai_content.strip():
                cleaned['description'] = ai_content.strip()
                description = cleaned['description']

            if description:
                cleaned_description = clean_lesson_body(description)
                cleaned['description'] = cleaned_description
                description = cleaned_description

            if ai_prompt and len(description.strip()) < 200 and ai_generated != '1':
                raise ValidationError("AI draft is too short. Click 'Generate AI Draft' to create a full learning material.")

            if lesson_type == 'pdf':
                # If a PDF file was manually uploaded, skip AI/manual PDF generation.
                if cleaned.get('attachment'):
                    return cleaned
                if not description.strip():
                    raise ValidationError("PDF learning materials require content in the description or a PDF upload.")
                try:
                    subject_code = section_subject.subject.code if section_subject else None
                    pdf_bytes = generate_pdf_bytes(
                        cleaned.get('title') or 'Learning Material',
                        description,
                        subject_code=subject_code,
                        resource_url=file_url,
                    )
                    cleaned['_pdf_bytes'] = pdf_bytes
                    cleaned['_pdf_filename'] = generate_pdf_filename(
                        cleaned.get('title') or 'Learning Material',
                        subject_code,
                    )
                except Exception as exc:
                    raise ValidationError(f"PDF generation failed: {exc}")

            return cleaned

    form = AILessonForm
    list_display = ('title', 'section_subject', 'type', 'attachment_link', 'created_at')
    list_filter = ('type', 'created_at')
    search_fields = ('title', 'section_subject__subject__code')
    ordering = ('-created_at',)
    list_per_page = 25
    autocomplete_fields = ('section_subject',)
    fieldsets = (
        ('AI Generator', {'fields': ('ai_prompt', 'ai_type', 'ai_link', 'ai_generated', 'ai_content')}),
        ('Material', {'fields': ('section_subject', 'title', 'description')}),
        ('Content', {'fields': ('type', 'attachment', 'file_url')}),
    )
    readonly_fields = ('created_at',)

    @admin.display(description='PDF')
    def attachment_link(self, obj):
        if obj.attachment:
            return format_html(
                '<a href="{}" target="_blank" rel="noopener">View PDF</a>',
                reverse('learning-material-download', kwargs={'pk': obj.pk})
            )
        return '-'

    def save_model(self, request, obj, form, change):
        if obj.type == 'pdf':
            pdf_bytes = form.cleaned_data.get('_pdf_bytes')
            pdf_filename = form.cleaned_data.get('_pdf_filename')
            if pdf_bytes and pdf_filename and not form.cleaned_data.get('attachment'):
                obj.attachment.save(pdf_filename, ContentFile(pdf_bytes), save=False)
                obj.file_url = None

        super().save_model(request, obj, form, change)

        if obj.type == 'pdf' and form.cleaned_data.get('_pdf_bytes'):
            messages.success(request, "PDF generated successfully.")

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path('ai-generate/', self.admin_site.admin_view(self.ai_generate_view), name='learningmaterial-ai-generate'),
        ]
        return custom_urls + urls

    def ai_generate_view(self, request):
        if request.method != 'POST':
            return JsonResponse({'error': 'Method not allowed'}, status=405)

        section_subject_id = request.POST.get('section_subject')
        prompt = request.POST.get('prompt')
        lesson_type = request.POST.get('type')
        provided_url = request.POST.get('file_url')

        if not section_subject_id or not prompt or not lesson_type:
            return JsonResponse({'error': 'section_subject, prompt, and type are required.'}, status=400)

        from subjects.models import SectionSubject

        try:
            section_subject = SectionSubject.objects.select_related('subject').get(id=section_subject_id)
        except SectionSubject.DoesNotExist:
            return JsonResponse({'error': 'Section subject not found.'}, status=404)

        try:
            title, body, resource_url = generate_lesson_with_gemini(
                prompt=prompt,
                subject_name=section_subject.subject.name,
                subject_code=section_subject.subject.code,
                lesson_type=lesson_type,
            )
        except RateLimitError as exc:
            return JsonResponse(
                {'error': 'Rate limited — try again in 60s.', 'detail': str(exc), 'retry_after': exc.retry_after},
                status=429
            )
        except Exception as exc:
            return JsonResponse(
                {'error': 'AI learning material generation failed.', 'detail': str(exc)},
                status=502
            )

        file_url = provided_url or resource_url
        if lesson_type in ['link', 'video'] and not file_url:
            return JsonResponse({'error': 'AI did not return a resource URL. Provide a link.'}, status=400)

        return JsonResponse({
            'title': title,
            'description': body,
            'body': body,
            'content': body,
            'raw': str(body)[:4000],
            'type': lesson_type,
            'file_url': file_url or '',
        })

    class Media:
        js = ('learning_materials/ai_lesson_admin.js',)
