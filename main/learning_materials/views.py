from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from rest_framework.authentication import SessionAuthentication
from rest_framework_simplejwt.authentication import JWTAuthentication
from django.http import FileResponse, HttpResponse, HttpResponseRedirect, JsonResponse
import mimetypes
import re
from django.conf import settings
import requests
try:
    from cloudinary.utils import cloudinary_url, private_download_url
    import cloudinary.api
except Exception:  # pragma: no cover - optional dependency
    cloudinary_url = None
    private_download_url = None
    cloudinary = None
from .models import LearningMaterial, FavoriteMaterial
from .serializers import LearningMaterialSerializer
from shared.permissions import IsTeacherOrAdmin, IsStudentOrTeacherOrAdmin
from subjects.models import SectionSubject
from .ai import generate_lesson_with_gemini, RateLimitError
from .pdf_utils import generate_pdf_bytes, generate_pdf_filename, clean_lesson_body
from django.core.files.base import ContentFile
from django.utils.text import slugify
from school_levels.models import SchoolYear
from sections.models import Enrollment
from users.authentication import CookieJWTAuthentication
from django.views.decorators.http import require_GET
from django.utils.timezone import now


class LearningMaterialViewSet(viewsets.ModelViewSet):
    queryset = LearningMaterial.objects.select_related('section_subject')
    serializer_class = LearningMaterialSerializer
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    
    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            permission_classes = [IsTeacherOrAdmin]
        else:
            permission_classes = [IsStudentOrTeacherOrAdmin]
        return [permission() for permission in permission_classes]
    
    def get_queryset(self):
        user = self.request.user
        queryset = LearningMaterial.objects.all()
        school_year_param = self.request.query_params.get('school_year')
        section_subject_param = self.request.query_params.get('section_subject')
        active_school_year = None
        if school_year_param:
            active_school_year = school_year_param
        else:
            active = SchoolYear.objects.filter(is_active=True).first()
            active_school_year = active.id if active else None
        if user.role == 'student':
            return queryset.filter(section_subject__section__enrollments__student__user=user).distinct()
        if user.role in ['instructor', 'adviser']:
            qs = queryset.filter(section_subject__instructor__user=user) | queryset.filter(section_subject__adviser__user=user)
            if active_school_year:
                qs = qs.filter(section_subject__school_year_id=active_school_year)
            if section_subject_param:
                qs = qs.filter(section_subject_id=section_subject_param)
            return qs
        if active_school_year:
            queryset = queryset.filter(section_subject__school_year_id=active_school_year)
        if section_subject_param:
            queryset = queryset.filter(section_subject_id=section_subject_param)
        return queryset

    @action(detail=True, methods=['post'], permission_classes=[IsStudentOrTeacherOrAdmin], url_path='toggle-favorite')
    def toggle_favorite(self, request, pk=None):
        material = self.get_object()
        fav, created = FavoriteMaterial.objects.get_or_create(student=request.user, material=material)
        if not created:
            fav.delete()
            return Response({'is_favorited': False})
        return Response({'is_favorited': True})

    @action(detail=False, methods=['get'], permission_classes=[IsStudentOrTeacherOrAdmin], url_path='favorites')
    def favorites(self, request):
        fav_ids = FavoriteMaterial.objects.filter(student=request.user).values_list('material_id', flat=True)
        materials = LearningMaterial.objects.filter(id__in=fav_ids)
        serializer = LearningMaterialSerializer(materials, many=True, context={'request': request, 'user': request.user})
        return Response(serializer.data)

    @action(detail=False, methods=['post'], permission_classes=[IsTeacherOrAdmin], url_path='ai-generate')
    def ai_generate(self, request):
        section_subject_id = request.data.get('section_subject')
        prompt = request.data.get('prompt')
        lesson_type = request.data.get('type')
        provided_url = request.data.get('file_url')

        if not section_subject_id or not prompt or not lesson_type:
            return Response(
                {"error": "section_subject, prompt, and type are required."},
                status=status.HTTP_400_BAD_REQUEST
            )
        if lesson_type not in ['text', 'pdf']:
            return Response(
                {"error": "Only text and pdf material types are supported."},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            section_subject = SectionSubject.objects.select_related('subject', 'section').get(id=section_subject_id)
        except SectionSubject.DoesNotExist:
            return Response({"error": "Section subject not found."}, status=status.HTTP_404_NOT_FOUND)

        user = request.user
        if user.role in ['instructor', 'adviser']:
            is_owner = (
                (section_subject.instructor_id and section_subject.instructor.user_id == user.id) or
                (section_subject.adviser_id and section_subject.adviser.user_id == user.id)
            )
            if not is_owner:
                return Response({"error": "You do not have access to this section subject."}, status=status.HTTP_403_FORBIDDEN)

        try:
            title, body, resource_url = generate_lesson_with_gemini(
                prompt=prompt,
                subject_name=section_subject.subject.name,
                subject_code=section_subject.subject.code,
                lesson_type=lesson_type,
            )
        except RateLimitError as exc:
            return Response(
                {
                    "error": "Rate limited — try again in 60s.",
                    "detail": str(exc),
                    "retry_after": exc.retry_after,
                },
                status=status.HTTP_429_TOO_MANY_REQUESTS
            )
        except Exception as exc:
            return Response(
                {
                    "error": "AI learning material generation failed. You can still create materials manually.",
                    "detail": str(exc),
                },
                status=status.HTTP_502_BAD_GATEWAY
            )

        file_url = provided_url or resource_url
        if lesson_type in ['link', 'video'] and not file_url:
            return Response(
                {"error": "AI did not return a resource URL. Please provide a link."},
                status=status.HTTP_400_BAD_REQUEST
            )

        cleaned_body = clean_lesson_body(body)
        material = LearningMaterial.objects.create(
            section_subject=section_subject,
            title=title,
            description=cleaned_body,
            type=lesson_type,
            file_url=file_url,
        )

        if lesson_type == 'pdf':
            pdf_bytes = generate_pdf_bytes(
                title,
                cleaned_body,
                subject_code=section_subject.subject.code,
                resource_url=file_url,
            )
            filename = generate_pdf_filename(title, section_subject.subject.code)
            material.attachment.save(filename, ContentFile(pdf_bytes), save=True)
            material.file_url = None
            material.save(update_fields=['file_url'])
        serializer = LearningMaterialSerializer(material, context={"request": request})
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=['post'], permission_classes=[IsTeacherOrAdmin], url_path='ai-preview')
    def ai_preview(self, request):
        section_subject_id = request.data.get('section_subject')
        prompt = request.data.get('prompt')
        lesson_type = request.data.get('type')
        provided_url = request.data.get('file_url')

        if not section_subject_id or not prompt or not lesson_type:
            return Response(
                {"error": "section_subject, prompt, and type are required."},
                status=status.HTTP_400_BAD_REQUEST
            )
        if lesson_type not in ['text', 'pdf']:
            return Response(
                {"error": "Only text and pdf material types are supported."},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            section_subject = SectionSubject.objects.select_related('subject', 'section').get(id=section_subject_id)
        except SectionSubject.DoesNotExist:
            return Response({"error": "Section subject not found."}, status=status.HTTP_404_NOT_FOUND)

        user = request.user
        if user.role in ['instructor', 'adviser']:
            is_owner = (
                (section_subject.instructor_id and section_subject.instructor.user_id == user.id) or
                (section_subject.adviser_id and section_subject.adviser.user_id == user.id)
            )
            if not is_owner:
                return Response({"error": "You do not have access to this section subject."}, status=status.HTTP_403_FORBIDDEN)

        try:
            title, body, resource_url = generate_lesson_with_gemini(
                prompt=prompt,
                subject_name=section_subject.subject.name,
                subject_code=section_subject.subject.code,
                lesson_type=lesson_type,
            )
        except RateLimitError as exc:
            return Response(
                {
                    "error": "Rate limited — try again in 60s.",
                    "detail": str(exc),
                    "retry_after": exc.retry_after,
                },
                status=status.HTTP_429_TOO_MANY_REQUESTS
            )
        except Exception as exc:
            return Response(
                {
                    "error": "AI learning material generation failed. You can still create materials manually.",
                    "detail": str(exc),
                },
                status=status.HTTP_502_BAD_GATEWAY
            )

        file_url = provided_url or resource_url
        if lesson_type in ['link', 'video'] and not file_url:
            return Response(
                {"error": "AI did not return a resource URL. Please provide a link."},
                status=status.HTTP_400_BAD_REQUEST
            )

        cleaned_body = clean_lesson_body(body)
        return Response(
            {
                "section_subject": str(section_subject.id),
                "title": title,
                "description": cleaned_body,
                "type": lesson_type,
                "file_url": file_url,
            },
            status=status.HTTP_200_OK,
        )

    @action(detail=False, methods=['post'], permission_classes=[IsTeacherOrAdmin], url_path='ai-save')
    def ai_save(self, request):
        section_subject_id = request.data.get('section_subject')
        title = request.data.get('title')
        description = request.data.get('description')
        lesson_type = request.data.get('type')
        file_url = request.data.get('file_url')

        if not section_subject_id or not title or not description or not lesson_type:
            return Response(
                {"error": "section_subject, title, description, and type are required."},
                status=status.HTTP_400_BAD_REQUEST
            )
        if lesson_type not in ['text', 'pdf']:
            return Response(
                {"error": "Only text and pdf material types are supported."},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            section_subject = SectionSubject.objects.select_related('subject', 'section').get(id=section_subject_id)
        except SectionSubject.DoesNotExist:
            return Response({"error": "Section subject not found."}, status=status.HTTP_404_NOT_FOUND)

        user = request.user
        if user.role in ['instructor', 'adviser']:
            is_owner = (
                (section_subject.instructor_id and section_subject.instructor.user_id == user.id) or
                (section_subject.adviser_id and section_subject.adviser.user_id == user.id)
            )
            if not is_owner:
                return Response({"error": "You do not have access to this section subject."}, status=status.HTTP_403_FORBIDDEN)

        cleaned_body = clean_lesson_body(description)
        material = LearningMaterial.objects.create(
            section_subject=section_subject,
            title=title,
            description=cleaned_body,
            type=lesson_type,
            file_url=file_url,
        )

        if lesson_type == 'pdf':
            pdf_bytes = generate_pdf_bytes(
                title,
                cleaned_body,
                subject_code=section_subject.subject.code,
                resource_url=file_url,
            )
            filename = generate_pdf_filename(title, section_subject.subject.code)
            material.attachment.save(filename, ContentFile(pdf_bytes), save=True)
            material.file_url = None
            material.save(update_fields=['file_url'])
        serializer = LearningMaterialSerializer(material, context={"request": request})
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=['post'], permission_classes=[IsTeacherOrAdmin], url_path='ai-preview-pdf')
    def ai_preview_pdf(self, request):
        section_subject_id = request.data.get('section_subject')
        title = request.data.get('title')
        description = request.data.get('description')
        file_url = request.data.get('file_url')

        if not section_subject_id or not title or not description:
            return Response(
                {"error": "section_subject, title, and description are required."},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            section_subject = SectionSubject.objects.select_related('subject').get(id=section_subject_id)
        except SectionSubject.DoesNotExist:
            return Response({"error": "Section subject not found."}, status=status.HTTP_404_NOT_FOUND)

        user = request.user
        if user.role in ['instructor', 'adviser']:
            is_owner = (
                (section_subject.instructor_id and section_subject.instructor.user_id == user.id) or
                (section_subject.adviser_id and section_subject.adviser.user_id == user.id)
            )
            if not is_owner:
                return Response({"error": "You do not have access to this section subject."}, status=status.HTTP_403_FORBIDDEN)

        cleaned_body = clean_lesson_body(description)
        pdf_bytes = generate_pdf_bytes(
            title,
            cleaned_body,
            subject_code=section_subject.subject.code,
            resource_url=file_url,
        )
        filename = generate_pdf_filename(title, section_subject.subject.code)
        response = HttpResponse(pdf_bytes, content_type='application/pdf')
        response['Content-Disposition'] = f'inline; filename=\"{filename}\"'
        return response

    @action(
        detail=True,
        methods=['get'],
        permission_classes=[IsStudentOrTeacherOrAdmin],
        authentication_classes=[CookieJWTAuthentication, JWTAuthentication, SessionAuthentication],
        url_path='download',
    )
    def download(self, request, pk=None):
        material = self.get_object()
        if material.attachment:
            try:
                file_handle = material.attachment.open('rb')
                content_type, _ = mimetypes.guess_type(material.attachment.name)
                response = FileResponse(file_handle, content_type=content_type or 'application/octet-stream')
                filename = material.attachment.name.split('/')[-1]
                response['Content-Disposition'] = f'inline; filename=\"{filename}\"'
                return response
            except Exception:
                attachment_url = getattr(material.attachment, 'url', None)
            signed_url = None
            if cloudinary_url and attachment_url and settings.CLOUDINARY_CLOUD_NAME:
                resource_types = []
                if '/image/' in attachment_url:
                    resource_types.append('image')
                elif '/video/' in attachment_url:
                    resource_types.append('video')
                elif '/raw/' in attachment_url:
                    resource_types.append('raw')
                resource_types.extend([t for t in ['raw', 'image', 'video'] if t not in resource_types])
                public_id = material.attachment.name
                filename = material.attachment.name.split('/')[-1]
                name_without_ext = filename.rsplit('.', 1)[0]
                match = re.search(r'/upload/(?:v\d+/)?(.+)$', attachment_url)
                if match:
                    public_id = match.group(1)
                candidates = []
                for resource_type in resource_types:
                    for access_type, sign in [('authenticated', True), ('upload', False), ('upload', True)]:
                        candidates.append((resource_type, access_type, sign))
                for resource_type, access_type, sign in candidates:
                    signed_url, _ = cloudinary_url(
                        public_id,
                        resource_type=resource_type,
                        secure=True,
                        sign_url=sign,
                        type=access_type,
                    )
                    try:
                        resp = requests.get(signed_url, stream=True, timeout=10)
                        if resp.status_code == 200:
                            content_type = resp.headers.get('Content-Type')
                            response = FileResponse(resp.raw, content_type=content_type or 'application/octet-stream')
                            response['Content-Disposition'] = f'inline; filename=\"{filename}\"'
                            return response
                    except requests.RequestException:
                        continue
                # Try with public_id without extension if Cloudinary stored it that way.
                for resource_type, access_type, sign in candidates:
                    signed_url, _ = cloudinary_url(
                        name_without_ext,
                        resource_type=resource_type,
                        secure=True,
                        sign_url=sign,
                        type=access_type,
                    )
                    try:
                        resp = requests.get(signed_url, stream=True, timeout=10)
                        if resp.status_code == 200:
                            content_type = resp.headers.get('Content-Type')
                            response = FileResponse(resp.raw, content_type=content_type or 'application/octet-stream')
                            response['Content-Disposition'] = f'inline; filename=\"{filename}\"'
                            return response
                    except requests.RequestException:
                        continue
                # As a last resort, use Cloudinary's authenticated download API (bypasses delivery restrictions).
                if private_download_url:
                    file_ext = filename.split('.')[-1] if '.' in filename else 'pdf'
                    for resource_type in resource_types:
                        try:
                            api_url = private_download_url(
                                public_id,
                                file_ext,
                                resource_type=resource_type,
                                type='authenticated',
                            )
                            resp = requests.get(api_url, stream=True, timeout=15)
                            if resp.status_code == 200:
                                content_type = resp.headers.get('Content-Type')
                                response = FileResponse(resp.raw, content_type=content_type or 'application/octet-stream')
                                response['Content-Disposition'] = f'inline; filename=\"{filename}\"'
                                return response
                        except requests.RequestException:
                            continue
                # Final fallback: ask Cloudinary Admin API to resolve correct type/format.
                if cloudinary and hasattr(cloudinary, 'api'):
                    for resource_type in ['raw', 'image', 'video']:
                        for access_type in ['authenticated', 'upload']:
                            try:
                                info = cloudinary.api.resource(public_id, resource_type=resource_type, type=access_type)
                                fmt = info.get('format') or (filename.split('.')[-1] if '.' in filename else 'pdf')
                                api_url = private_download_url(
                                    info.get('public_id', public_id),
                                    fmt,
                                    resource_type=resource_type,
                                    type=access_type,
                                )
                                resp = requests.get(api_url, stream=True, timeout=15)
                                if resp.status_code == 200:
                                    content_type = resp.headers.get('Content-Type')
                                    response = FileResponse(resp.raw, content_type=content_type or 'application/octet-stream')
                                    response['Content-Disposition'] = f'inline; filename=\"{filename}\"'
                                    return response
                            except Exception:
                                continue
                return Response(
                    {"error": "Unable to access file from storage. Please check Cloudinary settings."},
                    status=status.HTTP_502_BAD_GATEWAY,
                )
            if attachment_url:
                # Avoid redirecting to third-party storage to prevent CORS/auth issues.
                return Response(
                    {"error": "File URL requires authentication. Please use the download endpoint."},
                    status=status.HTTP_403_FORBIDDEN,
                )
        if material.file_url:
            return HttpResponseRedirect(material.file_url)
        return Response({"error": "No file available."}, status=status.HTTP_404_NOT_FOUND)


@require_GET
def cloudinary_healthcheck(request):
    if not settings.CLOUDINARY_CLOUD_NAME or not settings.CLOUDINARY_API_KEY or not settings.CLOUDINARY_API_SECRET:
        return JsonResponse(
            {"status": "error", "detail": "Cloudinary credentials are missing in environment."},
            status=500,
        )
    if not cloudinary or not hasattr(cloudinary, 'api'):
        return JsonResponse(
            {"status": "error", "detail": "Cloudinary SDK not available."},
            status=500,
        )
    try:
        usage = cloudinary.api.usage()
        return JsonResponse(
            {
                "status": "ok",
                "cloud_name": settings.CLOUDINARY_CLOUD_NAME,
                "credits": usage.get("credits"),
                "timestamp": now().isoformat(),
            }
        )
    except Exception as exc:
        return JsonResponse(
            {"status": "error", "detail": str(exc)},
            status=502,
        )
