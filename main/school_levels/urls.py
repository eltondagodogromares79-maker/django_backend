from django.urls import path, include
from main.routers import NoFormatSuffixRouter
from .views import SchoolLevelViewSet, SchoolYearViewSet, TermViewSet

router = NoFormatSuffixRouter()
router.register(r'', SchoolLevelViewSet, basename='schoollevel')
router.register(r'school-years', SchoolYearViewSet, basename='schoolyear')
router.register(r'terms', TermViewSet, basename='term')

urlpatterns = [
    path('', include(router.urls)),
]
