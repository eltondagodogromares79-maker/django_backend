from django.urls import path, include
from main.routers import NoFormatSuffixRouter
from .views import AnnouncementViewSet

router = NoFormatSuffixRouter()
router.register(r'', AnnouncementViewSet, basename='announcement')

urlpatterns = [
    path('', include(router.urls)),
]
