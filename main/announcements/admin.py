from django.contrib import admin
from .models import Announcement


@admin.register(Announcement)
class AnnouncementAdmin(admin.ModelAdmin):
    list_display = ('title', 'section_subject', 'created_at')
    list_filter = ('created_at',)
    search_fields = ('title', 'message', 'section_subject__subject__code')
    ordering = ('-created_at',)
    list_per_page = 25
    autocomplete_fields = ('section_subject',)
