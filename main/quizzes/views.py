from rest_framework import viewsets, status, serializers
import logging
from rest_framework.decorators import action
from rest_framework.response import Response
from django.db import models
from django.utils import timezone
from .models import (
    Quiz, Question, Choice, QuizAttempt, QuizAnswer,
    QuizProctorSession, QuizProctorEvent, QuizProctorSnapshot, QuizFilterPreference
)
from .serializers import (
    QuizSerializer, QuestionSerializer, ChoiceSerializer,
    QuizAttemptSerializer, QuizAnswerSerializer, QuizFilterPreferenceSerializer
)
from shared.permissions import IsTeacherOrAdmin, IsStudentOrTeacherOrAdmin, IsOwnerOrTeacherOrAdmin
from .ai import generate_quiz_with_gemini, grade_quiz_answer_with_gemini, RateLimitError
from django.utils import timezone as dj_timezone
from django.utils.dateparse import parse_datetime
from subjects.models import SectionSubject
from datetime import timedelta
from school_levels.models import SchoolYear
from sections.models import Enrollment
from users.models import Student
from django.conf import settings

try:
    import cloudinary
    import cloudinary.uploader
except Exception:
    cloudinary = None


def _get_student_from_user(user):
    if user.role != 'student':
        return None
    return Student.objects.filter(user=user).first()


def _upload_proctor_snapshot(image_data: str, reason: str | None):
    if not image_data:
        return None
    if not cloudinary or not hasattr(cloudinary, 'uploader'):
        return None
    try:
        result = cloudinary.uploader.upload(
            image_data,
            folder='quiz_proctor',
            resource_type='image',
            overwrite=False,
        )
        return result.get('secure_url')
    except Exception:
        return None


def _apply_penalty(raw_score: float, penalty_percent: int) -> float:
    if penalty_percent <= 0:
        return raw_score
    multiplier = max(0.0, 1.0 - (penalty_percent / 100.0))
    return max(0.0, raw_score * multiplier)


def _latest_penalty_for(student, quiz):
    session = QuizProctorSession.objects.filter(
        quiz=quiz,
        student=student
    ).order_by('-started_at').first()
    if not session:
        return 0
    return session.penalty_percent or 0


