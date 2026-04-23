from rest_framework import serializers
from .models import Department
from shared.serializers import SanitizedModelSerializer


class DepartmentSerializer(SanitizedModelSerializer):
    sanitize_fields = ('name',)
    school_level_name = serializers.CharField(source='school_level.name', read_only=True)
    
    class Meta:
        model = Department
        fields = [
            'id', 'name', 'school_level', 'school_level_name', 'created_at'
        ]
        read_only_fields = ['id', 'created_at']
