from django.urls import path, include
from main.routers import NoFormatSuffixRouter
from .views import ChatMessageViewSet, ChatReadReceiptView, ChatContactsView, ChatRoomViewSet, ChatReactionView, ChatConversationDeleteView, ChatGroupView, ChatGroupMemberView

router = NoFormatSuffixRouter()
router.register(r'messages', ChatMessageViewSet, basename='chat-message')
router.register(r'rooms', ChatRoomViewSet, basename='chat-room')

urlpatterns = [
    path('conversations/<path:room_key>/', ChatConversationDeleteView.as_view(), name='chat-conversation-delete'),
    path('groups/', ChatGroupView.as_view(), name='chat-groups'),
    path('groups/<path:room_key>/members/', ChatGroupMemberView.as_view(), name='chat-group-members'),
    path('read/', ChatReadReceiptView.as_view(), name='chat-read'),
    path('contacts/', ChatContactsView.as_view(), name='chat-contacts'),
    path('reactions/', ChatReactionView.as_view(), name='chat-reactions'),
    path('', include(router.urls)),
]
