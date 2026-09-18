import os

from django.contrib import admin
from django.urls import path, re_path, include
from django.conf import settings
from django.conf.urls.static import static
from django.views.generic import RedirectView
from django.views.static import serve as static_serve
from django.contrib.auth.decorators import login_required
from django.views.decorators.clickjacking import xframe_options_exempt
from rest_framework.routers import DefaultRouter
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularSwaggerView,
    SpectacularRedocView,
)

from apps.articles.views  import (
    CategoryViewSet, ArticleViewSet,
    SubmissionDraftView, SubmissionFinalizeView, SubmissionCancelDraftView,
    BotCheckAdminView, BotUserArticlesView, AiStatusView,
)
from apps.authors.views   import AuthorViewSet
from apps.panel.views    import CaptchaConfigView
from apps.journals.views  import JournalViewSet, IssueViewSet
from apps.comments.views  import CommentViewSet

# ── Admin ─────────────────────────────────────────────────────────────────────
admin.site.site_header = 'Kutubxona Arxivi — Boshqaruv'
admin.site.site_title  = 'Kutubxona Arxivi'
admin.site.index_title = 'Boshqaruv paneli'

# ── API router ────────────────────────────────────────────────────────────────
router = DefaultRouter()
router.register('articles',   ArticleViewSet,  basename='article')
router.register('categories', CategoryViewSet, basename='category')
router.register('authors',    AuthorViewSet,   basename='author')
router.register('journals',   JournalViewSet,  basename='journal')
router.register('issues',     IssueViewSet,    basename='issue')
router.register('comments',   CommentViewSet,  basename='comment')

# ── URL patterns ──────────────────────────────────────────────────────────────
urlpatterns = [
    # Root → Swagger
    path('', RedirectView.as_view(url='/api/docs/', permanent=False)),

    # Admin panel
    path('admin/', admin.site.urls),

    # REST API (router)
    path('api/', include(router.urls)),

    # Local AI holati (frontend "AI ulanmagan" modalini shu bilan boshqaradi)
    path('api/ai/status/', AiStatusView.as_view(), name='ai-status'),

    # CAPTCHA sozlamasi (login sahifasi uchun)
    path('api/auth/captcha/', CaptchaConfigView.as_view(), name='captcha-config'),

    # Bot submission endpointlari (secret orqali himoyalangan)
    path('api/submit/draft/',         SubmissionDraftView.as_view(),       name='submit-draft'),
    path('api/submit/finalize/',      SubmissionFinalizeView.as_view(),    name='submit-finalize'),
    path('api/submit/cancel/',        SubmissionCancelDraftView.as_view(), name='submit-cancel'),
    path('api/submit/check-admin/',   BotCheckAdminView.as_view(),         name='submit-check-admin'),
    path('api/submit/user-articles/', BotUserArticlesView.as_view(),       name='submit-user-articles'),

    # Admin panel API (SimpleJWT himoyasi)
    path('api/admin/', include('apps.panel.urls')),

    # Chat (admin + bot)
    path('api/', include('apps.chat.urls')),

    # Central Asia (einfolib.uz'dan parse qilinadi)
    path('api/', include('apps.central_asia.urls')),

    # Hamkor API (tashqi xizmatlar — access/refresh token bilan)
    path('api/partner/', include('apps.partner.urls')),

    # OpenAPI schema + interaktiv hujjatlar.
    # DIQQAT: faqat tizimga kirgan (admin panelga login qilgan) foydalanuvchilar
    # ko'ra oladi — aks holda /admin/login/ ga yo'naltiriladi.
    path('api/schema/',
         login_required(SpectacularAPIView.as_view(), login_url='/admin/login/'),
         name='schema'),
    path('api/docs/',
         login_required(SpectacularSwaggerView.as_view(url_name='schema'), login_url='/admin/login/'),
         name='swagger-ui'),
    path('api/redoc/',
         login_required(SpectacularRedocView.as_view(url_name='schema'), login_url='/admin/login/'),
         name='redoc'),
]

# ── Media fayllar ─────────────────────────────────────────────────────────────
# Docker'da /media/ so'rovlarini nginx to'g'ridan-to'g'ri diskdan beradi va
# bu yo'lgacha yetib kelmaydi. Ammo backend'ga to'g'ridan-to'g'ri murojaat
# qilinganda (masalan, :8000 dagi Swagger yoki admin panel) fayllar
# ochilishi kerak — shuning uchun DEBUG'dan qat'i nazar xizmat qilamiz.
# O'chirish uchun: SERVE_MEDIA=0
if os.environ.get('SERVE_MEDIA', '1') == '1':
    # iframe da PDF ko'rsatish uchun X-Frame-Options ni o'chiramiz
    media_url = settings.MEDIA_URL.lstrip('/')
    urlpatterns += [
        re_path(
            rf'^{media_url}(?P<path>.*)$',
            xframe_options_exempt(static_serve),
            {'document_root': settings.MEDIA_ROOT},
        ),
    ]

if settings.DEBUG:
    # Static — o'zgartirilmasdan (productionda WhiteNoise beradi)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
