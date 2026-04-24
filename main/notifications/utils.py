import requests
from django.conf import settings


def serialize_notification(notification):
    return {
        'id': str(notification.id),
        'kind': notification.kind,
        'title': notification.title,
        'body': notification.body,
        'target_id': str(notification.target_id),
        'section_subject_id': str(notification.section_subject_id) if notification.section_subject_id else None,
        'is_read': notification.is_read,
        'read_at': notification.read_at.isoformat() if notification.read_at else None,
        'created_at': notification.created_at.isoformat(),
    }


def _publish_notification_event(user_id, event_type, data):
    endpoint = getattr(settings, 'CHAT_SERVER_HTTP_URL', '').rstrip('/')
    token = getattr(settings, 'CHAT_SERVER_TOKEN', '')
    if not endpoint or not token:
        return

    try:
        requests.post(
            f"{endpoint}/internal/notifications/",
            json={
                'user_id': str(user_id),
                'payload': {
                    'type': event_type,
                    'data': data,
                },
            },
            headers={'Authorization': f'Bearer {token}'},
            timeout=5,
        )
    except requests.RequestException:
        return


def push_notification(user_id, payload):
    _publish_notification_event(user_id, 'notification', payload)


def push_notification_delete(user_id, ids):
    normalized_ids = [str(notification_id) for notification_id in ids if notification_id]
    if not normalized_ids:
        return
    _publish_notification_event(user_id, 'notification_deleted', {'ids': normalized_ids})
