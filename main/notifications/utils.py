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


def _publish_notification_events(events):
    endpoint = getattr(settings, 'CHAT_SERVER_HTTP_URL', '').rstrip('/')
    token = getattr(settings, 'CHAT_SERVER_TOKEN', '')
    if not endpoint or not token:
        return
    if not events:
        return

    try:
        requests.post(
            f"{endpoint}/internal/notifications/bulk/",
            json={'events': events},
            headers={'Authorization': f'Bearer {token}'},
            timeout=5,
        )
    except requests.RequestException:
        return


def push_notification(user_id, payload):
    push_notifications([(user_id, payload)])


def push_notifications(events):
    normalized = [
        {
            'user_id': str(user_id),
            'payload': {
                'type': 'notification',
                'data': payload,
            },
        }
        for user_id, payload in events
        if user_id and payload
    ]
    _publish_notification_events(normalized)


def push_notification_deletes(events):
    normalized_events = []
    for user_id, ids in events:
        normalized_ids = [str(notification_id) for notification_id in ids if notification_id]
        if not user_id or not normalized_ids:
            continue
        normalized_events.append(
            {
                'user_id': str(user_id),
                'payload': {
                    'type': 'notification_deleted',
                    'data': {'ids': normalized_ids},
                },
            }
        )
    _publish_notification_events(normalized_events)


def push_notification_delete(user_id, ids):
    normalized_ids = [str(notification_id) for notification_id in ids if notification_id]
    if not normalized_ids:
        return
    push_notification_deletes([(user_id, normalized_ids)])
