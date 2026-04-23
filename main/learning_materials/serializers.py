from rest_framework import serializers
from django.urls import reverse
from .models import LearningMaterial, FavoriteMaterial
from shared.serializers import SanitizedModelSerializer


class LearningMaterialSerializer(SanitizedModelSerializer):
    sanitize_fields = ('title', 'description')
    section_name = serializers.CharField(source='section_subject.section.name', read_only=True)
    subject_code = serializers.CharField(source='section_subject.subject.code', read_only=True)
    subject_id = serializers.CharField(source='section_subject.subject.id', read_only=True)
    subject_name = serializers.CharField(source='section_subject.subject.name', read_only=True)
    section_id = serializers.CharField(source='section_subject.section.id', read_only=True)
    file = serializers.FileField(required=False, allow_null=True, write_only=True)
    is_favorited = serializers.SerializerMethodField()

    class Meta:
        model = LearningMaterial
        fields = [
            'id', 'section_subject', 'section_id', 'section_name', 'subject_id', 'subject_name', 'subject_code',
            'title', 'description', 'type', 'file', 'file_url', 'is_favorited', 'created_at'
        ]
        read_only_fields = ['id', 'created_at']

    def get_is_favorited(self, obj):
        request = self.context.get('request')
        if not request or not request.user.is_authenticated:
            return False
        return FavoriteMaterial.objects.filter(student=request.user, material=obj).exists()


    def to_representation(self, instance):
        data = super().to_representation(instance)
        request = self.context.get('request')
        if instance.attachment:
            if request is not None:
                download_url = reverse('learning-material-download', kwargs={'pk': instance.pk})
                data['file_url'] = request.build_absolute_uri(download_url)
            else:
                data['file_url'] = instance.attachment.url
        return data

    def create(self, validated_data):
        file_obj = validated_data.pop('file', None)
        material = super().create(validated_data)
        if file_obj:
            material.attachment = file_obj
            material.save(update_fields=['attachment'])
        return material

    def update(self, instance, validated_data):
        file_obj = validated_data.pop('file', None)
        material = super().update(instance, validated_data)
        if file_obj is not None:
            material.attachment = file_obj
            material.save(update_fields=['attachment'])
        return material
