from rest_framework import viewsets
from .models import Announcement
from .serializers import AnnouncementSerializer
from shared.permissions import IsTeacherOrAdmin, IsStudentOrTeacherOrAdmin


class AnnouncementViewSet(viewsets.ModelViewSet):
    queryset = Announcement.objects.select_related('section_subject')
    serializer_class = AnnouncementSerializer

    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            permission_classes = [IsTeacherOrAdmin]
        else:
            permission_classes = [IsStudentOrTeacherOrAdmin]
        return [permission() for permission in permission_classes]

    def get_queryset(self):
        user = self.request.user
        queryset = Announcement.objects.all()
        if user.role == 'student':
            return queryset.filter(section_subject__section__enrollments__student__user=user).distinct()
        if user.role in ['instructor', 'adviser']:
            return queryset.filter(section_subject__instructor__user=user)
        return queryset
