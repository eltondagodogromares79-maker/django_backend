from rest_framework import serializers
from .models import SchoolLevel, SchoolYear, Term


class SchoolLevelSerializer(serializers.ModelSerializer):
    class Meta:
        model = SchoolLevel
        fields = ['id', 'name', 'created_at']
        read_only_fields = ['id', 'created_at']


class TermSerializer(serializers.ModelSerializer):

    class Meta:
        model = Term
        fields = ['id', 'semester', 'school_year', 'start_date', 'end_date', 'created_at']
        read_only_fields = ['id', 'created_at']


class SchoolYearSerializer(serializers.ModelSerializer):
    class Meta:
        model = SchoolYear
        fields = ['id', 'name', 'start_date', 'end_date', 'is_active', 'created_at']
        read_only_fields = ['id', 'created_at']
