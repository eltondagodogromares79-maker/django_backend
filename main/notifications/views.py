from django.utils import timezone
from rest_framework import mixins, viewsets, status
from rest_framework.pagination import PageNumberPagination
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from .models import Notification
from .serializers import NotificationSerializer
from .utils import (
    push_notification,
    push_notification_delete,
    push_notifications,
    serialize_notification,
)


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

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        notification_id = str(instance.id)
        response = super().destroy(request, *args, **kwargs)
        push_notification_delete(request.user.id, [notification_id])
        return response

    @action(detail=False, methods=['post'])
    def mark_read(self, request):
        ids = request.data.get('ids') or []
        mark_all = request.data.get('all', False)
        queryset = Notification.objects.filter(user=request.user, is_read=False)
        if mark_all:
            target_ids = list(queryset.values_list('id', flat=True))
            updated = queryset.update(is_read=True, read_at=timezone.now())
            push_notifications(
                [
                    (request.user.id, serialize_notification(notification))
                    for notification in Notification.objects.filter(user=request.user, id__in=target_ids)
                ]
            )
            return Response({'updated': updated})
        if isinstance(ids, str):
            ids = [ids]
        if not isinstance(ids, list) or not ids:
            return Response({'error': 'ids are required'}, status=status.HTTP_400_BAD_REQUEST)
        target_ids = list(queryset.filter(id__in=ids).values_list('id', flat=True))
        updated = queryset.filter(id__in=target_ids).update(is_read=True, read_at=timezone.now())
        push_notifications(
            [
                (request.user.id, serialize_notification(notification))
                for notification in Notification.objects.filter(user=request.user, id__in=target_ids)
            ]
        )
        return Response({'updated': updated})

    @action(detail=False, methods=['post'])
    def bulk_delete(self, request):
        ids = request.data.get('ids') or []
        delete_all = request.data.get('all', False)
        queryset = Notification.objects.filter(user=request.user)
        if delete_all:
            deleted_ids = list(queryset.values_list('id', flat=True))
            deleted = len(deleted_ids)
            queryset.delete()
            push_notification_delete(request.user.id, deleted_ids)
            return Response({'deleted': deleted})
        if isinstance(ids, str):
            ids = [ids]
        if not isinstance(ids, list) or not ids:
            return Response({'error': 'ids are required'}, status=status.HTTP_400_BAD_REQUEST)
        deleted_ids = list(queryset.filter(id__in=ids).values_list('id', flat=True))
        deleted, _ = queryset.filter(id__in=deleted_ids).delete()
        push_notification_delete(request.user.id, deleted_ids)
        return Response({'deleted': deleted})
