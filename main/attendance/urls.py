from django.urls import path, include
from main.routers import NoFormatSuffixRouter
from .views import AttendanceSessionViewSet

router = NoFormatSuffixRouter()
router.register(r'sessions', AttendanceSessionViewSet, basename='attendance-session')

urlpatterns = [
    path('', include(router.urls)),
]
