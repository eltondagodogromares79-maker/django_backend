from django.urls import path, include
from main.routers import NoFormatSuffixRouter
from .views import (
    UserViewSet,
    StudentViewSet,
    InstructorViewSet,
    AdviserViewSet,
    PrincipalViewSet,
    DeanViewSet,
    AdminProfileViewSet,
    LoginView,
    RefreshTokenView,
    LogoutView,
    LogoutAllDevicesView,
    VerifyTokenView,
    PasswordResetRequestView,
    PasswordResetVerifyView,
    PasswordResetConfirmView,
    PublicStaffListView,
    PublicStaffDetailView,
)

router = NoFormatSuffixRouter()
router.register(r'students', StudentViewSet, basename='student')
router.register(r'instructors', InstructorViewSet, basename='instructor')
router.register(r'advisers', AdviserViewSet, basename='adviser')
router.register(r'principals', PrincipalViewSet, basename='principal')
router.register(r'deans', DeanViewSet, basename='dean')
router.register(r'admins', AdminProfileViewSet, basename='admin-profile')
router.register(r'', UserViewSet, basename='user')

urlpatterns = [
    path('public-staff/', PublicStaffListView.as_view(), name='public_staff_list'),
    path('public-staff/<uuid:pk>/', PublicStaffDetailView.as_view(), name='public_staff_detail'),
    path('login/', LoginView.as_view(), name='user_login'),
    path('refresh/', RefreshTokenView.as_view(), name='user_refresh'),
    path('logout/', LogoutView.as_view(), name='user_logout'),
    path('logout-all/', LogoutAllDevicesView.as_view(), name='user_logout_all'),
    path('verify/', VerifyTokenView.as_view(), name='user_verify'),
    path('password-reset/request/', PasswordResetRequestView.as_view(), name='password_reset_request'),
    path('password-reset/verify/', PasswordResetVerifyView.as_view(), name='password_reset_verify'),
    path('password-reset/confirm/', PasswordResetConfirmView.as_view(), name='password_reset_confirm'),
    path('chat-context/', UserViewSet.as_view({'get': 'chat_context'}), name='user_chat_context'),
    path('chat-ws-token/', UserViewSet.as_view({'get': 'chat_ws_token'}), name='user_chat_ws_token'),
    path('students/', StudentViewSet.as_view({'get': 'list'}), name='student-list'),
    path('', include(router.urls)),
]
