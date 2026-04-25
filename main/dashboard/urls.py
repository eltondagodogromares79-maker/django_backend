from django.urls import path
from .views import DashboardStatsView, ProgressView, StudentPerformanceView, StudentPerformanceDetailView, PublicStatsView, TeacherStudentsView

urlpatterns = [
    path('stats/', DashboardStatsView.as_view(), name='dashboard-stats'),
    path('progress/', ProgressView.as_view(), name='dashboard-progress'),
    path('student-performance/', StudentPerformanceView.as_view(), name='student-performance'),
    path('student-performance/<uuid:student_id>/', StudentPerformanceDetailView.as_view(), name='student-performance-detail'),
    path('public-stats/', PublicStatsView.as_view(), name='public-stats'),
    path('teacher-students/', TeacherStudentsView.as_view(), name='teacher-students'),
]
