from django.urls import path, include
from main.routers import NoFormatSuffixRouter
from .views import LearningMaterialViewSet

router = NoFormatSuffixRouter()
router.register(r'', LearningMaterialViewSet, basename='learning-material')

urlpatterns = [
    path('', include(router.urls)),
]
