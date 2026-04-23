from django.contrib import admin
from .models import ChatRoom, ChatRoomMember, ChatMessage, ChatReadReceipt


@admin.register(ChatRoom)
class ChatRoomAdmin(admin.ModelAdmin):
    list_display = ('room_key', 'room_type', 'section', 'created_by', 'created_at')
    search_fields = ('room_key',)
    list_filter = ('room_type',)


@admin.register(ChatRoomMember)
class ChatRoomMemberAdmin(admin.ModelAdmin):
    list_display = ('room', 'user', 'joined_at')
    search_fields = ('room__room_key', 'user__email')


@admin.register(ChatMessage)
class ChatMessageAdmin(admin.ModelAdmin):
    list_display = ('room', 'sender', 'kind', 'sent_at')
    search_fields = ('room__room_key', 'sender__email', 'content')
    list_filter = ('kind',)


@admin.register(ChatReadReceipt)
class ChatReadReceiptAdmin(admin.ModelAdmin):
    list_display = ('room', 'user', 'last_read_at', 'updated_at')
    search_fields = ('room__room_key', 'user__email')
