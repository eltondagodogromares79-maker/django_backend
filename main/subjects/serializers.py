from rest_framework import serializers
from .models import Subject, SectionSubject, Grade
from shared.serializers import SanitizedModelSerializer


class SubjectSerializer(SanitizedModelSerializer):
    sanitize_fields = ('name', 'code', 'description')
    program_name = serializers.CharField(source='program.name', read_only=True)
    year_level_name = serializers.CharField(source='year_level.name', read_only=True)
    instructor_name = serializers.CharField(source='instructor.user.get_full_name', read_only=True)

    class Meta:
        model = Subject
        fields = [
            'id', 'name', 'code', 'program', 'program_name',
            'year_level', 'year_level_name', 'instructor', 'instructor_name',
            'units', 'description', 'created_at'
        ]
        read_only_fields = ['id', 'created_at']


class SectionSubjectSerializer(serializers.ModelSerializer):
    section_name = serializers.CharField(source='section.name', read_only=True)
    subject_name = serializers.CharField(source='subject.name', read_only=True)
    term_label = serializers.CharField(source='term.__str__', read_only=True)
    instructor_name = serializers.CharField(source='instructor.user.get_full_name', read_only=True)
    adviser_name = serializers.CharField(source='adviser.user.get_full_name', read_only=True)
    teacher_name = serializers.SerializerMethodField()

    class Meta:
        model = SectionSubject
        fields = [
            'id', 'section', 'section_name', 'subject', 'subject_name',
            'term', 'term_label', 'school_year', 'instructor', 'instructor_name',
            'adviser', 'adviser_name', 'teacher_name', 'schedule_days', 'schedule_time', 'created_at'
        ]
        read_only_fields = ['id', 'created_at']

    def get_teacher_name(self, obj):
        teacher = obj.teacher
        return teacher.user.get_full_name() if teacher else None


class GradeSerializer(serializers.ModelSerializer):
    student_name = serializers.CharField(source='student.user.get_full_name', read_only=True)
    subject_code = serializers.CharField(source='section_subject.subject.code', read_only=True)

    class Meta:
        model = Grade
        fields = [
            'id', 'student', 'student_name', 'section_subject', 'subject_code',
            'final_score', 'grade', 'remarks', 'school_year'
        ]
        read_only_fields = ['id', 'school_year']
