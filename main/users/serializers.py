from rest_framework import serializers
from .models import CustomUser, Student, Instructor, Adviser, Principal, Dean, AdminProfile
from sections.models import Section
from shared.serializers import SanitizedModelSerializer


class UserSerializer(SanitizedModelSerializer):
    sanitize_fields = ('first_name', 'last_name', 'middle_name', 'phone_number', 'address')
    password = serializers.CharField(write_only=True)

    class Meta:
        model = CustomUser
        fields = [
            'id', 'first_name', 'last_name', 'middle_name', 'email', 'role',
            'phone_number', 'address', 'date_of_birth', 'gender', 'profile_picture',
            'is_active', 'date_joined', 'must_change_password', 'password'
        ]
        read_only_fields = ['id', 'date_joined']
        extra_kwargs = {'password': {'write_only': True}}

    def create(self, validated_data):
        password = validated_data.pop('password')
        return CustomUser.objects.create_user(password=password, **validated_data)

    def validate(self, attrs):
        if not self.instance:
            gender = attrs.get('gender')
            if not gender or gender == CustomUser.Gender.UNSPECIFIED:
                raise serializers.ValidationError({"gender": "Gender is required."})
        return attrs

    def update(self, instance, validated_data):
        password = validated_data.pop('password', None)
        if password:
            instance.set_password(password)
        return super().update(instance, validated_data)


class UserProfileSerializer(SanitizedModelSerializer):
    sanitize_fields = ('first_name', 'last_name', 'middle_name', 'phone_number', 'address')
    emergency_contact_name = serializers.CharField(source='student_profile.emergency_contact_name', allow_blank=True, required=False)
    emergency_contact_phone = serializers.CharField(source='student_profile.emergency_contact_phone', allow_blank=True, required=False)
    emergency_contact_relationship = serializers.CharField(source='student_profile.emergency_contact_relationship', allow_blank=True, required=False)

    class Meta:
        model = CustomUser
        fields = [
            'id', 'first_name', 'last_name', 'middle_name', 'email', 'role',
            'phone_number', 'address', 'date_of_birth', 'gender', 'profile_picture', 'date_joined',
            'must_change_password',
            'emergency_contact_name', 'emergency_contact_phone', 'emergency_contact_relationship',
        ]
        read_only_fields = ['id', 'role', 'date_joined', 'must_change_password']

    def get_fields(self):
        fields = super().get_fields()
        request = self.context.get('request')
        if request and getattr(request.user, 'role', None) == CustomUser.Role.STUDENT:
            allowed_student_fields = {
                'email',
                'phone_number',
                'address',
                'profile_picture',
                'emergency_contact_name',
                'emergency_contact_phone',
                'emergency_contact_relationship',
            }
            for name, field in fields.items():
                if name not in allowed_student_fields and name not in self.Meta.read_only_fields:
                    field.read_only = True
        return fields

    def update(self, instance, validated_data):
        # Extract nested student_profile data
        student_profile_data = validated_data.pop('student_profile', {})
        instance = super().update(instance, validated_data)
        if student_profile_data and hasattr(instance, 'student_profile'):
            student = instance.student_profile
            for attr, value in student_profile_data.items():
                setattr(student, attr, value)
            student.save(update_fields=list(student_profile_data.keys()))
        return instance


class PublicStaffSerializer(serializers.ModelSerializer):
    sections = serializers.SerializerMethodField()
    profile_picture = serializers.SerializerMethodField()
    class Meta:
        model = CustomUser
        fields = ['id', 'first_name', 'last_name', 'role', 'profile_picture', 'sections']
        read_only_fields = ['id', 'first_name', 'last_name', 'role', 'profile_picture', 'sections']

    def get_sections(self, obj):
        if obj.role != 'adviser':
            return []
        adviser = Adviser.objects.prefetch_related('sections').filter(user=obj).first()
        if not adviser:
            return []
        return [
            {
                'id': str(section.id),
                'name': section.name,
            }
            for section in adviser.sections.all()
        ]

    def get_profile_picture(self, obj):
        request = self.context.get('request')
        if not obj.profile_picture:
            return None
        url = obj.profile_picture.url
        if request:
            return request.build_absolute_uri(url)
        return url


