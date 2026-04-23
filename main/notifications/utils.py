from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer


def push_notification(user_id, payload):
    channel_layer = get_channel_layer()
    if not channel_layer:
        return
    async_to_sync(channel_layer.group_send)(
        f"notifications_{user_id}",
        {"type": "notify", "payload": payload},
    )
