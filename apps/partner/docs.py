"""
Hamkorlar uchun hujjat sahifasi — `/api/partner/docs/`.

Oddiy sahifa: hamkor `client_id` (login) + `client_secret` (parol) bilan
kiradi, tepada shu hamkor uchun yangi access/refresh, pastda 3 ta endpoint
(ro'yxat, maqola, access yangilash) — misollar va real javob namunasi bilan.

Sessiya oddiy Django sessiyasi; hamkor o'chirilsa yoki tokenlari bekor
qilinsa sessiya ham tugaydi. Kirish sahifasida CAPTCHA (`.env` dagi
CAPTCHA_* kalitlari) — admin login bilan bir xil sozlama.
"""
import json

from django.conf import settings
from django.core.cache import cache
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.cache import never_cache

from utils import captcha
from utils.request_ip import client_ip

from .models import PartnerClient
from .serializers import PartnerArticleDetailSerializer, PartnerArticleListSerializer
from .tokens import issue_pair
from .utils import partner_api_base
from .views import published_articles

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
        'detail_url':  f'{base}/api/partner/articles/<id>/',
        'refresh_url': f'{base}/api/partner/auth/refresh/',
        'docs_url':    f'{base}/api/partner/docs/',
    }


def _pretty(data) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2)


# ── Kirish / chiqish ─────────────────────────────────────────────────────────

@method_decorator(never_cache, name='dispatch')
class PartnerDocsLoginView(View):
    template_name = 'partner/docs_login.html'

    def _render(self, request, status=200, **extra):
        return render(request, self.template_name, {
            'captcha': captcha.public_config(),
            'error':   None,
            **_urls(request),
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

        # Real javob namunalari — birinchi chop etilgan maqola
        qs      = published_articles()
        sample  = qs.first()
        ctx_ser = {'request': request}
        if sample is not None:
            list_example = {
                'count':    qs.count(),
                'next':     None,
                'previous': None,
                'results':  [PartnerArticleListSerializer(sample, context=ctx_ser).data],
            }
            detail_example = PartnerArticleDetailSerializer(sample, context=ctx_ser).data
            sample_id      = str(sample.pk)
        else:
            list_example   = {'count': 0, 'next': None, 'previous': None, 'results': []}
            detail_example = None
            sample_id      = '<id>'

        tokens = issue_pair(client)
        urls   = _urls(request)
        return render(request, self.template_name, {
            'client':         client,
            'tokens':         tokens,
            'logout_url':     reverse('partner-docs-logout'),
            'access_hours':   round(settings.PARTNER_ACCESS_LIFETIME.total_seconds() / 3600, 1),
            'refresh_days':   settings.PARTNER_REFRESH_LIFETIME.days,
            'sample_id':      sample_id,
            'detail_sample_url': f"{urls['api_base']}/api/partner/articles/{sample_id}/",
            'list_example':   _pretty(list_example),
            'detail_example': _pretty(detail_example) if detail_example else None,
            'refresh_example': _pretty({
                'token_type': 'Bearer', 'access': 'eyJ…', 'refresh': 'eyJ…',
                'access_expires_in': int(settings.PARTNER_ACCESS_LIFETIME.total_seconds()),
                'refresh_expires_in': int(settings.PARTNER_REFRESH_LIFETIME.total_seconds()),
            }),
            **urls,
        })
