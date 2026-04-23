from django.contrib import admin
from django.urls import path
from django.shortcuts import render
from users.models import CustomUser
from assignments.models import Assignment, AssignmentSubmission
from quizzes.models import Quiz
from subjects.models import Subject
from sections.models import Section, Enrollment


class CustomAdminSite(admin.AdminSite):
    site_header = "SCSIT E-Learning Administration"
    site_title = "SCSIT Admin"
    index_title = "Welcome to SCSIT E-Learning Administration"

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path("dashboard/", self.admin_view(self.dashboard_view), name="dashboard"),
        ]
        return custom_urls + urls

    def dashboard_view(self, request):
        stats = {
            "total_users": CustomUser.objects.count(),
            "students": CustomUser.objects.filter(role="student").count(),
            "instructors": CustomUser.objects.filter(role__in=["instructor", "adviser"]).count(),
            "admins": CustomUser.objects.filter(role__in=["admin", "principal", "dean"]).count(),
            "total_subjects": Subject.objects.count(),
            "total_sections": Section.objects.count(),
            "total_assignments": Assignment.objects.count(),
            "total_quizzes": Quiz.objects.count(),
            "pending_submissions": AssignmentSubmission.objects.filter(score__isnull=True).count(),
            "active_enrollments": Enrollment.objects.filter(status="enrolled").count(),
        }

        recent_assignments = Assignment.objects.order_by("-created_at")[:5]
        recent_submissions = AssignmentSubmission.objects.select_related("student", "assignment").order_by("-submitted_at")[:5]

        context = {
            "title": "Dashboard",
            "stats": stats,
            "recent_assignments": recent_assignments,
            "recent_submissions": recent_submissions,
        }

        return render(request, "admin/dashboard.html", context)


admin_site = CustomAdminSite(name="custom_admin")
