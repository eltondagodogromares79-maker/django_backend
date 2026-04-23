from rest_framework import viewsets, status, permissions
import uuid
from rest_framework.decorators import action
from rest_framework.response import Response
from django.db.models import Q, Prefetch, Count
from django.utils import timezone
from datetime import timedelta
from django.utils.text import slugify
from django.conf import settings
from .models import AttendanceSession, AttendanceRecord
from .serializers import AttendanceSessionSerializer, AttendanceRecordSerializer
from sections.models import Enrollment, Section, StudentSubject
from subjects.models import SectionSubject
from shared.permissions import IsTeacherOrAdmin


def _teacher_section_subjects(user):
    return SectionSubject.objects.filter(
        Q(instructor__user=user) | Q(adviser__user=user)
    ).select_related('section', 'subject')


def _teacher_sections(user):
    if user.role == 'adviser':
        return Section.objects.filter(adviser__user=user)
    if user.role == 'instructor':
        return Section.objects.filter(section_subjects__instructor__user=user).distinct()
    return Section.objects.none()


class AttendanceSessionViewSet(viewsets.ModelViewSet):
    queryset = AttendanceSession.objects.select_related('section', 'section_subject', 'created_by')
    serializer_class = AttendanceSessionSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_permissions(self):
        if self.action in ['list', 'retrieve', 'join']:
            return [permissions.IsAuthenticated()]
        return [IsTeacherOrAdmin()]

    def get_queryset(self):
        user = self.request.user
        qs = super().get_queryset()
        if user.role in ['admin', 'principal', 'dean']:
            return qs
        if user.role == 'student':
            student = getattr(user, 'student_profile', None)
            if not student:
                return qs.none()
            enrollments = Enrollment.objects.filter(
                student=student, is_current=True, status='enrolled'
            ).select_related('section')
            section_ids = enrollments.values_list('section_id', flat=True)
            section_subject_ids = StudentSubject.objects.filter(
                enrollment__in=enrollments
            ).values_list('section_subject_id', flat=True)
            student_records = AttendanceRecord.objects.filter(student=student)
            return (
                qs.filter(Q(section_id__in=section_ids) | Q(section_subject_id__in=section_subject_ids))
                .prefetch_related(Prefetch('records', queryset=student_records, to_attr='student_records'))
                .distinct()
            )
        section_subject_ids = _teacher_section_subjects(user).values_list('id', flat=True)
        section_ids = _teacher_sections(user).values_list('id', flat=True)
        return (
            qs.filter(Q(section_subject_id__in=section_subject_ids) | Q(section_id__in=section_ids))
            .annotate(
                present_count=Count('records', filter=Q(records__status='present')),
                absent_count=Count('records', filter=Q(records__status='absent')),
                late_count=Count('records', filter=Q(records__status='late')),
                excused_count=Count('records', filter=Q(records__status='excused')),
                total_count=Count('records'),
            )
        )

    def create(self, request, *args, **kwargs):
        payload = request.data.copy()
        section_subject_id = payload.get('section_subject') or payload.get('section_subject_id')
        section_id = payload.get('section')
        is_online = payload.get('is_online_class') or payload.get('online_class')

        section_subject = None
        if section_subject_id:
            section_subject = SectionSubject.objects.select_related('section').filter(id=section_subject_id).first()
            if not section_subject:
                return Response({'detail': 'Section subject not found.'}, status=status.HTTP_400_BAD_REQUEST)
            payload['section'] = str(section_subject.section_id)
            payload['section_subject'] = str(section_subject.id)
        elif not section_id:
            return Response({'detail': 'section or section_subject is required.'}, status=status.HTTP_400_BAD_REQUEST)

        if isinstance(is_online, str):
            is_online = is_online.lower() in ['true', '1', 'yes']
        payload['is_online_class'] = bool(is_online)

        if payload.get('is_online_class'):
            subject = getattr(section_subject, 'subject', None)
            subject_code = getattr(subject, 'code', None) or 'class'
            section_name = section_subject.section.name if section_subject and section_subject.section_id else 'section'
            slug = slugify(f"{subject_code}-{section_name}")[:24] or 'class'
            room_key = payload.get('room_key') or f"scsit-{slug}-{uuid.uuid4().hex[:6]}"
            payload['room_key'] = room_key
            base = getattr(settings, 'JITSI_BASE_URL', 'https://meet.jit.si')
            payload['join_url'] = payload.get('join_url') or f"{base.rstrip('/')}/{room_key}"
            payload['is_live'] = bool(payload.get('is_live', False))
        else:
            payload['is_live'] = False

        serializer = self.get_serializer(data=payload)
        serializer.is_valid(raise_exception=True)
        session = serializer.save(created_by=request.user)

        enrollments = Enrollment.objects.filter(section=session.section, is_current=True, status='enrolled').select_related('student')
        records = [
            AttendanceRecord(session=session, student=enrollment.student, status='absent')
            for enrollment in enrollments
        ]
        AttendanceRecord.objects.bulk_create(records)

        headers = self.get_success_headers(serializer.data)
        return Response(self.get_serializer(session).data, status=status.HTTP_201_CREATED, headers=headers)

    @action(detail=True, methods=['get'], permission_classes=[IsTeacherOrAdmin])
    def records(self, request, pk=None):
        session = self.get_object()
        records = AttendanceRecord.objects.filter(session=session).select_related('student__user')
        serializer = AttendanceRecordSerializer(records, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['post'], permission_classes=[IsTeacherOrAdmin], url_path='mark')
    def mark(self, request, pk=None):
        session = self.get_object()
        payload = request.data.get('records', [])
        if not isinstance(payload, list):
            return Response({'detail': 'records must be a list.'}, status=status.HTTP_400_BAD_REQUEST)

        updates = []
        for entry in payload:
            record_id = entry.get('id')
            status_value = entry.get('status')
            note = entry.get('note')
            if not record_id or not status_value:
                continue
            updates.append((record_id, status_value, note))

        records = AttendanceRecord.objects.filter(session=session, id__in=[r[0] for r in updates])
        record_map = {str(r.id): r for r in records}
        for record_id, status_value, note in updates:
            record = record_map.get(str(record_id))
            if not record:
                continue
            record.status = status_value
            if note is not None:
                record.note = note
            record.marked_by = request.user
            record.marked_at = timezone.now()
            record.save(update_fields=['status', 'note', 'marked_by', 'marked_at'])

        serializer = AttendanceRecordSerializer(records, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['post'], permission_classes=[permissions.IsAuthenticated], url_path='join')
    def join(self, request, pk=None):
        session = self.get_object()
        if request.user.role != 'student':
            join_url = AttendanceSessionSerializer(session, context={'request': request}).data.get('join_url')
            return Response({'join_url': join_url, 'status': 'viewer'})
        if session.is_online_class and not session.is_live:
            return Response({'detail': 'Class has not started yet.'}, status=status.HTTP_403_FORBIDDEN)
        if session.ended_at:
            return Response({'detail': 'Class already ended.'}, status=status.HTTP_400_BAD_REQUEST)
        student = getattr(request.user, 'student_profile', None)
        if not student:
            return Response({'detail': 'Student profile not found.'}, status=status.HTTP_400_BAD_REQUEST)
        record, _created = AttendanceRecord.objects.get_or_create(session=session, student=student)
        late_after = getattr(settings, 'ATTENDANCE_LATE_AFTER_MINUTES', 10)
        now = timezone.now()
        is_late = False
        if session.scheduled_at:
            try:
                is_late = now > session.scheduled_at + timedelta(minutes=late_after)
            except Exception:
                is_late = False
        record.status = 'late' if is_late else 'present'
        record.marked_at = timezone.now()
        record.marked_by = request.user
        record.save(update_fields=['status', 'marked_at', 'marked_by'])
        join_url = AttendanceSessionSerializer(session, context={'request': request}).data.get('join_url')
        return Response({'join_url': join_url, 'status': record.status})

    @action(detail=True, methods=['post'], permission_classes=[IsTeacherOrAdmin], url_path='start')
    def start(self, request, pk=None):
        session = self.get_object()
        if session.ended_at:
            return Response({'detail': 'Session already ended.'}, status=status.HTTP_400_BAD_REQUEST)
        if not session.is_online_class:
            return Response({'detail': 'Session is not an online class.'}, status=status.HTTP_400_BAD_REQUEST)
        if not session.is_live:
            session.is_live = True
            session.save(update_fields=['is_live'])
        join_url = AttendanceSessionSerializer(session, context={'request': request}).data.get('join_url')
        return Response({'join_url': join_url, 'is_live': session.is_live})

    @action(detail=True, methods=['post'], permission_classes=[IsTeacherOrAdmin], url_path='end')
    def end(self, request, pk=None):
        session = self.get_object()
        if session.ended_at:
            return Response({'detail': 'Session already ended.'}, status=status.HTTP_400_BAD_REQUEST)
        now = timezone.now()
        AttendanceRecord.objects.filter(session=session, status='absent').update(
            marked_at=now,
            marked_by=request.user,
        )
        session.ended_at = now
        session.is_live = False
        session.save(update_fields=['ended_at', 'is_live'])
        return Response({
            'ended_at': session.ended_at,
            'is_live': session.is_live,
        })

    @action(detail=False, methods=['get'], permission_classes=[IsTeacherOrAdmin], url_path='summary')
    def summary(self, request):
        qs = self.get_queryset()
        section_subject_id = request.query_params.get('section_subject')
        section_id = request.query_params.get('section')
        if section_subject_id:
            qs = qs.filter(section_subject_id=section_subject_id)
        if section_id:
            qs = qs.filter(section_id=section_id)

        records = AttendanceRecord.objects.filter(session__in=qs).values(
            'student_id',
            'student__student_number',
            'student__user__first_name',
            'student__user__last_name',
        ).annotate(
            present=Count('id', filter=Q(status='present')),
            absent=Count('id', filter=Q(status='absent')),
            late=Count('id', filter=Q(status='late')),
            excused=Count('id', filter=Q(status='excused')),
            total=Count('id'),
        ).order_by('student__user__last_name', 'student__user__first_name')

        data = []
        for item in records:
            present = item.get('present', 0)
            late = item.get('late', 0)
            excused = item.get('excused', 0)
            total = item.get('total', 0)
            attended = present + late + excused
            completion = round((attended / total) * 100, 1) if total else 0.0
            data.append({
                'student_id': str(item['student_id']),
                'student_name': f"{item.get('student__user__first_name', '').strip()} {item.get('student__user__last_name', '').strip()}".strip() or 'Student',
                'student_number': item.get('student__student_number'),
                'present': present,
                'absent': item.get('absent', 0),
                'late': late,
                'excused': excused,
                'total': total,
                'completion': completion,
            })

        return Response(data)
