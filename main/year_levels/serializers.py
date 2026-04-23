from rest_framework import serializers
from .models import YearLevel


class YearLevelSerializer(serializers.ModelSerializer):
    program_name = serializers.CharField(source='program.name', read_only=True)
    
    class Meta:
        model = YearLevel
        fields = [
            'id', 'name', 'order_number', 'program', 'program_name',
            'created_at'
        ]
        read_only_fields = ['id', 'created_at']
