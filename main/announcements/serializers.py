from rest_framework import serializers
from .models import Announcement
from shared.serializers import SanitizedModelSerializer


class AnnouncementSerializer(SanitizedModelSerializer):
    sanitize_fields = ('title', 'message')
    section_name = serializers.CharField(source='section_subject.section.name', read_only=True)
    subject_code = serializers.CharField(source='section_subject.subject.code', read_only=True)

    class Meta:
        model = Announcement
        fields = [
            'id', 'section_subject', 'section_name', 'subject_code',
            'title', 'message', 'created_at'
        ]
        read_only_fields = ['id', 'created_at']
