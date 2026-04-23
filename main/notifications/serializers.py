from rest_framework import serializers
from .models import Notification


class NotificationSerializer(serializers.ModelSerializer):
    section_subject_id = serializers.SerializerMethodField()

    class Meta:
        model = Notification
        fields = [
            'id',
            'kind',
            'title',
            'body',
            'target_id',
            'section_subject_id',
            'is_read',
            'read_at',
            'created_at',
        ]

    def get_section_subject_id(self, obj):
        return str(obj.section_subject_id) if obj.section_subject_id else None
