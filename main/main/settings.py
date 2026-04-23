from pathlib import Path
import os
from dotenv import load_dotenv
import dj_database_url

# ─────────────────────────────────────────────
# Base
# ─────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(os.path.join(BASE_DIR.parent, '.env'))

SECRET_KEY = os.getenv('DJANGO_SECRET_KEY', 'django-insecure-change-me-in-production')
DEBUG = os.getenv('DEBUG', 'true').lower() == 'true'

# ─────────────────────────────────────────────
# Hosts & CORS  — driven entirely from .env
# ALLOWED_HOSTS  = comma-separated hostnames   e.g. localhost,your-app.onrender.com
# FRONTEND_URLS  = comma-separated full URLs   e.g. http://localhost:3000,https://your-app.vercel.app
# ─────────────────────────────────────────────
def _split(value: str | None) -> list[str]:
    return [v.strip() for v in (value or '').split(',') if v.strip()]

FRONTEND_URLS = _split(os.getenv('FRONTEND_URLS'))

ALLOWED_HOSTS = _split(os.getenv('ALLOWED_HOSTS'))
# Render automatically injects RENDER_EXTERNAL_HOSTNAME — include it if present
_render_host = os.getenv('RENDER_EXTERNAL_HOSTNAME')
if _render_host and _render_host not in ALLOWED_HOSTS:
    ALLOWED_HOSTS.append(_render_host)
if DEBUG and not ALLOWED_HOSTS:
    ALLOWED_HOSTS = ['*']

# CORS — frontend URLs + any extra origins (e.g. chat server)
_extra_cors = _split(os.getenv('EXTRA_CORS_URLS'))
CORS_ALLOWED_ORIGINS = list(dict.fromkeys(FRONTEND_URLS + _extra_cors))
CORS_ALLOW_CREDENTIALS = True
CORS_ALLOW_HEADERS = [
    'accept',
    'accept-encoding',
    'authorization',
    'content-type',
    'dnt',
    'origin',
    'user-agent',
    'x-csrftoken',
    'x-requested-with',
]

CSRF_TRUSTED_ORIGINS = _split(os.getenv('CSRF_TRUSTED_ORIGINS')) or FRONTEND_URLS

# ─────────────────────────────────────────────
# Installed apps
# ─────────────────────────────────────────────
INSTALLED_APPS = [
    'daphne',
    'django.contrib.admin',
    'django.contrib.auth',
    'rest_framework_simplejwt.token_blacklist',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'rest_framework',
    'corsheaders',
    'channels',
    'cloudinary',
    'cloudinary_storage',
    'users',
    'departments',
    'year_levels',
    'sections',
    'subjects',
    'learning_materials',
    'assignments',
    'quizzes',
    'school_levels',
    'programs',
    'announcements',
    'chat',
    'notifications',
    'dashboard',
    'attendance',
]

# ─────────────────────────────────────────────
# Middleware
# ─────────────────────────────────────────────
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'main.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'main.wsgi.application'
ASGI_APPLICATION = 'main.asgi.application'

# ─────────────────────────────────────────────
# Channels
# ─────────────────────────────────────────────
CHANNEL_LAYERS = {
    'default': {
        'BACKEND': 'channels.layers.InMemoryChannelLayer',
    }
}

# ─────────────────────────────────────────────
# REST Framework
# ─────────────────────────────────────────────
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'users.authentication.CookieJWTAuthentication',
    ),
    'DEFAULT_PERMISSION_CLASSES': (
        'rest_framework.permissions.IsAuthenticated',
    ),
    'DEFAULT_THROTTLE_CLASSES': (
        'rest_framework.throttling.UserRateThrottle',
        'rest_framework.throttling.AnonRateThrottle',
    ),
    'DEFAULT_THROTTLE_RATES': {
        'user': '300/min',
        'anon': '60/min',
    },
}

# ─────────────────────────────────────────────
# Database
# ─────────────────────────────────────────────
DATABASE_TARGET = os.getenv('DATABASE_TARGET', 'local').lower()
REMOTE_DATABASE_URL = os.getenv('REMOTE_DATABASE_URL') or os.getenv('DATABASE_URL')

if DATABASE_TARGET in {'remote', 'online', 'render', 'production'} and REMOTE_DATABASE_URL:
    DATABASES = {
        'default': dj_database_url.config(
            default=REMOTE_DATABASE_URL,
            conn_max_age=int(os.getenv('DB_CONN_MAX_AGE', '600')),
            ssl_require=os.getenv('DB_SSL_REQUIRE', 'true').lower() == 'true',
        )
    }
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.postgresql',
            'NAME': os.getenv('DB_NAME', 'capstone_db'),
            'USER': os.getenv('DB_USER', 'postgres'),
            'PASSWORD': os.getenv('DB_PASSWORD', 'postgres'),
            'HOST': os.getenv('DB_HOST', 'localhost'),
            'PORT': os.getenv('DB_PORT', '5432'),
        }
    }

# ─────────────────────────────────────────────
# Password validation
# ─────────────────────────────────────────────
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

AUTH_USER_MODEL = 'users.CustomUser'

# ─────────────────────────────────────────────
# Internationalisation
# ─────────────────────────────────────────────
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

# ─────────────────────────────────────────────
# Static & media files
# ─────────────────────────────────────────────
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
MEDIA_URL = '/media/'
MEDIA_ROOT = os.path.join(BASE_DIR, 'media')

