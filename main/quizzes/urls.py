from django.urls import path, include
from main.routers import NoFormatSuffixRouter
from .views import QuizViewSet, QuestionViewSet, ChoiceViewSet, QuizAttemptViewSet, QuizProctorViewSet, QuizFilterPreferenceViewSet

router = NoFormatSuffixRouter()
# Register nested resources before the root quiz routes to avoid /attempts being treated as a quiz id.
router.register(r'attempts', QuizAttemptViewSet, basename='quiz-attempt')
router.register(r'proctor', QuizProctorViewSet, basename='quiz-proctor')
router.register(r'filters', QuizFilterPreferenceViewSet, basename='quiz-filters')
router.register(r'questions', QuestionViewSet, basename='question')
router.register(r'choices', ChoiceViewSet, basename='choice')
router.register(r'', QuizViewSet, basename='quiz')

urlpatterns = [
    path('', include(router.urls)),
]
