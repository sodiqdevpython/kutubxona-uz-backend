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
    # Channels (ASGI + WebSocket) — 'daphne' runserver'ni ASGI qiladi
    'daphne',
    'channels',
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
    # Chiqib ketilgan (logout qilingan) refresh tokenlarni bekor qilish uchun
    'rest_framework_simplejwt.token_blacklist',
    # Local apps
    'apps.articles',
    'apps.authors',
    'apps.journals',
    'apps.comments',
    'apps.panel',
    'apps.chat',
    'apps.central_asia',
    'apps.partner',
]

MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
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
# Asosiy baza — PostgreSQL. Docker'da `db` servisi orqali ulanadi.
# Docker'siz lokal ishlash uchun DB_ENGINE=sqlite qo'yish kifoya.
def _database_config():
    """
    Ustuvorlik:
      1) DATABASE_URL  (postgres://user:pass@host:port/dbname)
      2) POSTGRES_* env o'zgaruvchilari
      3) DB_ENGINE=sqlite → lokal db.sqlite3
    """
    if os.environ.get('DB_ENGINE', 'postgres').lower() in ('sqlite', 'sqlite3'):
        return {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME':   BASE_DIR / 'db.sqlite3',
        }

    url = os.environ.get('DATABASE_URL', '').strip()
    if url and url.startswith(('postgres://', 'postgresql://')):
        from urllib.parse import urlparse, unquote
        u = urlparse(url)
        cfg = {
            'ENGINE':   'django.db.backends.postgresql',
            'NAME':     (u.path or '/postgres').lstrip('/'),
            'USER':     unquote(u.username or 'postgres'),
            'PASSWORD': unquote(u.password or ''),
            'HOST':     u.hostname or 'db',
            'PORT':     str(u.port or 5432),
        }
    else:
        cfg = {
            'ENGINE':   'django.db.backends.postgresql',
            'NAME':     os.environ.get('POSTGRES_DB',       'kutubxona'),
            'USER':     os.environ.get('POSTGRES_USER',     'kutubxona'),
            'PASSWORD': os.environ.get('POSTGRES_PASSWORD', 'kutubxona'),
            'HOST':     os.environ.get('POSTGRES_HOST',     'db'),
            'PORT':     os.environ.get('POSTGRES_PORT',     '5432'),
        }

    # Har bir so'rovda yangi ulanish ochilmasligi uchun — connection pooling
    cfg['CONN_MAX_AGE']      = int(os.environ.get('DB_CONN_MAX_AGE', 60))
    cfg['CONN_HEALTH_CHECKS'] = True
    cfg['OPTIONS'] = {'connect_timeout': 10}
    return cfg


DATABASES = {'default': _database_config()}

# ── Redis: kesh + Channels (WebSocket) uchun ──────────────────────────────────
# Oxiridagi '/' olib tashlanadi — pastda /1 (kesh) va /2 (channels) qo'shiladi
REDIS_URL = os.environ.get('REDIS_URL', 'redis://redis:6379').rstrip('/')

CACHES = {
    'default': {
        'BACKEND':  'django.core.cache.backends.redis.RedisCache',
        'LOCATION': f'{REDIS_URL}/1',
        'KEY_PREFIX': 'kutubxona',
        'TIMEOUT': int(os.environ.get('CACHE_TTL', 300)),   # standart 5 daqiqa
    }
}

# Redis yo'q bo'lsa (masalan, testlarda) — xotira keshiga tushamiz
if os.environ.get('DISABLE_REDIS') == '1':
    CACHES = {
        'default': {
            'BACKEND':  'django.core.cache.backends.locmem.LocMemCache',
            'LOCATION': 'kutubxona-locmem',
        }
    }

# Public API javoblari uchun kesh muddati (sekund)
API_CACHE_TTL = int(os.environ.get('API_CACHE_TTL', 120))

# ── Channels (WebSocket — real-time chat, polling o'rniga) ────────────────────
if os.environ.get('DISABLE_REDIS') == '1':
    CHANNEL_LAYERS = {
        'default': {'BACKEND': 'channels.layers.InMemoryChannelLayer'},
    }
