from datetime import datetime
from django.utils.dateparse import parse_datetime
from django.utils import timezone
from rest_framework import status, viewsets
from django.db.models import Q, Count
from django.utils.text import slugify as dj_slugify
import uuid
from rest_framework.response import Response
from rest_framework.views import APIView

from users.models import CustomUser

from .models import ChatMessage, ChatReadReceipt, ChatRoom, ChatRoomMember
from .serializers import ChatMessageSerializer, ChatReadReceiptSerializer, ChatRoomSerializer, ChatContactSerializer, ChatGroupSerializer
from .permissions import ChatServerOrAuthenticated, ChatServerOnly
from .utils import (
    ensure_members,
    get_allowed_chat_contacts_queryset,
    get_or_create_room,
    parse_direct_room_members,
    update_read_receipt,
    user_can_access_room,
    user_can_direct_message,
    user_in_section,
)


class ChatRoomViewSet(viewsets.ViewSet):
    permission_classes = [ChatServerOnly]

    def create(self, request):
        room_key = request.data.get('room_key')
        room_type = request.data.get('room_type')
        members = request.data.get('members', [])
        created_by = request.data.get('created_by')
        created_by_user = None

        if not room_key:
            return Response({'error': 'room_key is required'}, status=status.HTTP_400_BAD_REQUEST)

        if created_by:
            try:
                created_by_user = CustomUser.objects.get(id=created_by)
            except CustomUser.DoesNotExist:
                return Response({'error': 'created_by user not found'}, status=status.HTTP_404_NOT_FOUND)

        try:
            room = get_or_create_room(room_key, room_type=room_type, created_by=created_by_user)
        except ValueError as exc:
            return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        if members:
            ensure_members(room, members)
        serializer = ChatRoomSerializer(room)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class ChatGroupView(APIView):
    permission_classes = [ChatServerOrAuthenticated]

    def get(self, request):
        rooms = (
            ChatRoom.objects
            .filter(room_type=ChatRoom.RoomType.GROUP, members__user=request.user)
            .annotate(member_count=Count('members'))
            .order_by('name', 'created_at')
        )
        serializer = ChatGroupSerializer(rooms, many=True)
        return Response(serializer.data)

    def post(self, request):
        name = (request.data.get('name') or '').strip()
        members = request.data.get('members', [])

        if not name:
            return Response({'error': 'name is required'}, status=status.HTTP_400_BAD_REQUEST)

        member_ids = {str(member_id) for member_id in members if member_id}
        member_ids.add(str(request.user.id))
        allowed_ids = set(get_allowed_chat_contacts_queryset(request.user).values_list('id', flat=True))
        valid_ids = set(
            CustomUser.objects.filter(id__in=member_ids, is_active=True).values_list('id', flat=True)
        ) & allowed_ids
        valid_ids.add(request.user.id)
        if not valid_ids:
            return Response({'error': 'members are invalid'}, status=status.HTTP_400_BAD_REQUEST)
        member_ids = [str(member_id) for member_id in valid_ids]

        slug = dj_slugify(name) or 'group'
        room_key = f"group:{slug}-{uuid.uuid4().hex[:6]}"

        try:
            room = get_or_create_room(room_key, room_type=ChatRoom.RoomType.GROUP, created_by=request.user)
        except ValueError as exc:
            return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        room.name = name
        room.save(update_fields=['name'])
        ensure_members(room, member_ids)

        serializer = ChatGroupSerializer(room)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class ChatGroupMemberView(APIView):
    permission_classes = [ChatServerOrAuthenticated]

    def get(self, request, room_key):
        try:
            room = ChatRoom.objects.get(room_key=room_key, room_type=ChatRoom.RoomType.GROUP)
        except ChatRoom.DoesNotExist:
            return Response({'error': 'Group not found'}, status=status.HTTP_404_NOT_FOUND)

        if not ChatRoomMember.objects.filter(room=room, user=request.user).exists():
            return Response({'detail': 'Forbidden'}, status=status.HTTP_403_FORBIDDEN)

        members = CustomUser.objects.filter(chat_memberships__room=room, is_active=True).distinct()
        serializer = ChatContactSerializer(members, many=True)
        return Response(serializer.data)

    def post(self, request, room_key):
        members = request.data.get('members', [])
        try:
            room = ChatRoom.objects.get(room_key=room_key, room_type=ChatRoom.RoomType.GROUP)
        except ChatRoom.DoesNotExist:
            return Response({'error': 'Group not found'}, status=status.HTTP_404_NOT_FOUND)

        if not ChatRoomMember.objects.filter(room=room, user=request.user).exists():
            return Response({'detail': 'Forbidden'}, status=status.HTTP_403_FORBIDDEN)

        if room.created_by_id != request.user.id:
            return Response({'detail': 'Only the creator can add members'}, status=status.HTTP_403_FORBIDDEN)

        member_ids = {str(member_id) for member_id in members if member_id}
        if not member_ids:
            return Response({'error': 'members are required'}, status=status.HTTP_400_BAD_REQUEST)
        allowed_ids = set(get_allowed_chat_contacts_queryset(request.user).values_list('id', flat=True))
        valid_ids = set(
            CustomUser.objects.filter(id__in=member_ids, is_active=True).values_list('id', flat=True)
        ) & allowed_ids
        if not valid_ids:
            return Response({'error': 'members are invalid'}, status=status.HTTP_400_BAD_REQUEST)
        ensure_members(room, valid_ids)
        serializer = ChatGroupSerializer(room)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def delete(self, request, room_key):
        try:
            room = ChatRoom.objects.get(room_key=room_key, room_type=ChatRoom.RoomType.GROUP)
        except ChatRoom.DoesNotExist:
            return Response({'error': 'Group not found'}, status=status.HTTP_404_NOT_FOUND)

        membership = ChatRoomMember.objects.filter(room=room, user=request.user).first()
        if not membership:
            return Response({'detail': 'Forbidden'}, status=status.HTTP_403_FORBIDDEN)

        membership.is_hidden = True
        membership.cleared_at = timezone.now()
        membership.save(update_fields=['is_hidden', 'cleared_at'])
        return Response(status=status.HTTP_204_NO_CONTENT)


