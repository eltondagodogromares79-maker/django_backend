from django.contrib import admin
from .models import YearLevel


@admin.register(YearLevel)
class YearLevelAdmin(admin.ModelAdmin):
    list_display = ('name', 'order_number', 'program')
    list_filter = ('program',)
    search_fields = ('name', 'program__name')
    ordering = ('order_number',)
    list_per_page = 25
    autocomplete_fields = ('program',)
