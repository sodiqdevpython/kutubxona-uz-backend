"""
Hamkorlar uchun alohida hujjat sahifasi — `/api/partner/docs/`.

Faqat hamkor endpointlari ko'rinadigan Swagger UI. Kirish uchun hamkorning
mavjud `client_id` + `client_secret` juftligi ishlatiladi (alohida Django
foydalanuvchisi yo'q). Kirgach:
  • yangi access + refresh tokenlar ko'rsatiladi (nusxalash uchun),
  • Swagger avtomatik shu access bilan avtorizatsiya qilinadi — «Try it out»
    darhol ishlaydi.

Sessiya oddiy Django sessiyasi; hamkor o'chirilsa yoki tokenlari bekor
qilinsa sessiya ham tugaydi.
"""
from django.conf import settings
from django.contrib import messages
from django.core.cache import cache
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.cache import never_cache
from drf_spectacular.views import SpectacularAPIView
from rest_framework.permissions import BasePermission

from utils.request_ip import client_ip

from .models import PartnerClient
from .tokens import issue_pair
from .utils import partner_api_base

SESSION_KEY    = 'partner_docs_client'      # PartnerClient.pk
SESSION_TV     = 'partner_docs_tv'          # kirish paytidagi token_version
LOGIN_ATTEMPTS = 10                         # bitta IP dan 10 daqiqada
LOGIN_WINDOW   = 600


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


def _urls(request) -> dict:
    base = partner_api_base(request)
    return {
        'api_base':    base,
        'list_url':    f'{base}/api/partner/articles/',
        'detail_url':  f'{base}/api/partner/articles/<slug>/',
        'file_url':    f'{base}/api/partner/articles/<slug>/file/',
        'token_url':   f'{base}/api/partner/auth/token/',
        'refresh_url': f'{base}/api/partner/auth/refresh/',
        'docs_url':    f'{base}/api/partner/docs/',
    }


# ── Kirish / chiqish ─────────────────────────────────────────────────────────

@method_decorator(never_cache, name='dispatch')
class PartnerDocsLoginView(View):
    template_name = 'partner/docs_login.html'

    def get(self, request):
        if _current_client(request):
            return redirect('partner-docs')
        return render(request, self.template_name, {'error': None, **_urls(request)})

    def post(self, request):
        ip  = client_ip(request)
        key = f'partner-docs-login:{ip}'
        if cache.get(key, 0) >= LOGIN_ATTEMPTS:
            return render(request, self.template_name, {
                'error': "Urinishlar ko'p. 10 daqiqadan keyin qayta urinib ko'ring.",
                **_urls(request),
            }, status=429)

        client_id = (request.POST.get('client_id') or '').strip()
        secret    = request.POST.get('client_secret') or ''
        client    = PartnerClient.objects.filter(client_id=client_id, is_active=True).first()

        if not client or not client.check_secret(secret):
            cache.set(key, cache.get(key, 0) + 1, LOGIN_WINDOW)
            return render(request, self.template_name, {
                'error': "client_id yoki client_secret noto'g'ri.",
                'client_id': client_id,
                **_urls(request),
            }, status=401)

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

        tokens = issue_pair(client)
        return render(request, self.template_name, {
            'client':       client,
            'tokens':       tokens,
            'schema_url':   reverse('partner-schema'),
            'logout_url':   reverse('partner-docs-logout'),
            'access_hours': round(settings.PARTNER_ACCESS_LIFETIME.total_seconds() / 3600, 1),
            'refresh_days': settings.PARTNER_REFRESH_LIFETIME.days,
            **_urls(request),
        })


# ── OpenAPI sxemasi — faqat /api/partner/ ────────────────────────────────────

class PartnerDocsSession(BasePermission):
    """Sxema faqat docs sahifasiga kirgan hamkorga beriladi."""
    def has_permission(self, request, view):
        return _current_client(request) is not None


class PartnerSchemaView(SpectacularAPIView):
    authentication_classes = []
    permission_classes     = [PartnerDocsSession]
    urlconf                = 'apps.partner.docs_urlconf'
    custom_settings = {
        'TITLE':       'Kutubxona.uz — Partner API',
        'DESCRIPTION': (
            "Tashqi xizmatlar uchun: chop etilgan maqolalar ro'yxati, bitta maqola "
            "va uning fayli. Faqat GET. Har so'rovga `Authorization: Bearer <access>` "
            "sarlavhasi kerak — bu sahifada u avtomatik qo'yilgan."
        ),
        'VERSION':            '1.0',
        'SCHEMA_PATH_PREFIX': '/api/partner',
    }
    serve_include_schema = False
