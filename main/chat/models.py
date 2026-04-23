import uuid
from django.db import models
from users.models import CustomUser
from sections.models import Section


class ChatRoom(models.Model):
    class RoomType(models.TextChoices):
        SECTION = 'section', 'Section'
        DIRECT = 'direct', 'Direct'
        GROUP = 'group', 'Group'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    room_key = models.CharField(max_length=255, unique=True)
    room_type = models.CharField(max_length=20, choices=RoomType.choices)
    name = models.CharField(max_length=120, null=True, blank=True)
    section = models.ForeignKey(Section, on_delete=models.SET_NULL, null=True, blank=True, related_name='chat_rooms')
    created_by = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True, blank=True, related_name='created_chat_rooms')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']
        indexes = [models.Index(fields=['room_type', 'room_key'])]

    def __str__(self):
        return f"{self.room_type}:{self.room_key}"


class ChatRoomMember(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    room = models.ForeignKey(ChatRoom, on_delete=models.CASCADE, related_name='members')
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='chat_memberships')
    joined_at = models.DateTimeField(auto_now_add=True)
    is_hidden = models.BooleanField(default=False)
    cleared_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = ('room', 'user')
        indexes = [models.Index(fields=['room', 'user'])]

    def __str__(self):
        return f"{self.user_id} -> {self.room.room_key}"


class ChatMessage(models.Model):
    class MessageKind(models.TextChoices):
        TEXT = 'text', 'Text'
        IMAGE = 'image', 'Image'
        FILE = 'file', 'File'
        AUDIO = 'audio', 'Audio'
        VIDEO = 'video', 'Video'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    room = models.ForeignKey(ChatRoom, on_delete=models.CASCADE, related_name='messages')
    sender = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='chat_messages')
    reply_to = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='replies'
    )
    content = models.TextField()
    kind = models.CharField(max_length=20, choices=MessageKind.choices, default=MessageKind.TEXT)
    reactions = models.JSONField(default=dict, blank=True)
    sent_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['sent_at']
        indexes = [models.Index(fields=['room', 'sent_at'])]

    def __str__(self):
        return f"{self.sender_id}: {self.content[:24]}"


class ChatReadReceipt(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    room = models.ForeignKey(ChatRoom, on_delete=models.CASCADE, related_name='read_receipts')
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='chat_read_receipts')
    last_read_at = models.DateTimeField()
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('room', 'user')
        indexes = [models.Index(fields=['room', 'user'])]

    def __str__(self):
        return f"{self.user_id} read {self.room.room_key}"
