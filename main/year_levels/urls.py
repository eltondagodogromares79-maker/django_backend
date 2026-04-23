from django.urls import path, include
from main.routers import NoFormatSuffixRouter
from .views import YearLevelViewSet

router = NoFormatSuffixRouter()
router.register(r'', YearLevelViewSet, basename='year-levels')

urlpatterns = [
    path('', include(router.urls)),
]
