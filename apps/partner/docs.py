"""
Hamkorlar uchun hujjat sahifasi — `/api/partner/docs/`.

Hamkor `client_id` (login) + `client_secret` (parol) bilan kiradi. Sahifada:
  • tepada shu hamkor uchun yangi access/refresh (nusxalash uchun),
  • pastda drf-spectacular Swagger UI — faqat 3 ta hamkor endpointi
    (ro'yxat, maqola, access yangilash); «Try it out» avtomatik shu access
    token bilan ishlaydi.

Sessiya oddiy Django sessiyasi; hamkor o'chirilsa yoki tokenlari bekor
qilinsa sessiya ham tugaydi. Kirish sahifasida CAPTCHA (`.env` dagi
CAPTCHA_* kalitlari) — admin login bilan bir xil sozlama.
"""
from django.conf import settings
from django.core.cache import cache
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.cache import never_cache
from drf_spectacular.views import SpectacularAPIView
from rest_framework.permissions import BasePermission

from utils import captcha
from utils.request_ip import client_ip

from .models import PartnerClient
from .tokens import issue_pair
from .utils import partner_api_base

SESSION_KEY    = 'partner_docs_client'      # PartnerClient.pk
SESSION_TV     = 'partner_docs_tv'          # kirish paytidagi token_version
LOGIN_ATTEMPTS = 10                         # bitta IP dan 10 daqiqada
LOGIN_WINDOW   = 600

# Swagger'da ko'rinadigan yo'llar — boshqasi chiqmaydi
DOCS_PATHS = {
    '/api/partner/articles/',
    '/api/partner/articles/{id}/',
    '/api/partner/auth/refresh/',
}


def _current_client(request) -> PartnerClient | None:
    """Sessiyadagi hamkor; o'chirilgan yoki tokenlari bekor qilingan bo'lsa — None."""
    pk = request.session.get(SESSION_KEY)
    if not pk:
        return None
    try:
        client = PartnerClient.objects.get(pk=pk, is_active=True)
    except (PartnerClient.DoesNotExist, ValueError):
        return None
    if int(request.session.get(SESSION_TV) or 0) != int(client.token_version or 1):
        return None
    return client


# ── Kirish / chiqish ─────────────────────────────────────────────────────────

@method_decorator(never_cache, name='dispatch')
class PartnerDocsLoginView(View):
    template_name = 'partner/docs_login.html'

    def _render(self, request, status=200, **extra):
        return render(request, self.template_name, {
            'captcha': captcha.public_config(),
            'error':   None,
            **extra,
        }, status=status)

    def get(self, request):
        if _current_client(request):
            return redirect('partner-docs')
        return self._render(request)

    def post(self, request):
        ip  = client_ip(request)
        key = f'partner-docs-login:{ip}'
        if cache.get(key, 0) >= LOGIN_ATTEMPTS:
            return self._render(request, 429, error="Urinishlar ko'p. 10 daqiqadan keyin qayta urinib ko'ring.")

        client_id = (request.POST.get('client_id') or '').strip()

        # CAPTCHA (yoqilgan bo'lsa) — parolni tekshirishdan oldin
        if captcha.is_enabled():
            field = captcha.public_config()['response_field']
            ok, _code = captcha.verify(request.POST.get(field, ''), ip)
            if not ok:
                cache.set(key, cache.get(key, 0) + 1, LOGIN_WINDOW)
                return self._render(request, 400, error="Tekshiruvdan o'tmadingiz. Qaytadan urinib ko'ring.",
                                    client_id=client_id)

        secret = request.POST.get('client_secret') or ''
        client = PartnerClient.objects.filter(client_id=client_id, is_active=True).first()
        if not client or not client.check_secret(secret):
            cache.set(key, cache.get(key, 0) + 1, LOGIN_WINDOW)
            return self._render(request, 401, error="login yoki parol noto'g'ri.", client_id=client_id)

        cache.delete(key)
        request.session.cycle_key()
        request.session[SESSION_KEY] = str(client.pk)
        request.session[SESSION_TV]  = int(client.token_version or 1)
        request.session.set_expiry(12 * 3600)      # 12 soat
        return redirect('partner-docs')


class PartnerDocsLogoutView(View):
    def post(self, request):
        request.session.flush()
        return redirect('partner-docs-login')

    get = post


# ── Hujjat sahifasi ──────────────────────────────────────────────────────────

@method_decorator(never_cache, name='dispatch')
class PartnerDocsView(View):
    template_name = 'partner/docs.html'

    def get(self, request):
        client = _current_client(request)
        if not client:
            request.session.flush()
            return redirect('partner-docs-login')

        return render(request, self.template_name, {
            'client':       client,
            'tokens':       issue_pair(client),
            'api_base':     partner_api_base(request),
            'schema_url':   reverse('partner-schema'),
            'logout_url':   reverse('partner-docs-logout'),
            'access_hours': round(settings.PARTNER_ACCESS_LIFETIME.total_seconds() / 3600, 1),
            'refresh_days': settings.PARTNER_REFRESH_LIFETIME.days,
        })


# ── OpenAPI sxemasi — faqat 3 ta hamkor endpointi ────────────────────────────

class PartnerDocsSession(BasePermission):
    """Sxema faqat docs sahifasiga kirgan hamkorga beriladi."""
    def has_permission(self, request, view):
        return _current_client(request) is not None


def keep_docs_paths(endpoints, **kwargs):
    """drf-spectacular preprocessing hook — DOCS_PATHS dan boshqasini tashlab yuboradi."""
    return [e for e in endpoints if e[0] in DOCS_PATHS]


class PartnerSchemaView(SpectacularAPIView):
    authentication_classes = []
    permission_classes     = [PartnerDocsSession]
    urlconf                = 'apps.partner.docs_urlconf'
    serve_include_schema   = False
    custom_settings = {
        'TITLE':       'Kutubxona.uz — Partner API',
        'DESCRIPTION': (
            ""
        ),
        'VERSION':             '1.0',
        'SCHEMA_PATH_PREFIX':  '/api/partner',
        'PREPROCESSING_HOOKS': ['apps.partner.docs.keep_docs_paths'],
    }
