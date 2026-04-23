from django.urls import path, include
from main.routers import NoFormatSuffixRouter
from .views import SubjectViewSet, SectionSubjectViewSet, GradeViewSet

router = NoFormatSuffixRouter()
router.register(r'section-subjects', SectionSubjectViewSet, basename='section-subject')
router.register(r'grades', GradeViewSet, basename='grade')
router.register(r'', SubjectViewSet, basename='subject')

urlpatterns = [
    path('section-subjects/', SectionSubjectViewSet.as_view({'get': 'list'}), name='section-subject-list'),
    path('', include(router.urls)),
]
