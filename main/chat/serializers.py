from rest_framework import serializers
from users.models import CustomUser
from .models import ChatMessage, ChatReadReceipt, ChatRoom
from shared.serializers import SanitizedModelSerializer


class ChatMessageSerializer(SanitizedModelSerializer):
    sanitize_fields = ('content',)
    sender_name = serializers.SerializerMethodField()
    room_key = serializers.CharField(source='room.room_key', read_only=True)
    reply_to_id = serializers.UUIDField(source='reply_to.id', read_only=True)
    reply_to_content = serializers.CharField(source='reply_to.content', read_only=True)
    reply_to_sender = serializers.SerializerMethodField()

    class Meta:
        model = ChatMessage
        fields = (
            'id',
            'room_key',
            'sender',
            'sender_name',
            'content',
            'kind',
            'sent_at',
            'reply_to_id',
            'reply_to_content',
            'reply_to_sender',
            'reactions',
        )

    def get_sender_name(self, obj: ChatMessage):
        return obj.sender.get_full_name()

    def get_reply_to_sender(self, obj: ChatMessage):
        if obj.reply_to_id and obj.reply_to:
            return obj.reply_to.sender.get_full_name()
        return None


class ChatReadReceiptSerializer(serializers.ModelSerializer):
    class Meta:
        model = ChatReadReceipt
        fields = ('user', 'last_read_at')


class ChatRoomSerializer(serializers.ModelSerializer):
    class Meta:
        model = ChatRoom
        fields = ('id', 'room_key', 'room_type', 'name')


class ChatGroupSerializer(serializers.ModelSerializer):
    member_count = serializers.SerializerMethodField()
    created_by = serializers.UUIDField(source='created_by_id', read_only=True)

    class Meta:
        model = ChatRoom
        fields = ('id', 'room_key', 'room_type', 'name', 'member_count', 'created_by')

    def get_member_count(self, obj: ChatRoom):
        return getattr(obj, 'member_count', None) or obj.members.count()


class ChatContactSerializer(serializers.ModelSerializer):
    full_name = serializers.SerializerMethodField()
    profile_picture = serializers.SerializerMethodField()

    class Meta:
        model = CustomUser
        fields = ('id', 'full_name', 'role', 'profile_picture')

    def get_full_name(self, obj: CustomUser):
        return obj.get_full_name()

    def get_profile_picture(self, obj: CustomUser):
        if not obj.profile_picture:
            return None
        try:
            return obj.profile_picture.url
        except Exception:
            return None