class QuizViewSet(viewsets.ModelViewSet):
    queryset = Quiz.objects.select_related('section_subject')
    serializer_class = QuizSerializer

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
            return Quiz.objects.filter(section_subject__section__enrollments__student__user=user).distinct()
        if user.role in ['instructor', 'adviser']:
            qs = Quiz.objects.filter(section_subject__instructor__user=user) | Quiz.objects.filter(section_subject__adviser__user=user)
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

    @action(detail=True, methods=['get'], permission_classes=[IsStudentOrTeacherOrAdmin], url_path='proctor-logs')
    def proctor_logs(self, request, pk=None):
        quiz = self.get_object()
        user = request.user
        student_id = request.query_params.get('student_id')
        attempt_id = request.query_params.get('attempt_id')
        if user.role in ['instructor', 'adviser']:
            is_owner = (
                (quiz.section_subject.instructor_id and quiz.section_subject.instructor.user_id == user.id) or
                (quiz.section_subject.adviser_id and quiz.section_subject.adviser.user_id == user.id)
            )
            if not is_owner:
                return Response({'error': 'Forbidden'}, status=status.HTTP_403_FORBIDDEN)
        if user.role == 'student':
            student = _get_student_from_user(user)
            if not student:
                return Response({'error': 'Student profile not found.'}, status=status.HTTP_400_BAD_REQUEST)
            student_id = str(student.id)

        sessions = QuizProctorSession.objects.filter(quiz=quiz)
        if student_id:
            sessions = sessions.filter(student_id=student_id)
        if attempt_id:
            sessions = sessions.filter(attempt_id=attempt_id)
        sessions = sessions.select_related('student__user').prefetch_related('events', 'snapshots')

        payload = []
        for session in sessions:
            payload.append({
                'id': str(session.id),
                'student_id': str(session.student_id),
                'student_name': session.student.user.get_full_name(),
                'attempt_id': str(session.attempt_id) if session.attempt_id else None,
                'status': session.status,
                'warnings': session.warnings_count,
                'terminations': session.terminations_count,
                'penalty_percent': session.penalty_percent,
                'started_at': session.started_at.isoformat(),
                'ended_at': session.ended_at.isoformat() if session.ended_at else None,
                'events': [
                    {
                        'id': str(event.id),
                        'type': event.event_type,
                        'detail': event.detail,
                        'created_at': event.created_at.isoformat(),
                    }
                    for event in session.events.all()
                ],
                'snapshots': [
                    {
                        'id': str(snapshot.id),
                        'image_url': snapshot.image_url,
                        'reason': snapshot.reason,
                        'created_at': snapshot.created_at.isoformat(),
                    }
                    for snapshot in session.snapshots.all()
                ],
            })
        return Response(payload)

    @action(detail=True, methods=['post'], permission_classes=[IsStudentOrTeacherOrAdmin], url_path='proctor/start')
    def proctor_start(self, request, pk=None):
        if request.user.role != 'student':
            return Response({'error': 'Only students can start proctoring.'}, status=status.HTTP_403_FORBIDDEN)
        quiz = self.get_object()
        if not quiz.is_available:
            return Response({'error': 'Quiz is not yet available.'}, status=status.HTTP_403_FORBIDDEN)
        student = _get_student_from_user(request.user)
        if not student:
            return Response({'error': 'Student profile not found.'}, status=status.HTTP_400_BAD_REQUEST)
        device_id = request.data.get('device_id') or request.headers.get('X-Device-Id')
        now = timezone.now()
        stale_threshold = now - timedelta(seconds=35)
        QuizProctorSession.objects.filter(
            quiz=quiz,
            student=student,
            status='active',
            last_heartbeat__lt=stale_threshold,
        ).update(status='ended', ended_at=now)

        last_session = QuizProctorSession.objects.filter(quiz=quiz, student=student).order_by('-started_at').first()
        if last_session and last_session.terminations_count >= 3:
            return Response({'error': 'Exam blocked due to repeated violations.', 'blocked': True}, status=status.HTTP_403_FORBIDDEN)

        active = QuizProctorSession.objects.filter(quiz=quiz, student=student, status='active').order_by('-started_at').first()
        if active and device_id and active.device_id and active.device_id != device_id:
            return Response({'error': 'Active session on another device.', 'code': 'active_session'}, status=status.HTTP_409_CONFLICT)

        if active:
            return Response({
                'session_id': str(active.id),
                'warnings': active.warnings_count,
                'terminations': active.terminations_count,
                'penalty_percent': active.penalty_percent,
                'status': active.status,
            })

        session = QuizProctorSession.objects.create(
            quiz=quiz,
            student=student,
            status='active',
            device_id=device_id,
            terminations_count=last_session.terminations_count if last_session else 0,
            penalty_percent=0,
            last_heartbeat=now,
        )
        QuizProctorEvent.objects.create(session=session, event_type='start', detail='Session started')
        return Response({
            'session_id': str(session.id),
            'warnings': session.warnings_count,
            'terminations': session.terminations_count,
            'penalty_percent': session.penalty_percent,
            'status': session.status,
        }, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=['post'], permission_classes=[IsTeacherOrAdmin], url_path='ai-generate')
    def ai_generate(self, request):
        section_subject_id = request.data.get('section_subject')
        prompt = request.data.get('prompt')
        due_date_raw = request.data.get('due_date')
        time_limit_raw = request.data.get('time_limit_minutes')
        attempt_limit_raw = request.data.get('attempt_limit')
        is_available_raw = request.data.get('is_available')
        is_available = (
            str(is_available_raw).lower() in ['1', 'true', 'yes']
            if is_available_raw is not None
            else False
        )

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
            time_limit = int(time_limit_raw) if time_limit_raw is not None else None
        except Exception:
            time_limit = None
        try:
            attempt_limit = int(attempt_limit_raw) if attempt_limit_raw is not None else 1
        except Exception:
            attempt_limit = 1

        try:
            payload = generate_quiz_with_gemini(
                prompt=prompt,
                subject_name=section_subject.subject.name,
                subject_code=section_subject.subject.code,
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
                    "error": "AI quiz generation failed. You can still create quizzes manually.",
                    "detail": str(exc),
                },
                status=status.HTTP_502_BAD_GATEWAY
            )

        title = payload.get("title") or f"{section_subject.subject.name} Quiz"
        description = payload.get("description") or ""
        time_limit = payload.get("time_limit_minutes") or time_limit
        attempt_limit = payload.get("attempt_limit") or attempt_limit
        questions_data = payload.get("questions") or []

        quiz = Quiz.objects.create(
            section_subject=section_subject,
            title=title,
            description=description,
            total_points=0.0,
            time_limit_minutes=time_limit,
            attempt_limit=attempt_limit,
            due_date=due_date,
            security_level=request.data.get('security_level') or 'normal',
            is_available=is_available,
        )

        total_points = 0.0
        for item in questions_data:
            q_text = item.get("question_text") or ""
            q_type = item.get("question_type") or "multiple_choice"
            if q_type == "mcq":
                q_type = "multiple_choice"
            points = float(item.get("points") or 1.0)
            question = Question.objects.create(
                quiz=quiz,
                question_text=q_text,
                question_type=q_type,
                points=points,
            )
            total_points += points
            choices = item.get("choices") or []
            if q_type in ["multiple_choice", "true_false"]:
                if not choices and q_type == "true_false":
                    choices = [
                        {"text": "True", "is_correct": bool(item.get("correct"))},
                        {"text": "False", "is_correct": not bool(item.get("correct"))},
                    ]
                for choice in choices:
                    Choice.objects.create(
                        question=question,
                        choice_text=str(choice.get("text") or ""),
                        is_correct=bool(choice.get("is_correct")),
                    )

        quiz.total_points = total_points
        quiz.save(update_fields=['total_points'])
        serializer = QuizSerializer(quiz, context={"request": request})
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=['post'], permission_classes=[IsTeacherOrAdmin], url_path='ai-preview')
    def ai_preview(self, request):
        section_subject_id = request.data.get('section_subject')
        prompt = request.data.get('prompt')
        due_date_raw = request.data.get('due_date')
        time_limit_raw = request.data.get('time_limit_minutes')
        attempt_limit_raw = request.data.get('attempt_limit')
        ai_grade_on_submit = request.data.get('ai_grade_on_submit')
        security_level = request.data.get('security_level') or 'normal'
        is_available_raw = request.data.get('is_available')
        is_available = (
            str(is_available_raw).lower() in ['1', 'true', 'yes']
            if is_available_raw is not None
            else False
        )

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
            time_limit = int(time_limit_raw) if time_limit_raw is not None else None
        except Exception:
            time_limit = None
        try:
            attempt_limit = int(attempt_limit_raw) if attempt_limit_raw is not None else 1
        except Exception:
            attempt_limit = 1

        try:
            payload = generate_quiz_with_gemini(
                prompt=prompt,
                subject_name=section_subject.subject.name,
                subject_code=section_subject.subject.code,
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
                    "error": "AI quiz generation failed. You can still create quizzes manually.",
                    "detail": str(exc),
                },
                status=status.HTTP_502_BAD_GATEWAY
            )

        title = payload.get("title") or f"{section_subject.subject.name} Quiz"
        description = payload.get("description") or ""
        time_limit = payload.get("time_limit_minutes") or time_limit
        attempt_limit = payload.get("attempt_limit") or attempt_limit
        questions_data = payload.get("questions") or []
        total_points = 0.0
        for item in questions_data:
            try:
                total_points += float(item.get("points") or 1.0)
            except Exception:
                total_points += 1.0

        return Response(
            {
                "section_subject": str(section_subject.id),
                "title": title,
                "description": description,
                "time_limit_minutes": time_limit,
                "attempt_limit": attempt_limit,
                "due_date": due_date.isoformat(),
                "security_level": security_level,
                "is_available": is_available,
                "questions": questions_data,
                "total_points": total_points,
                "ai_grade_on_submit": bool(ai_grade_on_submit) if ai_grade_on_submit is not None else True,
            },
            status=status.HTTP_200_OK,
        )

    @action(detail=False, methods=['post'], permission_classes=[IsTeacherOrAdmin], url_path='ai-save')
    def ai_save(self, request):
        section_subject_id = request.data.get('section_subject')
        title = request.data.get('title')
        description = request.data.get('description')
        due_date_raw = request.data.get('due_date')
        time_limit_raw = request.data.get('time_limit_minutes')
        attempt_limit_raw = request.data.get('attempt_limit')
        ai_grade_on_submit = request.data.get('ai_grade_on_submit')
        security_level = request.data.get('security_level') or 'normal'
        is_available_raw = request.data.get('is_available')
        is_available = (
            str(is_available_raw).lower() in ['1', 'true', 'yes']
            if is_available_raw is not None
            else False
        )
        questions_data = request.data.get('questions') or []

        if not section_subject_id or not title:
            return Response(
                {"error": "section_subject and title are required."},
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
            time_limit = int(time_limit_raw) if time_limit_raw is not None else None
        except Exception:
            time_limit = None
        try:
            attempt_limit = int(attempt_limit_raw) if attempt_limit_raw is not None else 1
        except Exception:
            attempt_limit = 1

        quiz = Quiz.objects.create(
            section_subject=section_subject,
            title=title,
            description=description or "",
            total_points=0.0,
            time_limit_minutes=time_limit,
            attempt_limit=attempt_limit,
            due_date=due_date,
            ai_grade_on_submit=bool(ai_grade_on_submit) if ai_grade_on_submit is not None else True,
            security_level=security_level,
            is_available=is_available,
        )

        total_points = 0.0
        for item in questions_data:
            q_text = item.get("question_text") or ""
            q_type = item.get("question_type") or "multiple_choice"
            if q_type == "mcq":
                q_type = "multiple_choice"
            points = float(item.get("points") or 1.0)
            question = Question.objects.create(
                quiz=quiz,
                question_text=q_text,
                question_type=q_type,
                points=points,
            )
            total_points += points
            choices = item.get("choices") or []
            if q_type in ["multiple_choice", "true_false"]:
                if not choices and q_type == "true_false":
                    choices = [
                        {"text": "True", "is_correct": bool(item.get("correct"))},
                        {"text": "False", "is_correct": not bool(item.get("correct"))},
                    ]
                for choice in choices:
                    Choice.objects.create(
                        question=question,
                        choice_text=str(choice.get("text") or ""),
                        is_correct=bool(choice.get("is_correct")),
                    )

        quiz.total_points = total_points
        quiz.save(update_fields=['total_points'])
        serializer = QuizSerializer(quiz, context={"request": request})
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['get'], permission_classes=[IsStudentOrTeacherOrAdmin])
    def attempts(self, request, pk=None):
        quiz = self.get_object()
        attempts = QuizAttempt.objects.filter(quiz=quiz)
        if request.user.role == 'student':
            attempts = attempts.filter(student__user=request.user)
        serializer = QuizAttemptSerializer(attempts, many=True)
        return Response(serializer.data)


