from django.urls import path, include
from main.routers import NoFormatSuffixRouter
from .views import AssignmentViewSet, AssignmentSubmissionViewSet

router = NoFormatSuffixRouter()
router.register(r'', AssignmentViewSet, basename='assignment')
router.register(r'submissions', AssignmentSubmissionViewSet, basename='assignmentsubmission')

urlpatterns = [
    path(
        'submissions/',
        AssignmentSubmissionViewSet.as_view({'get': 'list', 'post': 'create'}),
        name='assignment-submission-list',
    ),
    path(
        'submissions/<uuid:pk>/',
        AssignmentSubmissionViewSet.as_view({'get': 'retrieve', 'put': 'update', 'patch': 'partial_update', 'delete': 'destroy'}),
        name='assignment-submission-detail',
    ),
    path(
        'submissions/<uuid:pk>/grade/',
        AssignmentSubmissionViewSet.as_view({'patch': 'grade'}),
        name='assignment-submission-grade',
    ),
    path(
        'submissions/<uuid:pk>/ai-grade/',
        AssignmentSubmissionViewSet.as_view({'post': 'ai_grade'}),
        name='assignment-submission-ai-grade',
    ),
    path('', include(router.urls)),
]

# URL Patterns and Permissions:
# 
# GET /api/assignments/ - List assignments
#   - Students: See published assignments for enrolled sections
#   - Teachers: See their own assignments
#   - Admin/Principal: See all assignments
#
# POST /api/assignments/ - Create assignment
#   - Teachers, Admin, Principal only
#
# GET /api/assignments/{id}/ - Retrieve assignment
#   - Students, Teachers, Admin, Principal (with filtering)
#
# PUT/PATCH /api/assignments/{id}/ - Update assignment
#   - Teachers (own assignments), Admin, Principal only
#
# DELETE /api/assignments/{id}/ - Delete assignment
#   - Teachers (own assignments), Admin, Principal only
#
# GET /api/assignments/{id}/submissions/ - Get assignment submissions
#   - Students: See only their own submission
#   - Teachers: See all submissions for their assignments
#   - Admin/Principal: See all submissions
#
# GET /api/submissions/ - List submissions
#   - Students: See only their own submissions
#   - Teachers: See submissions for their assignments
#   - Admin/Principal: See all submissions
#
# POST /api/submissions/ - Create submission
#   - Students only
#
# GET /api/submissions/{id}/ - Retrieve submission
#   - Students: Own submissions only
#   - Teachers: Submissions for their assignments
#   - Admin/Principal: All submissions
#
# PUT/PATCH /api/submissions/{id}/ - Update submission
#   - Students: Own ungraded submissions only
#   - Teachers: Can grade submissions for their assignments
#   - Admin/Principal: All submissions
#
# DELETE /api/submissions/{id}/ - Delete submission
#   - Admin/Principal only
#
# PATCH /api/submissions/{id}/grade/ - Grade submission
#   - Teachers: For their assignments only
#   - Admin/Principal: All submissions