else:
    CHANNEL_LAYERS = {
        'default': {
            'BACKEND': 'channels_redis.core.RedisChannelLayer',
            'CONFIG': {
                'hosts': [f'{REDIS_URL}/2'],
                'capacity': 1000,
                'expiry': 30,
            },
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

# WhiteNoise — admin panel static fayllarini Django o'zi (nginx'siz ham) beradi.
# Productionda manifest (hash'langan nomlar) ishlatiladi, DEBUG'da esa oddiy
# siqilgan storage — collectstatic qilinmagan bo'lsa ham xato bermaydi.
STORAGES = {
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {
        # Manifest (hash'langan nomlar) ATAYLAB ishlatilmaydi: serverdagi nginx /static/ ni
        # eski papkadan bersa hash'langan fayllar topilmaydi (DEBUG=False da admin CSS yo'qolgan).
        'BACKEND': 'whitenoise.storage.CompressedStaticFilesStorage',
    },
}
WHITENOISE_MAX_AGE = 60 * 60 * 24 * 30

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
    'DEFAULT_SCHEMA_CLASS': 'utils.schema.ProjectAutoSchema',
    # Tashqi hamkor API'si uchun so'rov cheklovi
    'DEFAULT_THROTTLE_CLASSES': [
        'rest_framework.throttling.ScopedRateThrottle',
    ],
    'DEFAULT_THROTTLE_RATES': {
        'partner':       os.environ.get('PARTNER_RATE_LIMIT',      '1000/hour'),
        'partner_token': os.environ.get('PARTNER_TOKEN_RATE_LIMIT', '30/hour'),
        # Izohlar — bitta IP ketma-ket spam qila olmasligi uchun
        'comment_burst': os.environ.get('COMMENT_BURST_LIMIT', '1/minute'),
        'comment':       os.environ.get('COMMENT_RATE_LIMIT',  '10/hour'),
        # Admin login — parol tanlashga qarshi
        'login':         os.environ.get('LOGIN_RATE_LIMIT',    '10/hour'),
    },
}

# ── SimpleJWT ─────────────────────────────────────────────────────────────────
from datetime import timedelta
SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME':  timedelta(
        hours=int(os.environ.get('ADMIN_ACCESS_LIFETIME_HOURS', 24))
    ),
    'REFRESH_TOKEN_LIFETIME': timedelta(
        days=int(os.environ.get('ADMIN_REFRESH_LIFETIME_DAYS', 30))
    ),
    'ROTATE_REFRESH_TOKENS':  True,
    # Eski refresh token rotatsiyadan keyin darhol bekor qilinadi
    'BLACKLIST_AFTER_ROTATION': True,
    'AUTH_HEADER_TYPES':      ('Bearer',),
}

# ── CAPTCHA (admin login himoyasi) ───────────────────────────────────────────
# Kalitlar bo'sh bo'lsa CAPTCHA o'chiq. Yoqish uchun .env ga qo'ying:
#   CAPTCHA_PROVIDER=turnstile        (turnstile | hcaptcha | recaptcha)
#   CAPTCHA_SITE_KEY=...
#   CAPTCHA_SECRET_KEY=...
CAPTCHA_PROVIDER   = os.environ.get('CAPTCHA_PROVIDER', 'turnstile').strip()
CAPTCHA_SITE_KEY   = os.environ.get('CAPTCHA_SITE_KEY', '').strip()
CAPTCHA_SECRET_KEY = os.environ.get('CAPTCHA_SECRET_KEY', '').strip()

# ── Hamkor (tashqi xizmat) API tokenlari ─────────────────────────────────────
PARTNER_ACCESS_LIFETIME  = timedelta(
    minutes=int(os.environ.get('PARTNER_ACCESS_LIFETIME_MIN', 60))
)
PARTNER_REFRESH_LIFETIME = timedelta(
    days=int(os.environ.get('PARTNER_REFRESH_LIFETIME_DAYS', 30))
)
# Hamkorga beriladigan bazaviy manzil (admin paneldagi token sahifasida ko'rinadi)
PARTNER_API_BASE_URL = os.environ.get('PARTNER_API_BASE_URL', '').strip()

# ── drf-spectacular ────────────────────────────────────────────────────────────
SPECTACULAR_SETTINGS = {
    'TITLE':       'Kutubxona.uz API',
    'DESCRIPTION': 'Kutubxona Arxivi — ilmiy maqolalar, mualliflar va jurnal sonlari API.',
    'VERSION':     '1.0.0',
    'SERVE_INCLUDE_SCHEMA': False,
    'TAGS': [
        {'name': 'Partner API',
         'description': "."},
    ],
    # Har bir chaqiruvda takrorlanadigan "unable to guess serializer" xabarlari
    # ProjectAutoSchema orqali bostirilgan (utils/schema.py).
    'ENUM_NAME_OVERRIDES': {},
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

# ── Reverse proxy / Cloudflare ────────────────────────────────────────────────
# nginx (va Cloudflare) HTTPS ni o'zi tugatadi, Django'ga HTTP kelib tushadi.
# Bu sozlama bo'lmasa `request.build_absolute_uri()` http:// li manzil yasaydi —
# media va hamkor API fayl havolalari buziladi.
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
USE_X_FORWARDED_HOST    = True
USE_X_FORWARDED_PORT    = True

if not DEBUG:
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE    = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    SECURE_REFERRER_POLICY = 'strict-origin-when-cross-origin'
    # HSTS ni nginx beradi (u yerda preload/subdomain boshqariladi)

# ── WebSocket origin ruxsati ─────────────────────────────────────────────────
# '*' — barcha originlar (dev). Productionda frontend domenini yozing:
#   WS_ALLOWED_ORIGINS=https://journalkutubxona.uz
WS_ALLOWED_ORIGINS = [
    o.strip()
    for o in os.environ.get('WS_ALLOWED_ORIGINS', '*').split(',') if o.strip()
]

DATA_UPLOAD_MAX_MEMORY_SIZE = 52428800  # 50 MB
FILE_UPLOAD_MAX_MEMORY_SIZE = 52428800  # 50 MB