class QuestionViewSet(viewsets.ModelViewSet):
    queryset = Question.objects.prefetch_related('choices')
    serializer_class = QuestionSerializer
    permission_classes = [IsTeacherOrAdmin]

    def perform_create(self, serializer):
        quiz_id = self.request.data.get('quiz')
        if not quiz_id:
            raise serializers.ValidationError({'quiz': 'This field is required.'})
        quiz = Quiz.objects.filter(id=quiz_id).first()
        if not quiz:
            raise serializers.ValidationError({'quiz': 'Quiz not found.'})
        serializer.save(quiz=quiz)
        quiz.total_points = sum(q.points or 0.0 for q in quiz.questions.all())
        quiz.save(update_fields=['total_points'])

    def perform_update(self, serializer):
        instance = serializer.save()
        quiz = instance.quiz
        quiz.total_points = sum(q.points or 0.0 for q in quiz.questions.all())
        quiz.save(update_fields=['total_points'])

    def perform_destroy(self, instance):
        quiz = instance.quiz
        instance.delete()
        quiz.total_points = sum(q.points or 0.0 for q in quiz.questions.all())
        quiz.save(update_fields=['total_points'])


class ChoiceViewSet(viewsets.ModelViewSet):
    queryset = Choice.objects.all()
    serializer_class = ChoiceSerializer
    permission_classes = [IsTeacherOrAdmin]

    def perform_create(self, serializer):
        question_id = self.request.data.get('question')
        if not question_id:
            raise serializers.ValidationError({'question': 'This field is required.'})
        question = Question.objects.filter(id=question_id).first()
        if not question:
            raise serializers.ValidationError({'question': 'Question not found.'})
        serializer.save(question=question)