class ChatConversationDeleteView(APIView):
    permission_classes = [ChatServerOrAuthenticated]

    def delete(self, request, room_key):
        if request.headers.get('X-Chat-Server-Token'):
            return Response({'detail': 'Not allowed'}, status=status.HTTP_403_FORBIDDEN)

        room = ChatRoom.objects.filter(room_key=room_key).first()
        if not room:
            return Response(status=status.HTTP_204_NO_CONTENT)

        if not user_can_access_room(request.user, room):
            return Response({'detail': 'Forbidden'}, status=status.HTTP_403_FORBIDDEN)

        membership, _ = ChatRoomMember.objects.get_or_create(room=room, user=request.user)
        if not membership.is_hidden:
            membership.is_hidden = True
        membership.cleared_at = timezone.now()
        membership.save(update_fields=['is_hidden', 'cleared_at'])

        return Response(status=status.HTTP_204_NO_CONTENT)


class ChatMessageViewSet(viewsets.ViewSet):
    permission_classes = [ChatServerOrAuthenticated]

    def list(self, request):
        room_key = request.query_params.get('room_key')
        if not room_key:
            return Response({'error': 'room_key query param is required'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            room = get_or_create_room(room_key)
        except ValueError as exc:
            return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        membership = None
        if not request.headers.get('X-Chat-Server-Token'):
            if not user_can_access_room(request.user, room):
                return Response({'detail': 'Forbidden'}, status=status.HTTP_403_FORBIDDEN)
            membership = ChatRoomMember.objects.filter(room=room, user=request.user).first()
            if membership is None:
                membership = ChatRoomMember.objects.create(room=room, user=request.user)

        limit_param = request.query_params.get('limit')
        before_param = request.query_params.get('before')
        limit = 50
        if limit_param:
            try:
                limit = max(1, min(int(limit_param), 100))
            except ValueError:
                return Response({'error': 'limit must be an integer'}, status=status.HTTP_400_BAD_REQUEST)

        queryset = ChatMessage.objects.filter(room=room)
        if membership and membership.cleared_at:
            queryset = queryset.filter(sent_at__gt=membership.cleared_at)
        if before_param:
            before_dt = parse_datetime(before_param)
            if before_dt is None:
                return Response({'error': 'before must be an ISO datetime'}, status=status.HTTP_400_BAD_REQUEST)
            queryset = queryset.filter(sent_at__lt=before_dt)

        messages_desc = list(queryset.order_by('-sent_at')[:limit])
        messages = list(reversed(messages_desc))
        serializer = ChatMessageSerializer(messages, many=True)
        receipts = ChatReadReceipt.objects.filter(room=room)
        receipt_data = ChatReadReceiptSerializer(receipts, many=True).data

        next_before = None
        has_more = False
        if messages:
            oldest = messages[0].sent_at
            has_more = ChatMessage.objects.filter(room=room, sent_at__lt=oldest).exists()
            if has_more:
                next_before = oldest.isoformat()

        return Response({
            'room': ChatRoomSerializer(room).data,
            'messages': serializer.data,
            'read_receipts': receipt_data,
            'has_more': has_more,
            'next_before': next_before,
        })

    def create(self, request):
        room_key = request.data.get('room_key')
        room_type = request.data.get('room_type')
        sender_id = request.data.get('sender_id')
        content = request.data.get('content')
        kind = request.data.get('kind', 'text')
        sent_at = request.data.get('sent_at')
        members = request.data.get('members', [])
        reply_to_id = request.data.get('reply_to_id')

        if not room_key or not sender_id or not content:
            return Response({'error': 'room_key, sender_id and content are required'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            sender = CustomUser.objects.get(id=sender_id)
        except CustomUser.DoesNotExist:
            return Response({'error': 'Sender not found'}, status=status.HTTP_404_NOT_FOUND)

        try:
            room = get_or_create_room(room_key, room_type=room_type, created_by=sender)
        except ValueError as exc:
            return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        if not request.headers.get('X-Chat-Server-Token') and request.user.id != sender.id:
            return Response({'detail': 'Forbidden'}, status=status.HTTP_403_FORBIDDEN)

        member_ids = members or [sender_id]
        if member_ids:
            ensure_members(room, member_ids)
            ChatRoomMember.objects.filter(room=room, user_id__in=member_ids).update(is_hidden=False)
        else:
            # Ensure sender is member for direct/group rooms
            if room.room_type != ChatRoom.RoomType.SECTION:
                ensure_members(room, [sender_id])

        if room.room_type == ChatRoom.RoomType.SECTION and not user_in_section(sender, room.section_id):
            return Response({'error': 'Sender is not allowed in this section'}, status=status.HTTP_403_FORBIDDEN)

        if room.room_type == ChatRoom.RoomType.DIRECT:
            direct_members = parse_direct_room_members(room.room_key)
            if not direct_members:
                return Response({'error': 'Invalid direct room'}, status=status.HTTP_400_BAD_REQUEST)
            left_id, right_id = direct_members
            sender_id_str = str(sender.id)
            if sender_id_str not in {left_id, right_id}:
                return Response({'error': 'Sender is not part of this conversation'}, status=status.HTTP_403_FORBIDDEN)
            other_id = right_id if left_id == sender_id_str else left_id
            other_user = CustomUser.objects.filter(id=other_id, is_active=True).first()
            if not other_user or not user_can_direct_message(sender, other_user):
                return Response({'error': 'Direct messaging is not allowed with this user'}, status=status.HTTP_403_FORBIDDEN)
            ensure_members(room, [sender_id_str, other_id])
            ChatRoomMember.objects.filter(room=room, user_id__in=[sender_id_str, other_id]).update(is_hidden=False)

        reply_to = None
        if reply_to_id:
            try:
                reply_to = ChatMessage.objects.get(id=reply_to_id, room=room)
            except ChatMessage.DoesNotExist:
                return Response({'error': 'Reply target not found'}, status=status.HTTP_404_NOT_FOUND)

        if isinstance(sent_at, str):
            sent_at_dt = parse_datetime(sent_at) or timezone.now()
        elif isinstance(sent_at, datetime):
            sent_at_dt = sent_at
        else:
            sent_at_dt = timezone.now()

        message = ChatMessage.objects.create(
            room=room,
            sender=sender,
            reply_to=reply_to,
            content=content,
            kind=kind,
            sent_at=sent_at_dt,
        )

        return Response(ChatMessageSerializer(message).data, status=status.HTTP_201_CREATED)

    def partial_update(self, request, pk=None):
        if not pk:
            return Response({'error': 'Message id is required'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            message = ChatMessage.objects.get(id=pk)
        except ChatMessage.DoesNotExist:
            return Response({'error': 'Message not found'}, status=status.HTTP_404_NOT_FOUND)

        if not request.headers.get('X-Chat-Server-Token'):
            if message.sender_id != request.user.id:
                return Response({'detail': 'Forbidden'}, status=status.HTTP_403_FORBIDDEN)

        content = request.data.get('content')
        if content is None or not str(content).strip():
            return Response({'error': 'content is required'}, status=status.HTTP_400_BAD_REQUEST)

        message.content = content
        message.save(update_fields=['content'])
        return Response(ChatMessageSerializer(message).data)

    def destroy(self, request, pk=None):
        if not pk:
            return Response({'error': 'Message id is required'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            message = ChatMessage.objects.get(id=pk)
        except ChatMessage.DoesNotExist:
            return Response({'error': 'Message not found'}, status=status.HTTP_404_NOT_FOUND)

        if not request.headers.get('X-Chat-Server-Token'):
            if message.sender_id != request.user.id:
                return Response({'detail': 'Forbidden'}, status=status.HTTP_403_FORBIDDEN)

        message.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class ChatReadReceiptView(APIView):
    permission_classes = [ChatServerOrAuthenticated]

    def post(self, request):
        room_key = request.data.get('room_key')
        last_read_at = request.data.get('last_read_at')
        user_id = request.data.get('user_id')

        if not room_key:
            return Response({'error': 'room_key is required'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            room = get_or_create_room(room_key)
        except ValueError as exc:
            return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        if request.headers.get('X-Chat-Server-Token'):
            if not user_id:
                return Response({'error': 'user_id is required for token requests'}, status=status.HTTP_400_BAD_REQUEST)
            try:
                user = CustomUser.objects.get(id=user_id)
            except CustomUser.DoesNotExist:
                return Response({'error': 'User not found'}, status=status.HTTP_404_NOT_FOUND)
        else:
            user = request.user
            if not user_can_access_room(user, room):
                return Response({'detail': 'Forbidden'}, status=status.HTTP_403_FORBIDDEN)

        if isinstance(last_read_at, str):
            last_read_at_dt = parse_datetime(last_read_at) or timezone.now()
        elif isinstance(last_read_at, datetime):
            last_read_at_dt = last_read_at
        else:
            last_read_at_dt = timezone.now()

        receipt = update_read_receipt(room, user, last_read_at_dt)
        return Response(ChatReadReceiptSerializer(receipt).data, status=status.HTTP_200_OK)


class ChatContactsView(APIView):
    def get(self, request):
        user = request.user
        query = (request.query_params.get('q') or '').strip()
        all_users = (request.query_params.get('all') or '').lower() == 'true'
        allowed_contacts = get_allowed_chat_contacts_queryset(user)

        if all_users and not query:
            contacts = allowed_contacts[:200]
            serializer = ChatContactSerializer(contacts, many=True)
            return Response(serializer.data)
        if query:
            contacts = allowed_contacts.filter(
                Q(first_name__icontains=query)
                | Q(last_name__icontains=query)
                | Q(email__icontains=query)
            )
            serializer = ChatContactSerializer(contacts.distinct()[:50], many=True)
            return Response(serializer.data)

        contacts = CustomUser.objects.none()

        # If no query and not listing all, show only users with existing conversations.
        if not query and not all_users:
            member_rooms = (
                ChatRoomMember.objects
                .select_related('room')
                .filter(user=user, room__room_type=ChatRoom.RoomType.DIRECT)
            )
            other_user_ids = []
            for membership in member_rooms:
                room = membership.room
                last_message = ChatMessage.objects.filter(room=room).order_by('-sent_at').first()
                if not last_message:
                    continue
                if membership.cleared_at and last_message.sent_at <= membership.cleared_at:
                    continue
                if membership.is_hidden:
                    membership.is_hidden = False
                    membership.save(update_fields=['is_hidden'])
                room_key = room.room_key
                if room_key.startswith('dm:'):
                    parts = room_key.split(':')
                    if len(parts) >= 3:
                        a = parts[1]
                        b = parts[2]
                        other_id = a if str(user.id) != a else b
                        if allowed_contacts.filter(id=other_id).exists():
                            other_user_ids.append(other_id)
            if other_user_ids:
                contacts = CustomUser.objects.filter(id__in=other_user_ids).exclude(id=user.id)

        serializer = ChatContactSerializer(contacts.distinct(), many=True)
        return Response(serializer.data)


class ChatReactionView(APIView):
    permission_classes = [ChatServerOrAuthenticated]

    def post(self, request):
        message_id = request.data.get('message_id')
        emoji = request.data.get('emoji')
        user_id = request.data.get('user_id')

        if not message_id or not emoji:
            return Response({'error': 'message_id and emoji are required'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            message = ChatMessage.objects.select_related('room').get(id=message_id)
        except ChatMessage.DoesNotExist:
            return Response({'error': 'Message not found'}, status=status.HTTP_404_NOT_FOUND)

        if request.headers.get('X-Chat-Server-Token'):
            if not user_id:
                return Response({'error': 'user_id is required for token requests'}, status=status.HTTP_400_BAD_REQUEST)
            try:
                user = CustomUser.objects.get(id=user_id)
            except CustomUser.DoesNotExist:
                return Response({'error': 'User not found'}, status=status.HTTP_404_NOT_FOUND)
        else:
            user = request.user
            if not user_can_access_room(user, message.room):
                return Response({'detail': 'Forbidden'}, status=status.HTTP_403_FORBIDDEN)

        reactions = message.reactions or {}
        user_key = str(user.id)
        had_same_reaction = user_key in reactions.get(emoji, [])
        # Ensure one reaction per user per message: remove user from all emojis first.
        cleaned = {}
        for key, users in reactions.items():
            cleaned_users = [uid for uid in users if uid != user_key]
            if cleaned_users:
                cleaned[key] = cleaned_users

        if not had_same_reaction:
            current = cleaned.get(emoji, [])
            current = current + [user_key]
            cleaned[emoji] = current
        reactions = cleaned

        message.reactions = reactions
        message.save(update_fields=['reactions'])
        return Response({'message_id': str(message.id), 'reactions': reactions})
