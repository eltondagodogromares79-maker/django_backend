from django.conf import settings
from rest_framework.permissions import BasePermission


class ChatServerOrAuthenticated(BasePermission):
    def has_permission(self, request, view):
        token = request.headers.get('X-Chat-Server-Token')
        if token and token == getattr(settings, 'CHAT_SERVER_TOKEN', ''):
            return True
        return bool(request.user and request.user.is_authenticated)


class ChatServerOnly(BasePermission):
    def has_permission(self, request, view):
        token = request.headers.get('X-Chat-Server-Token')
        return bool(token and token == getattr(settings, 'CHAT_SERVER_TOKEN', ''))