class QuizAttemptViewSet(viewsets.ModelViewSet):
    queryset = QuizAttempt.objects.select_related('quiz', 'student')
    serializer_class = QuizAttemptSerializer

    def get_permissions(self):
        if self.action == 'create':
            permission_classes = [IsStudentOrTeacherOrAdmin]
        else:
            permission_classes = [IsOwnerOrTeacherOrAdmin]
        return [permission() for permission in permission_classes]

    def get_queryset(self):
        user = self.request.user
        if user.role == 'student':
            return QuizAttempt.objects.filter(student__user=user)
        if user.role in ['instructor', 'adviser']:
            return QuizAttempt.objects.filter(quiz__section_subject__instructor__user=user) | QuizAttempt.objects.filter(quiz__section_subject__adviser__user=user)
        return super().get_queryset()

    def create(self, request, *args, **kwargs):
        if request.user.role != 'student':
            return Response({'error': 'Only students can submit quizzes'}, status=status.HTTP_403_FORBIDDEN)
        quiz_id = request.data.get('quiz')
        if not quiz_id:
            return Response({'error': 'quiz is required'}, status=status.HTTP_400_BAD_REQUEST)
        quiz = Quiz.objects.filter(id=quiz_id).first()
        if not quiz:
            return Response({'error': 'Quiz not found'}, status=status.HTTP_404_NOT_FOUND)
        if not quiz.is_available:
            return Response({'error': 'Quiz is not yet available.'}, status=status.HTTP_403_FORBIDDEN)
        student = _get_student_from_user(request.user)
        if not student:
            return Response({'error': 'Student profile not found'}, status=status.HTTP_400_BAD_REQUEST)

        attempts = QuizAttempt.objects.filter(quiz=quiz, student=student).count()
        if attempts >= quiz.attempt_limit:
            return Response({'error': 'Attempt limit reached'}, status=status.HTTP_400_BAD_REQUEST)

        latest_session = QuizProctorSession.objects.filter(quiz=quiz, student=student).order_by('-started_at').first()
        if latest_session and latest_session.status == 'blocked':
            return Response({'error': 'Exam blocked due to violations.'}, status=status.HTTP_403_FORBIDDEN)

        attempt = QuizAttempt.objects.create(quiz=quiz, student=student, score=0.0, raw_score=0.0)
        active_session = QuizProctorSession.objects.filter(quiz=quiz, student=student, status='active').order_by('-started_at').first()
        if active_session and active_session.attempt_id is None:
            active_session.attempt = attempt
            active_session.save(update_fields=['attempt'])
        serializer = self.get_serializer(attempt)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'], permission_classes=[IsOwnerOrTeacherOrAdmin])
    def ai_grade(self, request, pk=None):
        attempt = self.get_object()
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
                    try:
                        score, _feedback = grade_quiz_answer_with_gemini(
                            question_text=question.question_text,
                            student_answer=answer.text_answer,
                            points=points,
                        )
                        answer.points_earned = score
                        answer.is_correct = score >= points * 0.7
                        answer.feedback = _feedback
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
                else:
                    answer.points_earned = 0.0
                    answer.is_correct = False
            else:
                answer.points_earned = 0.0
                answer.is_correct = False

            total += float(answer.points_earned or 0.0)
            answer.save(update_fields=['points_earned', 'is_correct', 'feedback'])

        attempt.score = total
        penalty = _latest_penalty_for(attempt.student, attempt.quiz)
        attempt.raw_score = total
        attempt.penalty_percent = penalty
        attempt.score = _apply_penalty(total, penalty)
        attempt.ai_grade_applied = True
        attempt.ai_grade_failed = False
        if not attempt.submitted_at:
            attempt.submitted_at = timezone.now()
        attempt.save(update_fields=['score', 'raw_score', 'penalty_percent', 'submitted_at', 'ai_grade_applied', 'ai_grade_failed'])
        serializer = self.get_serializer(attempt)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['get'], permission_classes=[IsOwnerOrTeacherOrAdmin], url_path='proctor-logs')
    def proctor_logs(self, request, pk=None):
        attempt = self.get_object()
        sessions = QuizProctorSession.objects.filter(quiz=attempt.quiz, student=attempt.student)
        linked = sessions.filter(attempt=attempt)
        if linked.exists():
            sessions = linked
        sessions = sessions.select_related('student__user').prefetch_related('events', 'snapshots')

        payload = []
        for session in sessions:
            payload.append({
                'id': str(session.id),
                'student_id': str(session.student_id),
                'student_name': session.student.user.get_full_name(),
                'attempt_id': str(session.attempt_id) if session.attempt_id else None,
                'status': session.status,
                'warnings': session.warnings_count,
                'terminations': session.terminations_count,
                'penalty_percent': session.penalty_percent,
                'started_at': session.started_at.isoformat(),
                'ended_at': session.ended_at.isoformat() if session.ended_at else None,
                'events': [
                    {
                        'id': str(event.id),
                        'type': event.event_type,
                        'detail': event.detail,
                        'created_at': event.created_at.isoformat(),
                    }
                    for event in session.events.all()
                ],
                'snapshots': [
                    {
                        'id': str(snapshot.id),
                        'image_url': snapshot.image_url,
                        'reason': snapshot.reason,
                        'created_at': snapshot.created_at.isoformat(),
                    }
                    for snapshot in session.snapshots.all()
                ],
            })
        return Response(payload)

    @action(detail=True, methods=['patch'], permission_classes=[IsOwnerOrTeacherOrAdmin], url_path='grade-answers')
    def grade_answers(self, request, pk=None):
        attempt = self.get_object()
        if request.user.role == 'student':
            return Response({'error': 'Only teachers can grade answers'}, status=status.HTTP_403_FORBIDDEN)

        payload = request.data.get('answers', [])
        if not isinstance(payload, list):
            return Response({'error': 'answers must be a list'}, status=status.HTTP_400_BAD_REQUEST)

        answers_by_id = {str(answer.id): answer for answer in attempt.answers.select_related('question')}
        updated = 0
        for entry in payload:
            answer_id = str(entry.get('answer_id') or '')
            if not answer_id or answer_id not in answers_by_id:
                continue
            answer = answers_by_id[answer_id]
            question = answer.question
            if question.question_type not in ['essay', 'identification']:
                continue
            try:
                points = float(entry.get('points_earned'))
            except (TypeError, ValueError):
                points = None
            if points < 0:
                points = 0.0
            max_points = float(question.points or 0.0)
            if points > max_points:
                points = max_points
            if points is not None:
                answer.points_earned = points
                answer.is_correct = points >= max_points * 0.7 if max_points > 0 else False
            if 'feedback' in entry:
                answer.feedback = entry.get('feedback')
            answer.save(update_fields=['points_earned', 'is_correct', 'feedback'])
            updated += 1

        if updated:
            total = 0.0
            for answer in answers_by_id.values():
                total += float(answer.points_earned or 0.0)
            penalty = _latest_penalty_for(attempt.student, attempt.quiz)
            attempt.raw_score = total
            attempt.penalty_percent = penalty
            attempt.score = _apply_penalty(total, penalty)
            if not attempt.submitted_at:
                attempt.submitted_at = timezone.now()
            attempt.save(update_fields=['raw_score', 'penalty_percent', 'score', 'submitted_at'])

        serializer = self.get_serializer(attempt)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'], permission_classes=[IsOwnerOrTeacherOrAdmin], url_path='ai-grade-answer')
    def ai_grade_answer(self, request, pk=None):
        attempt = self.get_object()
        if request.user.role == 'student':
            return Response({'error': 'Only teachers can grade answers'}, status=status.HTTP_403_FORBIDDEN)

        answer_id = request.data.get('answer_id')
        if not answer_id:
            return Response({'error': 'answer_id is required'}, status=status.HTTP_400_BAD_REQUEST)

        answer = attempt.answers.select_related('question').filter(id=answer_id).first()
        if not answer:
            return Response({'error': 'Answer not found'}, status=status.HTTP_404_NOT_FOUND)
        question = answer.question
        if question.question_type not in ['essay', 'identification']:
            return Response({'error': 'AI grading only supports essay and identification'}, status=status.HTTP_400_BAD_REQUEST)
        if not answer.text_answer:
            return Response({'error': 'No answer text to grade'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            score, _feedback = grade_quiz_answer_with_gemini(
                question_text=question.question_text,
                student_answer=answer.text_answer,
                points=question.points or 0.0,
            )
            answer.points_earned = score
            answer.is_correct = score >= (question.points or 0.0) * 0.7 if question.points else False
            answer.feedback = _feedback
            answer.save(update_fields=['points_earned', 'is_correct', 'feedback'])
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

        total = 0.0
        for item in attempt.answers.all():
            total += float(item.points_earned or 0.0)
        penalty = _latest_penalty_for(attempt.student, attempt.quiz)
        attempt.raw_score = total
        attempt.penalty_percent = penalty
        attempt.score = _apply_penalty(total, penalty)
        attempt.ai_grade_applied = True
        attempt.ai_grade_failed = False
        if not attempt.submitted_at:
            attempt.submitted_at = timezone.now()
        attempt.save(update_fields=['raw_score', 'penalty_percent', 'score', 'submitted_at', 'ai_grade_applied', 'ai_grade_failed'])

        serializer = self.get_serializer(attempt)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'], permission_classes=[IsOwnerOrTeacherOrAdmin], url_path='ai-preview-answer')
    def ai_preview_answer(self, request, pk=None):
        attempt = self.get_object()
        if request.user.role == 'student':
            return Response({'error': 'Only teachers can grade answers'}, status=status.HTTP_403_FORBIDDEN)

        answer_id = request.data.get('answer_id')
        if not answer_id:
            return Response({'error': 'answer_id is required'}, status=status.HTTP_400_BAD_REQUEST)

        answer = attempt.answers.select_related('question').filter(id=answer_id).first()
        if not answer:
            return Response({'error': 'Answer not found'}, status=status.HTTP_404_NOT_FOUND)
        question = answer.question
        if question.question_type not in ['essay', 'identification']:
            return Response({'error': 'AI preview only supports essay and identification'}, status=status.HTTP_400_BAD_REQUEST)
        if not answer.text_answer:
            return Response({'error': 'No answer text to grade'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            score, feedback = grade_quiz_answer_with_gemini(
                question_text=question.question_text,
                student_answer=answer.text_answer,
                points=question.points or 0.0,
            )
            return Response({'score': score, 'feedback': feedback}, status=status.HTTP_200_OK)
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

    @action(detail=True, methods=['post'], permission_classes=[IsOwnerOrTeacherOrAdmin], url_path='ai-grade-essay')
    def ai_grade_essay(self, request, pk=None):
        attempt = self.get_object()
        if request.user.role == 'student':
            return Response({'error': 'Only teachers can grade answers'}, status=status.HTTP_403_FORBIDDEN)

        total = 0.0
        for answer in attempt.answers.select_related('question'):
            question = answer.question
            if question.question_type in ['multiple_choice', 'true_false']:
                total += float(answer.points_earned or 0.0)
                continue
            if question.question_type in ['essay', 'identification'] and answer.text_answer:
                try:
                    score, _feedback = grade_quiz_answer_with_gemini(
                        question_text=question.question_text,
                        student_answer=answer.text_answer,
                        points=question.points or 0.0,
                    )
                    answer.points_earned = score
                    answer.is_correct = score >= (question.points or 0.0) * 0.7 if question.points else False
                    answer.feedback = _feedback
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
                answer.save(update_fields=['points_earned', 'is_correct', 'feedback'])
            total += float(answer.points_earned or 0.0)

        penalty = _latest_penalty_for(attempt.student, attempt.quiz)
        attempt.raw_score = total
        attempt.penalty_percent = penalty
        attempt.score = _apply_penalty(total, penalty)
        attempt.ai_grade_applied = True
        attempt.ai_grade_failed = False
        if not attempt.submitted_at:
            attempt.submitted_at = timezone.now()
        attempt.save(update_fields=['raw_score', 'penalty_percent', 'score', 'submitted_at', 'ai_grade_applied', 'ai_grade_failed'])

        serializer = self.get_serializer(attempt)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['patch'], permission_classes=[IsOwnerOrTeacherOrAdmin])
    def submit(self, request, pk=None):
        attempt = self.get_object()
        logger = logging.getLogger(__name__)
        if request.user.role != 'student':
            return Response({'error': 'Only students can submit quizzes'}, status=status.HTTP_403_FORBIDDEN)
        if attempt.submitted_at:
            return Response({'error': 'Quiz already submitted'}, status=status.HTTP_400_BAD_REQUEST)
        answers_payload = request.data.get('answers', [])
        ai_grade_flag = request.data.get('ai_grade')
        ai_grade = attempt.quiz.ai_grade_on_submit if ai_grade_flag is None else bool(ai_grade_flag)
        ai_grade_failed = False
        ai_grade_applied = False
        if not isinstance(answers_payload, list):
            return Response({'error': 'answers must be a list'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            logger.info(
                "Quiz submit payload: attempt=%s quiz=%s student=%s answers_count=%s sample=%s",
                attempt.id,
                attempt.quiz_id,
                attempt.student_id,
                len(answers_payload),
                answers_payload[:3],
            )
        except Exception:
            pass

        total = 0.0
        for answer_data in answers_payload:
            question_id = answer_data.get('question_id')
            selected_choice_id = answer_data.get('selected_choice_id')
            text_answer = answer_data.get('text_answer')
            if not question_id:
                continue
            question = Question.objects.filter(id=question_id, quiz=attempt.quiz).first()
            if not question:
                continue
            answer, _created = QuizAnswer.objects.get_or_create(attempt=attempt, question=question)
            if question.question_type in ['multiple_choice', 'true_false']:
                choice = Choice.objects.filter(id=selected_choice_id, question=question).first()
                answer.selected_choice = choice
                answer.text_answer = None
                is_correct = bool(choice and choice.is_correct)
                answer.is_correct = is_correct
                answer.points_earned = question.points if is_correct else 0.0
            else:
                answer.selected_choice = None
                answer.text_answer = text_answer
                if ai_grade and answer.text_answer:
                    ai_grade_applied = True
                    try:
                        score, _feedback = grade_quiz_answer_with_gemini(
                            question_text=question.question_text,
                            student_answer=answer.text_answer,
                            points=question.points or 0.0,
                        )
                        answer.points_earned = score
                        answer.is_correct = score >= (question.points or 0.0) * 0.7
                        answer.feedback = _feedback
                    except RateLimitError:
                        ai_grade_failed = True
                        answer.is_correct = False
                        answer.points_earned = 0.0
                        answer.feedback = None
                    except Exception:
                        ai_grade_failed = True
                        answer.is_correct = False
                        answer.points_earned = 0.0
                        answer.feedback = None
                else:
                    answer.is_correct = False
                    answer.points_earned = 0.0
            answer.save(update_fields=['selected_choice', 'text_answer', 'is_correct', 'points_earned', 'feedback'])
            total += float(answer.points_earned or 0.0)

        penalty = _latest_penalty_for(attempt.student, attempt.quiz)
        attempt.raw_score = total
        attempt.penalty_percent = penalty
        attempt.score = _apply_penalty(total, penalty)
        attempt.ai_grade_applied = ai_grade_applied
        attempt.ai_grade_failed = ai_grade_failed
        attempt.submitted_at = timezone.now()
        attempt.save(update_fields=['raw_score', 'penalty_percent', 'score', 'submitted_at', 'ai_grade_applied', 'ai_grade_failed'])
        serializer = self.get_serializer(attempt)
        return Response(
            {
                **serializer.data,
                'ai_grade_applied': ai_grade_applied,
                'ai_grade_failed': ai_grade_failed,
            }
        )

    def update(self, request, *args, **kwargs):
        response = super().update(request, *args, **kwargs)
        attempt_id = kwargs.get('pk')
        if attempt_id and ('score' in request.data or 'feedback' in request.data):
            attempt = QuizAttempt.objects.filter(id=attempt_id).first()
            if attempt:
                updated_fields = []
                if 'score' in request.data:
                    penalty = attempt.penalty_percent or 0
                    raw_score = float(request.data.get('score') or 0.0)
                    attempt.raw_score = raw_score
                    attempt.score = _apply_penalty(raw_score, penalty)
                    updated_fields.extend(['raw_score', 'score'])
                if 'feedback' in request.data:
                    attempt.feedback = request.data.get('feedback')
                    updated_fields.append('feedback')
                if updated_fields:
                    attempt.save(update_fields=updated_fields)
                    response.data = self.get_serializer(attempt).data
        return response


class QuizProctorViewSet(viewsets.ViewSet):
    permission_classes = [IsStudentOrTeacherOrAdmin]

    def _get_session(self, request):
        session_id = request.data.get('session_id') or request.query_params.get('session_id')
        if not session_id and request.body:
            try:
                import json
                payload = json.loads(request.body.decode('utf-8'))
                session_id = payload.get('session_id')
            except Exception:
                session_id = None
        if not session_id:
            return None
        return QuizProctorSession.objects.filter(id=session_id).select_related('quiz', 'student__user').first()

    def _ensure_owner(self, request, session):
        student = _get_student_from_user(request.user)
        if not student:
            return False
        return session.student_id == student.id

    @action(detail=False, methods=['post'], url_path='heartbeat')
    def heartbeat(self, request):
        session = self._get_session(request)
        if not session:
            return Response({'error': 'Session not found.'}, status=status.HTTP_404_NOT_FOUND)
        if not self._ensure_owner(request, session):
            return Response({'error': 'Forbidden.'}, status=status.HTTP_403_FORBIDDEN)
        if session.status != 'active':
            return Response({'status': session.status}, status=status.HTTP_200_OK)
        device_id = request.data.get('device_id') or request.headers.get('X-Device-Id')
        if session.device_id and device_id and session.device_id != device_id:
            return Response({'error': 'Active session on another device.', 'code': 'active_session'}, status=status.HTTP_409_CONFLICT)
        session.last_heartbeat = timezone.now()
        session.save(update_fields=['last_heartbeat'])
        return Response({
            'status': session.status,
            'warnings': session.warnings_count,
            'terminations': session.terminations_count,
            'penalty_percent': session.penalty_percent,
        })

    @action(detail=False, methods=['post'], url_path='violation')
    def violation(self, request):
        session = self._get_session(request)
        if not session:
            return Response({'error': 'Session not found.'}, status=status.HTTP_404_NOT_FOUND)
        if not self._ensure_owner(request, session):
            return Response({'error': 'Forbidden.'}, status=status.HTTP_403_FORBIDDEN)
        if session.status not in ['active', 'terminated']:
            return Response({'status': session.status}, status=status.HTTP_200_OK)

        reason = request.data.get('reason') or 'violation'
        detail = request.data.get('detail')
        image_data = request.data.get('image_data')
        answers_payload = request.data.get('answers') or []
        ai_grade_flag = request.data.get('ai_grade')
        if image_data:
            image_url = _upload_proctor_snapshot(image_data, reason)
            if image_url:
                QuizProctorSnapshot.objects.create(session=session, image_url=image_url, reason=reason)

        session.warnings_count += 1
        session.last_violation_at = timezone.now()
        QuizProctorEvent.objects.create(session=session, event_type='violation', detail=reason)

        terminated = False
        blocked = False
        if session.warnings_count % 5 == 0:
            session.terminations_count += 1
            terminated = True
            if session.terminations_count == 1:
                session.penalty_percent = 10
                session.status = 'terminated'
            elif session.terminations_count == 2:
                session.penalty_percent = 30
                session.status = 'terminated'
            else:
                session.penalty_percent = 100
                session.status = 'blocked'
                blocked = True
            session.ended_at = timezone.now()

        session.save(update_fields=['warnings_count', 'last_violation_at', 'terminations_count', 'penalty_percent', 'status', 'ended_at'])

        # Server-side fallback auto-submit to ensure teacher sees a submitted attempt.
        attempt = session.attempt
        if not attempt:
            attempt = QuizAttempt.objects.create(quiz=session.quiz, student=session.student, score=0.0, raw_score=0.0)
            session.attempt = attempt
            session.save(update_fields=['attempt'])
        if attempt and not attempt.submitted_at:
            # If answers are provided, grade and store them before submitting.
            if isinstance(answers_payload, list) and answers_payload:
                ai_grade = attempt.quiz.ai_grade_on_submit if ai_grade_flag is None else bool(ai_grade_flag)
                ai_grade_applied = False
                ai_grade_failed = False
                total = 0.0
                for answer_data in answers_payload:
                    question_id = answer_data.get('question_id')
                    selected_choice_id = answer_data.get('selected_choice_id')
                    text_answer = answer_data.get('text_answer')
                    if not question_id:
                        continue
                    question = Question.objects.filter(id=question_id, quiz=attempt.quiz).first()
                    if not question:
                        continue
                    answer, _created = QuizAnswer.objects.get_or_create(attempt=attempt, question=question)
                    if question.question_type in ['multiple_choice', 'true_false']:
                        choice = Choice.objects.filter(id=selected_choice_id, question=question).first()
                        answer.selected_choice = choice
                        answer.text_answer = None
                        is_correct = bool(choice and choice.is_correct)
                        answer.is_correct = is_correct
                        answer.points_earned = question.points if is_correct else 0.0
                    else:
                        answer.selected_choice = None
                        answer.text_answer = text_answer
                        if ai_grade and answer.text_answer:
                            ai_grade_applied = True
                            try:
                                score, _feedback = grade_quiz_answer_with_gemini(
                                    question_text=question.question_text,
                                    student_answer=answer.text_answer,
                                    points=question.points or 0.0,
                                )
                                answer.points_earned = score
                                answer.is_correct = score >= (question.points or 0.0) * 0.7
                                answer.feedback = _feedback
                            except Exception:
                                ai_grade_failed = True
                                answer.points_earned = 0.0
                                answer.is_correct = False
                        else:
                            answer.points_earned = 0.0
                            answer.is_correct = False
                    answer.save(update_fields=['selected_choice', 'text_answer', 'is_correct', 'points_earned', 'feedback'])
                    total += float(answer.points_earned or 0.0)
                attempt.raw_score = total
                attempt.ai_grade_applied = ai_grade_applied
                attempt.ai_grade_failed = ai_grade_failed
            else:
                attempt.raw_score = 0.0
            penalty = _latest_penalty_for(attempt.student, attempt.quiz)
            attempt.penalty_percent = penalty
            attempt.score = _apply_penalty(float(attempt.raw_score or 0.0), penalty)
            attempt.submitted_at = timezone.now()
            attempt.save(update_fields=['raw_score', 'penalty_percent', 'score', 'submitted_at', 'ai_grade_applied', 'ai_grade_failed'])

        return Response({
            'warnings': session.warnings_count,
            'terminations': session.terminations_count,
            'penalty_percent': session.penalty_percent,
            'status': session.status,
            'terminated': terminated,
            'blocked': blocked,
        })

    @action(detail=False, methods=['post'], url_path='snapshot')
    def snapshot(self, request):
        session = self._get_session(request)
        if not session:
            return Response({'error': 'Session not found.'}, status=status.HTTP_404_NOT_FOUND)
        if not self._ensure_owner(request, session):
            return Response({'error': 'Forbidden.'}, status=status.HTTP_403_FORBIDDEN)
        reason = request.data.get('reason') or 'snapshot'
        image_data = request.data.get('image_data')
        image_url = _upload_proctor_snapshot(image_data, reason)
        if not image_url:
            return Response({'error': 'Unable to upload snapshot.'}, status=status.HTTP_400_BAD_REQUEST)
        snapshot = QuizProctorSnapshot.objects.create(session=session, image_url=image_url, reason=reason)
        QuizProctorEvent.objects.create(session=session, event_type='snapshot', detail=reason)
        return Response({'id': str(snapshot.id), 'image_url': snapshot.image_url})

    @action(detail=False, methods=['post'], url_path='event')
    def event(self, request):
        session = self._get_session(request)
        if not session:
            return Response({'error': 'Session not found.'}, status=status.HTTP_404_NOT_FOUND)
        if not self._ensure_owner(request, session):
            return Response({'error': 'Forbidden.'}, status=status.HTTP_403_FORBIDDEN)
        event_type = request.data.get('event_type') or 'event'
        detail = request.data.get('detail')
        QuizProctorEvent.objects.create(session=session, event_type=event_type, detail=detail)
        return Response({'status': 'ok'})


class QuizFilterPreferenceViewSet(viewsets.ModelViewSet):
    serializer_class = QuizFilterPreferenceSerializer
    permission_classes = [IsStudentOrTeacherOrAdmin]

    def get_queryset(self):
        user = self.request.user
        qs = QuizFilterPreference.objects.filter(user=user)
        quiz_id = self.request.query_params.get('quiz')
        if quiz_id:
            qs = qs.filter(quiz_id=quiz_id)
        return qs

    def list(self, request, *args, **kwargs):
        if request.user.role == 'student':
            return Response([], status=status.HTTP_200_OK)
        return super().list(request, *args, **kwargs)

    def create(self, request, *args, **kwargs):
        if request.user.role == 'student':
            return Response({'error': 'Only teachers can update filters'}, status=status.HTTP_403_FORBIDDEN)
        quiz_id = request.data.get('quiz')
        if not quiz_id:
            return Response({'error': 'quiz is required'}, status=status.HTTP_400_BAD_REQUEST)
        preference, _created = QuizFilterPreference.objects.get_or_create(user=request.user, quiz_id=quiz_id)
        serializer = self.get_serializer(preference, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data, status=status.HTTP_200_OK)

    @action(detail=False, methods=['post'], url_path='end')
    def end(self, request):
        session = self._get_session(request)
        if not session:
            return Response({'error': 'Session not found.'}, status=status.HTTP_404_NOT_FOUND)
        if not self._ensure_owner(request, session):
            return Response({'error': 'Forbidden.'}, status=status.HTTP_403_FORBIDDEN)
        if session.status == 'active':
            session.status = 'ended'
            session.ended_at = timezone.now()
            session.save(update_fields=['status', 'ended_at'])
            QuizProctorEvent.objects.create(session=session, event_type='end', detail=request.data.get('reason'))
        return Response({'status': session.status})

    @action(detail=False, methods=['get'], permission_classes=[IsStudentOrTeacherOrAdmin], url_path='logs')
    def logs(self, request):
        quiz_id = request.query_params.get('quiz_id')
        attempt_id = request.query_params.get('attempt_id')
        student_id = request.query_params.get('student_id')
        if not quiz_id:
            return Response({'error': 'quiz_id is required'}, status=status.HTTP_400_BAD_REQUEST)
        quiz = Quiz.objects.filter(id=quiz_id).select_related('section_subject__instructor__user', 'section_subject__adviser__user').first()
        if not quiz:
            return Response({'error': 'Quiz not found'}, status=status.HTTP_404_NOT_FOUND)
        user = request.user
        if user.role in ['instructor', 'adviser']:
            is_owner = (
                (quiz.section_subject.instructor_id and quiz.section_subject.instructor.user_id == user.id) or
                (quiz.section_subject.adviser_id and quiz.section_subject.adviser.user_id == user.id)
            )
            if not is_owner:
                return Response({'error': 'Forbidden'}, status=status.HTTP_403_FORBIDDEN)
        if user.role == 'student':
            student = _get_student_from_user(user)
            if not student:
                return Response({'error': 'Student profile not found.'}, status=status.HTTP_400_BAD_REQUEST)
            student_id = str(student.id)

        sessions = QuizProctorSession.objects.filter(quiz=quiz)
        if student_id:
            sessions = sessions.filter(student_id=student_id)
        if attempt_id:
            sessions = sessions.filter(attempt_id=attempt_id)
        sessions = sessions.select_related('student__user').prefetch_related('events', 'snapshots')

        payload = []
        for session in sessions:
            payload.append({
                'id': str(session.id),
                'student_id': str(session.student_id),
                'student_name': session.student.user.get_full_name(),
                'attempt_id': str(session.attempt_id) if session.attempt_id else None,
                'status': session.status,
                'warnings': session.warnings_count,
                'terminations': session.terminations_count,
                'penalty_percent': session.penalty_percent,
                'started_at': session.started_at.isoformat(),
                'ended_at': session.ended_at.isoformat() if session.ended_at else None,
                'events': [
                    {
                        'id': str(event.id),
                        'type': event.event_type,
                        'detail': event.detail,
                        'created_at': event.created_at.isoformat(),
                    }
                    for event in session.events.all()
                ],
                'snapshots': [
                    {
                        'id': str(snapshot.id),
                        'image_url': snapshot.image_url,
                        'reason': snapshot.reason,
                        'created_at': snapshot.created_at.isoformat(),
                    }
                    for snapshot in session.snapshots.all()
                ],
            })
        return Response(payload)

    @action(detail=False, methods=['get'], permission_classes=[IsTeacherOrAdmin], url_path='summary')
    def summary(self, request):
        user = request.user
        quizzes_qs = Quiz.objects.all().select_related('section_subject__instructor__user', 'section_subject__adviser__user')
        if user.role in ['instructor', 'adviser']:
            quizzes_qs = quizzes_qs.filter(
                Q(section_subject__instructor__user=user) | Q(section_subject__adviser__user=user)
            )
        summaries = []
        for quiz in quizzes_qs:
            sessions = QuizProctorSession.objects.filter(quiz=quiz)
            total_sessions = sessions.count()
            total_warnings = sessions.aggregate(total=models.Sum('warnings_count')).get('total') or 0
            total_terminations = sessions.aggregate(total=models.Sum('terminations_count')).get('total') or 0
            total_snapshots = QuizProctorSnapshot.objects.filter(session__quiz=quiz).count()
            summaries.append({
                'quiz_id': str(quiz.id),
                'quiz_title': quiz.title,
                'total_sessions': total_sessions,
                'total_warnings': total_warnings,
                'total_terminations': total_terminations,
                'total_snapshots': total_snapshots,
            })
        return Response(summaries)
