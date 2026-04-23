from rest_framework.routers import DefaultRouter

class NoFormatSuffixRouter(DefaultRouter):
    """Router that doesn't add format suffix patterns to avoid converter conflicts"""
    
    def get_urls(self):
        """Override to skip format_suffix_patterns"""
        urls = super(DefaultRouter, self).get_urls()
        return urls