class ChangePasswordSerializer(serializers.Serializer):
    current_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(write_only=True, min_length=8)
    confirm_password = serializers.CharField(write_only=True, min_length=8)

    def validate(self, attrs):
        if attrs['new_password'] != attrs['confirm_password']:
            raise serializers.ValidationError({"confirm_password": "Passwords do not match."})
        return attrs


class StudentSerializer(serializers.ModelSerializer):
    user_name = serializers.CharField(source='user.get_full_name', read_only=True)

    class Meta:
        model = Student
        fields = ['id', 'user', 'user_name', 'student_number', 'admission_date']
        read_only_fields = ['id']


class InstructorSerializer(serializers.ModelSerializer):
    user_name = serializers.CharField(source='user.get_full_name', read_only=True)
    department_name = serializers.CharField(source='department.name', read_only=True)

    class Meta:
        model = Instructor
        fields = ['id', 'user', 'user_name', 'department', 'department_name', 'hire_date']
        read_only_fields = ['id']


class AdviserSerializer(serializers.ModelSerializer):
    user_name = serializers.CharField(source='user.get_full_name', read_only=True)
    department_name = serializers.CharField(source='department.name', read_only=True)
    program_name = serializers.CharField(source='program.name', read_only=True)
    section = serializers.PrimaryKeyRelatedField(
        queryset=Section.objects.all(),
        write_only=True,
        required=False
    )
    sections = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = Adviser
        fields = [
            'id', 'user', 'user_name', 'program', 'program_name',
            'department', 'department_name', 'hire_date', 'section', 'sections'
        ]
        read_only_fields = ['id']

    def get_sections(self, obj):
        return [
            {
                'id': section.id,
                'name': section.name,
                'year_level': section.year_level.name,
            }
            for section in obj.sections.select_related('year_level').all()
        ]

    def validate(self, attrs):
        program = attrs.get('program') or (self.instance.program if self.instance else None)
        if not program:
            raise serializers.ValidationError({"program": "Adviser must be assigned to a strand or grade."})

        program_type = (program.type or "").strip().lower()
        if program_type not in ['strand', 'grade']:
            raise serializers.ValidationError({"program": "Program must be a strand or grade."})

        if not program.department.school_level.is_high_school:
            raise serializers.ValidationError({"program": "Program must belong to a high school level."})

        department = attrs.get('department') or (self.instance.department if self.instance else None)
        if department and department.id != program.department_id:
            raise serializers.ValidationError({"department": "Department must match the program's department."})

        section = attrs.get('section')
        if section:
            if not section.is_high_school:
                raise serializers.ValidationError({"section": "Only high school sections can be assigned."})
            if section.year_level.program_id != program.id:
                raise serializers.ValidationError({"section": "Section must match the selected strand/grade."})
            if section.adviser_id and (not self.instance or section.adviser_id != self.instance.id):
                raise serializers.ValidationError({"section": "This section already has an adviser."})

        return attrs

    def create(self, validated_data):
        section = validated_data.pop('section', None)
        adviser = super().create(validated_data)
        if section:
            section.adviser = adviser
            section.full_clean()
            section.save(update_fields=['adviser'])
        return adviser

    def update(self, instance, validated_data):
        section = validated_data.pop('section', None)
        adviser = super().update(instance, validated_data)
        if section:
            section.adviser = adviser
            section.full_clean()
            section.save(update_fields=['adviser'])
        return adviser


class PrincipalSerializer(serializers.ModelSerializer):
    user_name = serializers.CharField(source='user.get_full_name', read_only=True)
    school_level_name = serializers.CharField(source='school_level.name', read_only=True)

    class Meta:
        model = Principal
        fields = ['id', 'user', 'user_name', 'school_level', 'school_level_name', 'appointed_date']
        read_only_fields = ['id']


class DeanSerializer(serializers.ModelSerializer):
    user_name = serializers.CharField(source='user.get_full_name', read_only=True)
    department_name = serializers.CharField(source='department.name', read_only=True)

    class Meta:
        model = Dean
        fields = ['id', 'user', 'user_name', 'department', 'department_name', 'appointed_date']
        read_only_fields = ['id']


class AdminProfileSerializer(serializers.ModelSerializer):
    user_name = serializers.CharField(source='user.get_full_name', read_only=True)

    class Meta:
        model = AdminProfile
        fields = ['id', 'user', 'user_name', 'employee_id']
        read_only_fields = ['id']