CLOUDINARY_CLOUD_NAME = os.getenv('CLOUDINARY_CLOUD_NAME', '')
CLOUDINARY_API_KEY    = os.getenv('CLOUDINARY_API_KEY', '')
CLOUDINARY_API_SECRET = os.getenv('CLOUDINARY_API_SECRET', '')

if CLOUDINARY_CLOUD_NAME and CLOUDINARY_API_KEY and CLOUDINARY_API_SECRET:
    CLOUDINARY_STORAGE = {
        'CLOUD_NAME': CLOUDINARY_CLOUD_NAME,
        'API_KEY':    CLOUDINARY_API_KEY,
        'API_SECRET': CLOUDINARY_API_SECRET,
        'SECURE': True,
        'RESOURCE_TYPE': 'auto',
    }
    STORAGES = {
        'default':    {'BACKEND': 'cloudinary_storage.storage.MediaCloudinaryStorage'},
        'staticfiles': {'BACKEND': 'whitenoise.storage.CompressedManifestStaticFilesStorage'},
    }
else:
    STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

# ─────────────────────────────────────────────
# Security
# ─────────────────────────────────────────────
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = 'DENY'
REFERRER_POLICY = 'same-origin'
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

SECURE_SSL_REDIRECT          = not DEBUG
SESSION_COOKIE_SECURE        = not DEBUG
CSRF_COOKIE_SECURE           = not DEBUG
SECURE_HSTS_SECONDS          = 0 if DEBUG else int(os.getenv('SECURE_HSTS_SECONDS', '3600'))
SECURE_HSTS_INCLUDE_SUBDOMAINS = not DEBUG
SECURE_HSTS_PRELOAD            = not DEBUG

# ─────────────────────────────────────────────
# Chat server
# ─────────────────────────────────────────────
CHAT_SERVER_TARGET          = os.getenv('CHAT_SERVER_TARGET', 'local').lower()
CHAT_SERVER_TOKEN           = os.getenv('CHAT_SERVER_TOKEN', '')
_chat_remote                = os.getenv('CHAT_SERVER_HTTP_REMOTE_URL', 'https://chat-server-2h01.onrender.com')
_chat_local                 = os.getenv('CHAT_SERVER_HTTP_LOCAL_URL',  'http://127.0.0.1:8080')
_chat_ws_remote             = os.getenv('CHAT_SERVER_WS_REMOTE_URL',   'wss://chat-server-2h01.onrender.com/ws/chat/')
_chat_ws_local              = os.getenv('CHAT_SERVER_WS_LOCAL_URL',    'ws://127.0.0.1:8080/ws/chat/')
_is_remote                  = CHAT_SERVER_TARGET in {'remote', 'online', 'render', 'production'}
CHAT_SERVER_HTTP_URL        = _chat_remote if _is_remote else _chat_local
CHAT_SERVER_WS_URL          = _chat_ws_remote if _is_remote else _chat_ws_local

# ─────────────────────────────────────────────
# Jitsi & Attendance
# ─────────────────────────────────────────────
JITSI_BASE_URL              = os.getenv('JITSI_BASE_URL', 'https://meet.jit.si')
ATTENDANCE_LATE_AFTER_MINUTES = int(os.getenv('ATTENDANCE_LATE_AFTER_MINUTES', '10'))

# ─────────────────────────────────────────────
# AI grading
# ─────────────────────────────────────────────
GEMINI_API_KEY  = os.getenv('GEMINI_API_KEY', '')
GEMINI_MODEL    = os.getenv('GEMINI_MODEL', 'gemini-1.5-flash')
GEMINI_API_BASE = os.getenv('GEMINI_API_BASE', 'https://generativelanguage.googleapis.com/v1beta')

OPENAI_API_KEY  = os.getenv('OPENAI_API_KEY', '')
OPENAI_MODEL    = os.getenv('OPENAI_MODEL', 'gpt-4.1-mini')
OPENAI_API_BASE = os.getenv('OPENAI_API_BASE', 'https://api.openai.com/v1')

# ─────────────────────────────────────────────
# PDF generation
# ─────────────────────────────────────────────
PDF_LOGO_PATH        = os.getenv('PDF_LOGO_PATH', '')
PDF_HEADER_TEXT      = os.getenv('PDF_HEADER_TEXT', 'Learning Materials Pack')
PDF_FOOTER_TEXT      = os.getenv('PDF_FOOTER_TEXT', 'Generated by AI learning materials assistant')
PDF_FILENAME_TEMPLATE = os.getenv('PDF_FILENAME_TEMPLATE', '{subject}-{title}-{date}.pdf')

# ─────────────────────────────────────────────
# Email (SMTP)
# ─────────────────────────────────────────────
EMAIL_BACKEND      = os.getenv('EMAIL_BACKEND', 'django.core.mail.backends.smtp.EmailBackend')
EMAIL_HOST         = os.getenv('EMAIL_HOST', '')
EMAIL_PORT         = int(os.getenv('EMAIL_PORT', '587'))
EMAIL_HOST_USER    = os.getenv('EMAIL_HOST_USER', '')
EMAIL_HOST_PASSWORD = os.getenv('EMAIL_HOST_PASSWORD', '')
EMAIL_USE_TLS      = os.getenv('EMAIL_USE_TLS', 'true').lower() == 'true'
EMAIL_USE_SSL      = os.getenv('EMAIL_USE_SSL', 'false').lower() == 'true'
DEFAULT_FROM_EMAIL = os.getenv('DEFAULT_FROM_EMAIL', 'SCSIT NEXUS <no-reply@scsitnexus.local>')
