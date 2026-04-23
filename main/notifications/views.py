from django.utils import timezone
from rest_framework import mixins, viewsets, status
from rest_framework.pagination import PageNumberPagination
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from .models import Notification
from .serializers import NotificationSerializer


class NotificationPagination(PageNumberPagination):
    page_size = 12
    page_size_query_param = 'page_size'
    max_page_size = 50


class NotificationViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    serializer_class = NotificationSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = NotificationPagination

    def get_queryset(self):
        return Notification.objects.filter(user=self.request.user)

    @action(detail=False, methods=['post'])
    def mark_read(self, request):
        ids = request.data.get('ids') or []
        mark_all = request.data.get('all', False)
        queryset = Notification.objects.filter(user=request.user, is_read=False)
        if mark_all:
            updated = queryset.update(is_read=True, read_at=timezone.now())
            return Response({'updated': updated})
        if isinstance(ids, str):
            ids = [ids]
        if not isinstance(ids, list) or not ids:
            return Response({'error': 'ids are required'}, status=status.HTTP_400_BAD_REQUEST)
        updated = queryset.filter(id__in=ids).update(is_read=True, read_at=timezone.now())
        return Response({'updated': updated})

    @action(detail=False, methods=['post'])
    def bulk_delete(self, request):
        ids = request.data.get('ids') or []
        delete_all = request.data.get('all', False)
        queryset = Notification.objects.filter(user=request.user)
        if delete_all:
            deleted = queryset.count()
            queryset.delete()
            return Response({'deleted': deleted})
        if isinstance(ids, str):
            ids = [ids]
        if not isinstance(ids, list) or not ids:
            return Response({'error': 'ids are required'}, status=status.HTTP_400_BAD_REQUEST)
        deleted, _ = queryset.filter(id__in=ids).delete()
        return Response({'deleted': deleted})
