from pathlib import Path
import os
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.environ.get(
    'SECRET_KEY',
    'django-insecure-kutubxona-dev-key-change-in-production'
)

DEBUG = os.environ.get('DEBUG', 'True') == 'True'

ALLOWED_HOSTS = os.environ.get('ALLOWED_HOSTS', '*').split(',')

# ── Applications ──────────────────────────────────────────────────────────────
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    # Third-party
    'rest_framework',
    'corsheaders',
    'django_filters',
    'drf_spectacular',
    # Local apps
    'apps.articles',
    'apps.authors',
    'apps.journals',
    'apps.comments',
    'apps.panel',
    'apps.chat',
]

MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'
ASGI_APPLICATION = 'config.asgi.application'

# ── Database ──────────────────────────────────────────────────────────────────
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

# ── Password validators ───────────────────────────────────────────────────────
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# ── Internationalisation ──────────────────────────────────────────────────────
LANGUAGE_CODE = 'uz'
TIME_ZONE = 'Asia/Tashkent'
USE_I18N = True
USE_TZ = True

# ── Static & media ────────────────────────────────────────────────────────────
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# ── Django REST Framework ─────────────────────────────────────────────────────
REST_FRAMEWORK = {
    'DEFAULT_FILTER_BACKENDS': [
        'django_filters.rest_framework.DjangoFilterBackend',
        'rest_framework.filters.SearchFilter',
        'rest_framework.filters.OrderingFilter',
    ],
    'DEFAULT_PAGINATION_CLASS': 'utils.pagination.StandardPagination',
    'PAGE_SIZE': 20,
    'DEFAULT_RENDERER_CLASSES': [
        'rest_framework.renderers.JSONRenderer',
    ],
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ],
    'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',
}

# ── SimpleJWT ─────────────────────────────────────────────────────────────────
from datetime import timedelta
SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME':  timedelta(hours=24),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=30),
    'ROTATE_REFRESH_TOKENS':  True,
    'AUTH_HEADER_TYPES':      ('Bearer',),
}

# ── drf-spectacular ────────────────────────────────────────────────────────────
SPECTACULAR_SETTINGS = {
    'TITLE':       'Kutubxona.uz API',
    'DESCRIPTION': 'Kutubxona Arxivi — ilmiy maqolalar, mualliflar va jurnal sonlari API.',
    'VERSION':     '1.0.0',
    'SERVE_INCLUDE_SCHEMA': False,
}

# ── Telegram Bot ─────────────────────────────────────────────────────────────
TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN', '')
TELEGRAM_ADMIN_IDS = [
    int(x) for x in os.environ.get('TELEGRAM_ADMIN_IDS', '').split(',') if x.strip()
]
BOT_SECRET = os.environ.get('BOT_SECRET', 'kutubxona-bot-secret-change-me')

# ── Sayt manzili (Telegram link xabarlari uchun) ──────────────────────────────
SITE_URL = os.environ.get('SITE_URL', 'http://localhost:5173')

# ── Gemini AI (eski, hozir ishlatilmayapti) ───────────────────────────────────
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY', '')
GEMINI_MODEL   = os.environ.get('GEMINI_MODEL', 'gemini-flash-latest')

# ── Local LLM (Ollama) — AI extract uchun ─────────────────────────────────────
LOCAL_LLM_BASE_URL = os.environ.get('LOCAL_LLM_BASE_URL', 'https://sodiqdevpython.jprq.live')

# ── CORS ──────────────────────────────────────────────────────────────────────
if DEBUG:
    CORS_ALLOW_ALL_ORIGINS = True
else:
    CORS_ALLOWED_ORIGINS = [
        o.strip()
        for o in os.environ.get(
            'CORS_ALLOWED_ORIGINS',
            'https://journalkutubxona.uz,https://www.journalkutubxona.uz'
        ).split(',') if o.strip()
    ]
    # JWT token bilan ishlatish uchun
    CORS_ALLOW_CREDENTIALS = True
    CORS_ALLOW_HEADERS = [
        'accept', 'accept-encoding', 'authorization', 'content-type',
        'dnt', 'origin', 'user-agent', 'x-csrftoken', 'x-requested-with',
    ]
    CORS_ALLOW_METHODS = ['DELETE', 'GET', 'OPTIONS', 'PATCH', 'POST', 'PUT']

# ── CSRF (production) ────────────────────────────────────────────────────────
# Django 4+ — POST/PATCH'lar uchun frontend domeni CSRF_TRUSTED_ORIGINS'da bo'lishi shart
CSRF_TRUSTED_ORIGINS = [
    o.strip()
    for o in os.environ.get(
        'CSRF_TRUSTED_ORIGINS',
        'https://journalkutubxona.uz,https://www.journalkutubxona.uz,https://api.journalkutubxona.uz'
    ).split(',') if o.strip()
]

# CSRF sozlamalari
CSRF_TRUSTED_ORIGINS = [
    o.strip()
    for o in os.environ.get(
        'CSRF_TRUSTED_ORIGINS',
        'https://journalkutubxona.uz,https://www.journalkutubxona.uz,https://api.journalkutubxona.uz'
    ).split(',')
]

DATA_UPLOAD_MAX_MEMORY_SIZE = 52428800  # 50 MB
FILE_UPLOAD_MAX_MEMORY_SIZE = 52428800  # 50 MB