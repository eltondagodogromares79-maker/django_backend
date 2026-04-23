from django.contrib import admin
from .models import Department


@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    def get_head(self, obj):
        school_level = obj.school_level
        if school_level.name in ['Primary', 'Secondary']:
            principal = obj.principals.select_related('user').first()
            return principal.user.get_full_name() if principal else '-'
        else:
            dean = obj.deans.select_related('user').first()
            return dean.user.get_full_name() if dean else '-'
    get_head.short_description = 'Principal/Dean'

    list_display = ('name', 'school_level', 'get_head', 'created_at')
    list_filter = ('school_level', 'created_at')
    search_fields = ('name',)
    ordering = ('school_level', 'name')
    list_per_page = 20
    autocomplete_fields = ('school_level',)
    
    fieldsets = (
        ('Department', {
            'fields': ('name',)
        }),
        ('School Level', {
            'fields': ('school_level',)
        }),
    )
    
    readonly_fields = ('created_at',)
