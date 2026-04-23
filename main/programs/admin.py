from django.contrib import admin
from .models import Program


@admin.register(Program)
class ProgramAdmin(admin.ModelAdmin):
    def get_adviser(self, obj):
        adviser = getattr(obj, 'adviser', None)
        return adviser.user.get_full_name() if adviser else '-'
    get_adviser.short_description = 'Adviser'

    def get_principal(self, obj):
        school_level = obj.department.school_level
        if school_level.name in ['Primary', 'Secondary']:
            principal = obj.department.principals.select_related('user').first()
            return principal.user.get_full_name() if principal else '-'
        else:
            dean = obj.department.deans.select_related('user').first()
            return dean.user.get_full_name() if dean else '-'
    get_principal.short_description = 'Principal/Dean'

    list_display = ('name', 'type', 'department', 'get_adviser', 'get_principal', 'created_at')
    list_filter = ('department',)
    search_fields = ('name', 'department__name')
    ordering = ('department', 'name')
    list_per_page = 25
    autocomplete_fields = ('department',)
    fieldsets = (
        (None, {'fields': ('name', 'type', 'department')}),
    )
    readonly_fields = ('created_at',)
