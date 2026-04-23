from rest_framework import serializers
from django.utils import timezone
from .models import AttendanceSession, AttendanceRecord
from shared.serializers import SanitizedModelSerializer
from django.conf import settings


class AttendanceSessionSerializer(SanitizedModelSerializer):
    sanitize_fields = ('title',)
    section_name = serializers.CharField(source='section.name', read_only=True)
    subject_name = serializers.CharField(source='section_subject.subject.name', read_only=True)
    subject_code = serializers.CharField(source='section_subject.subject.code', read_only=True)
    section_subject_id = serializers.CharField(source='section_subject.id', read_only=True)
    created_by_name = serializers.CharField(source='created_by.get_full_name', read_only=True)
    my_status = serializers.SerializerMethodField()
    join_url = serializers.SerializerMethodField()
    present_count = serializers.IntegerField(read_only=True)
    absent_count = serializers.IntegerField(read_only=True)
    late_count = serializers.IntegerField(read_only=True)
    excused_count = serializers.IntegerField(read_only=True)
    total_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = AttendanceSession
        fields = [
            'id',
            'section',
            'section_name',
            'section_subject',
            'section_subject_id',
            'subject_name',
            'subject_code',
            'announcement',
            'title',
            'scheduled_at',
            'is_online_class',
            'is_live',
            'provider',
            'room_key',
            'join_url',
            'ended_at',
            'present_count',
            'absent_count',
            'late_count',
            'excused_count',
            'total_count',
            'created_by',
            'created_by_name',
            'created_at',
            'my_status',
        ]
        read_only_fields = ['id', 'created_at', 'created_by', 'created_by_name', 'section_subject_id']

    def validate_scheduled_at(self, value):
        if value and value < timezone.now():
            raise serializers.ValidationError('Scheduled time cannot be in the past.')
        return value

    def get_my_status(self, obj):
        request = self.context.get('request')
        user = getattr(request, 'user', None)
        if not user or not getattr(user, 'is_authenticated', False):
            return None
        if getattr(user, 'role', None) != 'student':
            return None
        student = getattr(user, 'student_profile', None)
        if not student:
            return None

        now = timezone.now()
        is_future_session = bool(obj.scheduled_at and obj.scheduled_at > now and not obj.is_live and not obj.ended_at)

        def normalize_status(status_value):
            if status_value == 'absent' and not obj.ended_at:
                if is_future_session:
                    return 'upcoming'
                return 'pending'
            return status_value

        cached_records = getattr(obj, 'student_records', None)
        if cached_records is not None:
            if not cached_records:
                return None
            return normalize_status(cached_records[0].status)
        record = AttendanceRecord.objects.filter(session=obj, student=student).first()
        return normalize_status(record.status) if record else ('upcoming' if is_future_session else None)

    def get_join_url(self, obj):
        if not obj.is_online_class:
            return obj.join_url or None
        if obj.join_url:
            return obj.join_url
        base = getattr(settings, 'JITSI_BASE_URL', 'https://meet.jit.si')
        if obj.room_key:
            return f"{base.rstrip('/')}/{obj.room_key}"
        return None


class AttendanceRecordSerializer(SanitizedModelSerializer):
    sanitize_fields = ('note',)
    student_name = serializers.CharField(source='student.user.get_full_name', read_only=True)
    student_number = serializers.CharField(source='student.student_number', read_only=True)

    class Meta:
        model = AttendanceRecord
        fields = [
            'id',
            'session',
            'student',
            'student_name',
            'student_number',
            'status',
            'note',
            'marked_by',
            'marked_at',
        ]
        read_only_fields = ['id', 'marked_by', 'marked_at']

    def update(self, instance, validated_data):
        validated_data['marked_at'] = timezone.now()
        return super().update(instance, validated_data)
