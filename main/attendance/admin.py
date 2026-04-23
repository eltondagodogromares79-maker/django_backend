from django.contrib import admin
from .models import AttendanceSession, AttendanceRecord


@admin.register(AttendanceSession)
class AttendanceSessionAdmin(admin.ModelAdmin):
    list_display = ('id', 'section', 'section_subject', 'scheduled_at', 'created_by')
    search_fields = ('section__name', 'section_subject__subject__name')
    list_filter = ('section', 'section_subject')


@admin.register(AttendanceRecord)
class AttendanceRecordAdmin(admin.ModelAdmin):
    list_display = ('session', 'student', 'status', 'marked_at')
    search_fields = ('student__user__first_name', 'student__user__last_name', 'student__student_number')
    list_filter = ('status',)
