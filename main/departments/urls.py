from django.urls import path, include
from main.routers import NoFormatSuffixRouter
from .views import DepartmentViewSet

router = NoFormatSuffixRouter()
router.register(r'', DepartmentViewSet, basename='department')

urlpatterns = [
    path('', include(router.urls)),
]