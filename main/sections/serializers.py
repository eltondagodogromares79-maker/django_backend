from rest_framework import serializers
from .models import Section, Enrollment, StudentSubject
from programs.models import Program
from year_levels.models import YearLevel
from subjects.models import Subject, SectionSubject
from shared.serializers import SanitizedModelSerializer


class SectionSerializer(SanitizedModelSerializer):
    sanitize_fields = ('name',)
    year_level_name = serializers.CharField(source='year_level.name', read_only=True)
    adviser_name = serializers.CharField(source='adviser.user.get_full_name', read_only=True)
    is_high_school = serializers.BooleanField(read_only=True)

    class Meta:
        model = Section
        fields = [
            'id', 'name', 'year_level', 'year_level_name', 'school_year',
            'adviser', 'adviser_name', 'capacity', 'is_high_school', 'created_at'
        ]
        read_only_fields = ['id', 'created_at']

    def validate(self, attrs):
        adviser = attrs.get('adviser') or (self.instance.adviser if self.instance else None)
        year_level = attrs.get('year_level') or (self.instance.year_level if self.instance else None)

        if not adviser:
            return attrs

        school_level = year_level.program.department.school_level if year_level and year_level.program_id else None
        if not school_level or not school_level.is_high_school:
            raise serializers.ValidationError({"adviser": "Only high school sections can have an adviser assigned."})

        if not adviser.program_id:
            raise serializers.ValidationError({"adviser": "Adviser must be assigned to a strand or grade."})

        if year_level and year_level.program_id != adviser.program_id:
            raise serializers.ValidationError({"adviser": "Adviser must match the section's strand/grade."})

        return attrs


class PublicSectionSerializer(serializers.ModelSerializer):
    adviser_name = serializers.CharField(source='adviser.user.get_full_name', read_only=True)
    school_year_name = serializers.CharField(source='school_year.name', read_only=True)

    class Meta:
        model = Section
        fields = ['id', 'name', 'adviser_name', 'school_year_name']
        read_only_fields = ['id', 'name', 'adviser_name', 'school_year_name']


class EnrollmentSerializer(serializers.ModelSerializer):
    section = serializers.PrimaryKeyRelatedField(
        queryset=Section.objects.all(),
        write_only=True,
        required=False
    )
    program = serializers.PrimaryKeyRelatedField(
        queryset=Program.objects.all(),
        write_only=True,
        required=False
    )
    year_level = serializers.PrimaryKeyRelatedField(
        queryset=YearLevel.objects.all(),
        required=False
    )
    student_name = serializers.CharField(source='student.user.get_full_name', read_only=True)
    student_number = serializers.CharField(source='student.student_number', read_only=True)
    student_profile_picture = serializers.SerializerMethodField()
    term_label = serializers.CharField(source='term.__str__', read_only=True)
    school_year = serializers.PrimaryKeyRelatedField(read_only=True)
    is_high_school = serializers.BooleanField(source='section.is_high_school', read_only=True)
    year_level_name = serializers.SerializerMethodField()
    program_id = serializers.SerializerMethodField()
    program_name = serializers.SerializerMethodField()
    program_type = serializers.SerializerMethodField()
    school_level = serializers.SerializerMethodField()

    class Meta:
        model = Enrollment
        fields = [
            'id', 'student', 'student_name', 'student_number', 'student_profile_picture', 'section', 'program', 'year_level',
            'year_level_name', 'program_id', 'program_name', 'program_type', 'school_level',
            'term', 'term_label', 'school_year', 'status', 'is_current', 'is_high_school', 'enrolled_at'
        ]
        read_only_fields = ['id', 'enrolled_at']

    def get_student_profile_picture(self, obj):
        request = self.context.get('request')
        picture = getattr(getattr(obj.student, 'user', None), 'profile_picture', None)
        if not picture:
            return None
        url = picture.url
        if request:
            return request.build_absolute_uri(url)
        return url

    def _get_year_level(self, obj):
        if obj.section_id:
            return obj.section.year_level
        return obj.year_level

    def get_year_level_name(self, obj):
        year_level = self._get_year_level(obj)
        return year_level.name if year_level else None

    def get_program_id(self, obj):
        year_level = self._get_year_level(obj)
        return year_level.program_id if year_level else None

    def get_program_name(self, obj):
        year_level = self._get_year_level(obj)
        return year_level.program.name if year_level and year_level.program_id else None

    def get_program_type(self, obj):
        year_level = self._get_year_level(obj)
        return year_level.program.type if year_level and year_level.program_id else None

    def get_school_level(self, obj):
        year_level = self._get_year_level(obj)
        if year_level and year_level.program_id:
            return year_level.program.department.school_level.name
        return None

    def validate(self, attrs):
        section = attrs.get('section')
        program = attrs.get('program')
        year_level = attrs.get('year_level')
        term = attrs.get('term')

        if not section:
            if not year_level:
                raise serializers.ValidationError("Provide year_level (grade) or section.")
            if program and year_level.program_id != program.id:
                raise serializers.ValidationError("Selected year level does not belong to the chosen program/strand/grade.")

            sections = Section.objects.filter(year_level=year_level)
            count = sections.count()
            if count == 1:
                attrs['section'] = sections.first()
            elif count == 0:
                # Allow enrollment even if no section exists yet
                attrs['section'] = None
            else:
                raise serializers.ValidationError(
                    "Multiple sections exist for the selected grade/year level. "
                    "Please choose a specific section or keep only one section per grade."
                )
        else:
            if not year_level:
                attrs['year_level'] = section.year_level
            elif section.year_level_id != year_level.id:
                raise serializers.ValidationError("Section does not belong to the selected year level.")

        if year_level and program and year_level.program_id != program.id:
            raise serializers.ValidationError("Selected year level does not belong to the chosen program/strand/grade.")

        if term:
            attrs['school_year'] = term.school_year

        return attrs


