from rest_framework import serializers
from django.utils import timezone
from .models import Assignment, AssignmentSubmission
from shared.serializers import SanitizedModelSerializer


class AssignmentSerializer(SanitizedModelSerializer):
    sanitize_fields = ('title', 'description')
    subject_code = serializers.CharField(source='section_subject.subject.code', read_only=True)
    section_name = serializers.CharField(source='section_subject.section.name', read_only=True)
    subject_id = serializers.CharField(source='section_subject.subject.id', read_only=True)
    subject_name = serializers.CharField(source='section_subject.subject.name', read_only=True)
    section_id = serializers.CharField(source='section_subject.section.id', read_only=True)
    created_by_name = serializers.CharField(source='created_by.get_full_name', read_only=True)
    
    class Meta:
        model = Assignment
        fields = [
            'id', 'section_subject', 'section_id', 'section_name', 'subject_id', 'subject_name', 'subject_code',
            'title', 'description', 'total_points', 'due_date',
            'allow_late_submission', 'created_by', 'created_by_name', 'created_at'
        ]
        read_only_fields = ['id', 'created_at']

    def create(self, validated_data):
        request = self.context.get('request')
        if request and request.user and not validated_data.get('created_by'):
            validated_data['created_by'] = request.user
        return super().create(validated_data)

    def validate_due_date(self, value):
        if value and value < timezone.now():
            raise serializers.ValidationError('Due date cannot be in the past.')
        return value


class AssignmentSubmissionSerializer(SanitizedModelSerializer):
    sanitize_fields = ('text_answer', 'feedback')
    student_name = serializers.CharField(source='student.user.get_full_name', read_only=True)
    assignment_title = serializers.CharField(source='assignment.title', read_only=True)
    
    class Meta:
        model = AssignmentSubmission
        fields = [
            'id', 'assignment', 'assignment_title', 'student', 'student_name',
            'file_url', 'text_answer', 'score', 'feedback',
            'submitted_at', 'graded_at'
        ]
        read_only_fields = ['id', 'submitted_at', 'graded_at']

class AssignmentSubmissionGradeSerializer(serializers.ModelSerializer):
    class Meta:
        model = AssignmentSubmission
        fields = ['score', 'feedback']

    def update(self, instance, validated_data):
        if 'score' in validated_data:
            validated_data['graded_at'] = timezone.now()
        return super().update(instance, validated_data)
