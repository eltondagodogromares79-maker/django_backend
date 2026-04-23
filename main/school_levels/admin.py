from django.contrib import admin
from .models import SchoolLevel, SchoolYear, Term


@admin.register(SchoolLevel)
class SchoolLevelAdmin(admin.ModelAdmin):
    list_display = ('name', 'created_at')
    search_fields = ('name',)
    ordering = ('name',)
    list_per_page = 25
    readonly_fields = ('created_at',)


@admin.register(SchoolYear)
class SchoolYearAdmin(admin.ModelAdmin):
    list_display = ('name', 'start_date', 'end_date', 'is_active', 'created_at')
    list_filter = ('is_active',)
    search_fields = ('name',)
    ordering = ('-start_date',)
    list_per_page = 25
    readonly_fields = ('created_at',)


@admin.register(Term)
class TermAdmin(admin.ModelAdmin):
    list_display = ('semester', 'school_year', 'start_date', 'end_date', 'created_at')
    list_filter = ('school_year', 'semester')
    search_fields = ('school_year__name',)
    ordering = ('school_year', 'semester')
    list_per_page = 25
    readonly_fields = ('created_at',)
