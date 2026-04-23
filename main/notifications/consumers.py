from urllib.parse import parse_qs
from django.contrib.auth import get_user_model
from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from rest_framework_simplejwt.tokens import UntypedToken
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError


def _get_token_from_scope(scope):
    query_string = scope.get('query_string', b'').decode('utf-8')
    params = parse_qs(query_string)
    token = params.get('token', [None])[0]
    if token:
        return token
    headers = dict(scope.get('headers') or [])
    cookie_header = headers.get(b'cookie', b'').decode('utf-8')
    if not cookie_header:
        return None
    for chunk in cookie_header.split(';'):
        if '=' not in chunk:
            continue
        key, value = chunk.strip().split('=', 1)
        if key == 'access_token':
            return value
    return None


@database_sync_to_async
def _get_user_from_token(token):
    if not token:
        return None
    try:
        validated = UntypedToken(token)
    except (InvalidToken, TokenError):
        return None
    user_id = validated.get('user_id')
    if not user_id:
        return None
    User = get_user_model()
    try:
        return User.objects.get(id=user_id)
    except User.DoesNotExist:
        return None


class NotificationConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        token = _get_token_from_scope(self.scope)
        user = await _get_user_from_token(token)
        if not user or not user.is_authenticated:
            await self.close(code=4401)
            return
        self.user = user
        self.group_name = f"notifications_{user.id}"
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, code):
        if hasattr(self, 'group_name'):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def notify(self, event):
        payload = event.get('payload', {})
        await self.send_json({'type': 'notification', 'data': payload})