class StudentSubjectSerializer(serializers.ModelSerializer):
    subject_code = serializers.CharField(source='section_subject.subject.code', read_only=True)
    subject_name = serializers.CharField(source='section_subject.subject.name', read_only=True)
    teacher_name = serializers.SerializerMethodField()
    section_subject = serializers.PrimaryKeyRelatedField(
        queryset=SectionSubject.objects.all(),
        write_only=True
    )
    subject = serializers.PrimaryKeyRelatedField(
        queryset=Subject.objects.all(),
        write_only=True,
        required=False
    )

    class Meta:
        model = StudentSubject
        fields = ['id', 'enrollment', 'section_subject', 'subject', 'subject_code', 'subject_name', 'teacher_name', 'school_year']
        read_only_fields = ['id', 'school_year']

    def get_teacher_name(self, obj):
        teacher = obj.section_subject.teacher
        return teacher.user.get_full_name() if teacher else None

    def validate(self, attrs):
        enrollment = attrs['enrollment']
        section_subject = attrs.get('section_subject')
        subject = attrs.get('subject')
        # College only — high school subjects are auto-assigned
        if not enrollment.section_id:
            raise serializers.ValidationError("Enrollment has no section yet.")
        if enrollment.section.is_high_school:
            raise serializers.ValidationError("High school subjects are automatically assigned.")
        if subject and not section_subject:
            section_subject = SectionSubject.objects.filter(
                section=enrollment.section,
                term=enrollment.term,
                subject=subject
            ).first()
            if not section_subject:
                raise serializers.ValidationError(
                    "Selected subject is not offered for this section/term."
                )
            attrs['section_subject'] = section_subject

        if not section_subject:
            raise serializers.ValidationError("Provide subject or section_subject.")

        if section_subject.section_id != enrollment.section_id:
            raise serializers.ValidationError("Subject does not belong to the enrolled section.")
        return attrs


class TranscriptEnrollmentSerializer(serializers.ModelSerializer):
    term_label = serializers.CharField(source='term.__str__', read_only=True)
    school_year_name = serializers.CharField(source='school_year.name', read_only=True)
    year_level_name = serializers.SerializerMethodField()
    program_name = serializers.SerializerMethodField()
    section_name = serializers.CharField(source='section.name', read_only=True)
    student_subjects = StudentSubjectSerializer(many=True, read_only=True)

    class Meta:
        model = Enrollment
        fields = [
            'id', 'term_label', 'school_year_name', 'status', 'is_current',
            'year_level_name', 'program_name', 'section_name', 'enrolled_at', 'student_subjects'
        ]

    def get_year_level_name(self, obj):
        if obj.section_id:
            return obj.section.year_level.name
        if obj.year_level_id:
            return obj.year_level.name
        return None

    def get_program_name(self, obj):
        year_level = obj.section.year_level if obj.section_id else obj.year_level
        return year_level.program.name if year_level and year_level.program_id else None
