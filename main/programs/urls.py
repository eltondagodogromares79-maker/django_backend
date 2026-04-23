from django.urls import path, include
from main.routers import NoFormatSuffixRouter
from .views import ProgramViewSet

router = NoFormatSuffixRouter()
router.register(r'', ProgramViewSet, basename='program')

urlpatterns = [
    path('', include(router.urls)),
]