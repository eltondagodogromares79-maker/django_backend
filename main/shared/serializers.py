from django.utils.html import strip_tags
from rest_framework import serializers


class SanitizedModelSerializer(serializers.ModelSerializer):
    """
    Base serializer that strips HTML tags and trims whitespace for selected fields.
    """

    sanitize_fields: tuple[str, ...] = ()

    def validate(self, attrs):
        attrs = super().validate(attrs)
        for field in self.sanitize_fields:
            if field not in attrs:
                continue
            value = attrs.get(field)
            if not isinstance(value, str):
                continue
            cleaned = strip_tags(value).replace('\x00', '').strip()
            serializer_field = self.fields.get(field)
            if cleaned == '' and serializer_field is not None and getattr(serializer_field, 'allow_null', False):
                attrs[field] = None
            else:
                attrs[field] = cleaned
        return attrs
