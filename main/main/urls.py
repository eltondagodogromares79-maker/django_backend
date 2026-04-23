
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from rest_framework_simplejwt.views import ( # type: ignore
    TokenObtainPairView,
    TokenRefreshView,
)
from learning_materials.views import cloudinary_healthcheck

urlpatterns = [
    path('admin/', admin.site.urls),

    path('api/health/cloudinary/', cloudinary_healthcheck, name='cloudinary-healthcheck'),
    path('api/users/', include('users.urls')),
    path('api/departments/', include('departments.urls')),
    path('api/school-levels/', include('school_levels.urls')),
    path('api/programs/', include('programs.urls')),
    path('api/year-levels/', include('year_levels.urls')),
    path('api/sections/', include('sections.urls')),
    path('api/subjects/', include('subjects.urls')),
    path('api/learning-materials/', include('learning_materials.urls')),
    path('api/assignments/', include('assignments.urls')),
    path('api/quizzes/', include('quizzes.urls')),
    path('api/announcements/', include('announcements.urls')),
    path('api/notifications/', include('notifications.urls')),
    path('api/attendance/', include('attendance.urls')),
    path('api/dashboard/', include('dashboard.urls')),
    path('api/chat/', include('chat.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
