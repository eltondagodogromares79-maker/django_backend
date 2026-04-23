from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from django.http import HttpResponse
from .models import Assignment, AssignmentSubmission
from .serializers import AssignmentSerializer, AssignmentSubmissionSerializer, AssignmentSubmissionGradeSerializer
from .permissions import IsTeacherOrAdmin, IsStudentOrTeacherOrAdmin, IsOwnerOrTeacherOrAdmin, CanGradeSubmission
from .ai import grade_assignment_with_gemini, generate_assignment_with_gemini, RateLimitError
from django.utils import timezone
from django.utils import timezone as dj_timezone
from django.utils.dateparse import parse_datetime
from subjects.models import SectionSubject
from datetime import timedelta
from io import BytesIO
from zipfile import ZipFile, ZIP_DEFLATED
import requests
from school_levels.models import SchoolYear
from sections.models import Enrollment


class AssignmentViewSet(viewsets.ModelViewSet):
    queryset = Assignment.objects.select_related('section_subject')
    serializer_class = AssignmentSerializer

    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            permission_classes = [IsTeacherOrAdmin]
        else:
            permission_classes = [IsStudentOrTeacherOrAdmin]
        return [permission() for permission in permission_classes]

    def get_queryset(self):
        user = self.request.user
        school_year_param = self.request.query_params.get('school_year')
        section_subject_param = self.request.query_params.get('section_subject')
        active_school_year = None
        if school_year_param:
            active_school_year = school_year_param
        else:
            active = SchoolYear.objects.filter(is_active=True).first()
            active_school_year = active.id if active else None
        if user.role == 'student':
            return Assignment.objects.filter(section_subject__section__enrollments__student__user=user).distinct()
        if user.role in ['instructor', 'adviser']:
            qs = Assignment.objects.filter(
                section_subject__instructor__user=user
            ) | Assignment.objects.filter(
                section_subject__adviser__user=user
            )
            if active_school_year:
                qs = qs.filter(section_subject__school_year_id=active_school_year)
            if section_subject_param:
                qs = qs.filter(section_subject_id=section_subject_param)
            return qs
        qs = super().get_queryset()
        if active_school_year:
            qs = qs.filter(section_subject__school_year_id=active_school_year)
        if section_subject_param:
            qs = qs.filter(section_subject_id=section_subject_param)
        return qs

    @action(detail=False, methods=['post'], permission_classes=[IsTeacherOrAdmin], url_path='ai-generate')
    def ai_generate(self, request):
        section_subject_id = request.data.get('section_subject')
        prompt = request.data.get('prompt')
        due_date_raw = request.data.get('due_date')
        total_points_raw = request.data.get('total_points')
        allow_late_raw = request.data.get('allow_late_submission', False)

        if not section_subject_id or not prompt:
            return Response(
                {"error": "section_subject and prompt are required."},
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

        due_date = None
        if due_date_raw:
            due_date = parse_datetime(due_date_raw)
        if not due_date:
            due_date = dj_timezone.now() + timedelta(days=7)
        if due_date < dj_timezone.now():
            return Response({"error": "Due date cannot be in the past."}, status=status.HTTP_400_BAD_REQUEST)

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
                    "error": "AI assignment generation failed. You can still create assignments manually.",
                    "detail": str(exc),
                },
                status=status.HTTP_502_BAD_GATEWAY
            )

        allow_late = str(allow_late_raw).lower() in ['1', 'true', 'yes']
        assignment = Assignment.objects.create(
            section_subject=section_subject,
            created_by=request.user,
            title=title,
            description=description,
            total_points=final_points,
            due_date=due_date,
            allow_late_submission=allow_late,
        )

        serializer = AssignmentSerializer(assignment, context={"request": request})
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=['post'], permission_classes=[IsTeacherOrAdmin], url_path='ai-preview')
    def ai_preview(self, request):
        section_subject_id = request.data.get('section_subject')
        prompt = request.data.get('prompt')
        due_date_raw = request.data.get('due_date')
        total_points_raw = request.data.get('total_points')
        allow_late_raw = request.data.get('allow_late_submission', False)

        if not section_subject_id or not prompt:
            return Response(
                {"error": "section_subject and prompt are required."},
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

        due_date = parse_datetime(due_date_raw) if due_date_raw else None
        if not due_date:
            due_date = dj_timezone.now() + timedelta(days=7)
        if due_date < dj_timezone.now():
            return Response({"error": "Due date cannot be in the past."}, status=status.HTTP_400_BAD_REQUEST)

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
                    "error": "AI assignment generation failed. You can still create assignments manually.",
                    "detail": str(exc),
                },
                status=status.HTTP_502_BAD_GATEWAY
            )

        allow_late = str(allow_late_raw).lower() in ['1', 'true', 'yes']
        return Response(
            {
                "section_subject": str(section_subject.id),
                "title": title,
                "description": description,
                "total_points": final_points,
                "due_date": due_date.isoformat(),
                "allow_late_submission": allow_late,
            },
            status=status.HTTP_200_OK,
        )

    @action(detail=False, methods=['post'], permission_classes=[IsTeacherOrAdmin], url_path='ai-save')
    def ai_save(self, request):
        section_subject_id = request.data.get('section_subject')
        title = request.data.get('title')
        description = request.data.get('description')
        due_date_raw = request.data.get('due_date')
        total_points_raw = request.data.get('total_points')
        allow_late_raw = request.data.get('allow_late_submission', False)

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

        due_date = parse_datetime(due_date_raw) if due_date_raw else None
        if not due_date:
            due_date = dj_timezone.now() + timedelta(days=7)
        if due_date < dj_timezone.now():
            return Response({"error": "Due date cannot be in the past."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            total_points = float(total_points_raw) if total_points_raw is not None else 100.0
        except Exception:
            total_points = 100.0

        allow_late = str(allow_late_raw).lower() in ['1', 'true', 'yes']
        assignment = Assignment.objects.create(
            section_subject=section_subject,
            created_by=request.user,
            title=title,
            description=description,
            total_points=total_points,
            due_date=due_date,
            allow_late_submission=allow_late,
        )

        serializer = AssignmentSerializer(assignment, context={"request": request})
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['get'], permission_classes=[IsStudentOrTeacherOrAdmin])
    def submissions(self, request, pk=None):
        assignment = self.get_object()
        submissions = AssignmentSubmission.objects.filter(assignment=assignment)
        if request.user.role == 'student':
            submissions = submissions.filter(student__user=request.user)
        serializer = AssignmentSubmissionSerializer(submissions, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['get'], permission_classes=[IsTeacherOrAdmin], url_path='download-submissions')
    def download_submissions(self, request, pk=None):
        assignment = self.get_object()
        submissions = AssignmentSubmission.objects.filter(assignment=assignment).select_related('student__user')
        buffer = BytesIO()
        with ZipFile(buffer, 'w', ZIP_DEFLATED) as zip_file:
            for submission in submissions:
                student_name = submission.student.user.get_full_name() if submission.student_id else 'student'
                safe_name = ''.join(c if c.isalnum() or c in [' ', '-', '_'] else '_' for c in student_name).strip() or 'student'
                base_name = f"{safe_name}_{submission.id}"
                if submission.text_answer:
                    zip_file.writestr(f"{base_name}_answer.txt", submission.text_answer)
                if submission.file_url:
                    try:
                        response = requests.get(submission.file_url, timeout=10)
                        response.raise_for_status()
                        content = response.content
                        extension = submission.file_url.split('.')[-1].split('?')[0][:6]
                        extension = extension if extension.isalnum() else 'file'
                        zip_file.writestr(f"{base_name}_attachment.{extension}", content)
                    except Exception:
                        zip_file.writestr(
                            f"{base_name}_attachment_link.txt",
                            f"Download link: {submission.file_url}"
                        )
        buffer.seek(0)
        response = HttpResponse(buffer.getvalue(), content_type='application/zip')
        response['Content-Disposition'] = f'attachment; filename="assignment_{assignment.id}_submissions.zip"'
        return response


class AssignmentSubmissionViewSet(viewsets.ModelViewSet):
    queryset = AssignmentSubmission.objects.select_related('assignment', 'student')
    serializer_class = AssignmentSubmissionSerializer

    def get_permissions(self):
        if self.action == 'create':
            permission_classes = [permissions.IsAuthenticated]
        elif self.action in ['update', 'partial_update']:
            permission_classes = [IsOwnerOrTeacherOrAdmin]
        elif self.action == 'grade':
            permission_classes = [CanGradeSubmission]
        else:
            permission_classes = [IsStudentOrTeacherOrAdmin]
        return [permission() for permission in permission_classes]

    def get_queryset(self):
        user = self.request.user
        if user.role == 'student':
            return AssignmentSubmission.objects.filter(student__user=user)
        if user.role in ['instructor', 'adviser']:
            return AssignmentSubmission.objects.filter(assignment__section_subject__instructor__user=user)
        return super().get_queryset()

    def create(self, request, *args, **kwargs):
        if request.user.role != 'student':
            return Response({'error': 'Only students can submit assignments'}, status=status.HTTP_403_FORBIDDEN)
        return super().create(request, *args, **kwargs)

    @action(detail=True, methods=['patch'], permission_classes=[CanGradeSubmission])
    def grade(self, request, pk=None):
        submission = self.get_object()
        serializer = AssignmentSubmissionGradeSerializer(submission, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['post'], permission_classes=[CanGradeSubmission])
    def ai_grade(self, request, pk=None):
        submission = self.get_object()
        assignment = submission.assignment

        answer_parts = []
        if submission.text_answer:
            answer_parts.append(submission.text_answer)
        if submission.file_url:
            answer_parts.append(f"Attachment link: {submission.file_url}")
        student_answer = "\n\n".join(answer_parts).strip()

        if not student_answer:
            return Response(
                {"error": "No student answer found to grade."},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            score, feedback = grade_assignment_with_gemini(
                assignment_title=assignment.title,
                assignment_description=assignment.description,
                total_points=assignment.total_points,
                student_answer=student_answer,
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
                    "error": "AI grading failed. You can still grade manually.",
                    "detail": str(exc),
                },
                status=status.HTTP_502_BAD_GATEWAY
            )

        submission.score = score
        submission.feedback = feedback
        submission.graded_at = timezone.now()
        submission.save(update_fields=['score', 'feedback', 'graded_at'])

        return Response(AssignmentSubmissionSerializer(submission).data, status=status.HTTP_200_OK)
