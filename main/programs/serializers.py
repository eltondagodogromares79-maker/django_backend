from rest_framework import serializers
from .models import Program
from shared.serializers import SanitizedModelSerializer


class ProgramSerializer(SanitizedModelSerializer):
    sanitize_fields = ('name', 'type')
    department_name = serializers.CharField(source='department.name', read_only=True)
    
    class Meta:
        model = Program
        fields = [
            'id', 'name', 'type', 'department', 'department_name', 'created_at'
        ]
        read_only_fields = ['id', 'created_at']
