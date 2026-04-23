from django.urls import path, include
from main.routers import NoFormatSuffixRouter
from .views import SectionViewSet, EnrollmentViewSet, StudentSubjectViewSet, PublicSectionListViewPaginated

router = NoFormatSuffixRouter()
router.register(r'enrollments', EnrollmentViewSet, basename='enrollment')
router.register(r'student-subjects', StudentSubjectViewSet, basename='student-subject')
router.register(r'', SectionViewSet, basename='section')

urlpatterns = [
    path('public/', PublicSectionListViewPaginated.as_view({'get': 'list'}), name='public-sections'),
    path('', include(router.urls)),
]
