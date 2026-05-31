from django.contrib import admin
from django.urls import path, re_path, include
from django.conf import settings
from django.conf.urls.static import static
from django.views.generic import RedirectView
from django.views.static import serve as static_serve
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
    BotCheckAdminView, BotUserArticlesView,
)
from apps.authors.views   import AuthorViewSet
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

    # OpenAPI schema + interactive docs
    path('api/schema/',  SpectacularAPIView.as_view(),                       name='schema'),
    path('api/docs/',    SpectacularSwaggerView.as_view(url_name='schema'),  name='swagger-ui'),
    path('api/redoc/',   SpectacularRedocView.as_view(url_name='schema'),    name='redoc'),
]

if settings.DEBUG:
    # ── Media: iframe da PDF ko'rsatish uchun X-Frame-Options ni o'chiramiz ──
    media_url = settings.MEDIA_URL.lstrip('/')
    urlpatterns += [
        re_path(
            rf'^{media_url}(?P<path>.*)$',
            xframe_options_exempt(static_serve),
            {'document_root': settings.MEDIA_ROOT},
        ),
    ]
    # Static — o'zgartirilmasdan
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
