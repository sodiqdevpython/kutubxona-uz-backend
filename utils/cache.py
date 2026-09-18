"""
Redis kesh yordamchilari.

Ommaviy (anonim) API javoblari keshlanadi — maqolalar ro'yxati, yo'nalishlar,
statistika, mualliflar. Har bir kesh kaliti "namespace versiyasi" bilan
belgilanadi: kontent o'zgarganda versiya bittaga oshadi va eski kalitlar
avtomatik "yo'qoladi" (ularni birma-bir o'chirish shart emas).

    api:catalog:v7:<querystring hash>

Foydalanish:
    class ArticleViewSet(CachedListMixin, viewsets.ReadOnlyModelViewSet):
        cache_namespace = 'catalog'

    @cached_action(namespace='catalog')
    def stats(self, request): ...
"""
import functools
import hashlib
import logging

from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)

# Kontent guruhlari — biri o'zgarsa, faqat shu guruh keshi yangilanadi
NS_CATALOG      = 'catalog'       # maqolalar, yo'nalishlar, jurnal sonlari
NS_AUTHORS      = 'authors'       # mualliflar
NS_CENTRAL_ASIA = 'central_asia'  # einfolib parser postlari

_VERSION_KEY = 'cachens:{}'
# Versiya kaliti uzoq yashaydi, lekin muddatsiz emas — Redis'da
# maxmemory-policy=volatile-lru bo'lsa ham to'g'ri ishlashi uchun.
_VERSION_TTL = 60 * 60 * 24 * 30      # 30 kun


def default_ttl() -> int:
    return int(getattr(settings, 'API_CACHE_TTL', 120))


# ── Namespace versiyasi ──────────────────────────────────────────────────────

def get_version(namespace: str) -> int:
    key = _VERSION_KEY.format(namespace)
    try:
        version = cache.get(key)
        if version is None:
            version = 1
            cache.set(key, version, _VERSION_TTL)
        return int(version)
    except Exception as exc:                   # Redis ishlamayapti
        logger.warning('Kesh versiyasini o\'qib bo\'lmadi (%s): %s', namespace, exc)
        return 0                               # 0 → kesh amalda o'chadi


def bump(namespace: str) -> None:
    """Kontent o'zgardi — shu guruhning barcha keshini bekor qiladi."""
    key = _VERSION_KEY.format(namespace)
    try:
        cache.incr(key)
    except ValueError:
        # kalit yo'q edi — noldan boshlaymiz
        cache.set(key, 1, _VERSION_TTL)
    except Exception as exc:
        logger.warning('Kesh bekor qilinmadi (%s): %s', namespace, exc)


def bump_all() -> None:
    for ns in (NS_CATALOG, NS_AUTHORS, NS_CENTRAL_ASIA):
        bump(ns)


# ── Kalit va keshlanadigan so'rov shartlari ──────────────────────────────────

def request_cache_key(request, namespace: str) -> str:
    raw = '{}?{}'.format(request.path, request.META.get('QUERY_STRING', ''))
    digest = hashlib.md5(raw.encode('utf-8')).hexdigest()
    return 'api:{}:v{}:{}'.format(namespace, get_version(namespace), digest)


def is_cacheable(request) -> bool:
    """
    Faqat anonim GET so'rovlar keshlanadi. Tizimga kirgan admin har doim
    yangi ma'lumot ko'rishi kerak, shuning uchun Authorization bor bo'lsa — yo'q.
    """
    if request.method != 'GET':
        return False
    if request.META.get('HTTP_AUTHORIZATION'):
        return False
    user = getattr(request, 'user', None)
    return not (user and user.is_authenticated)


# ── DRF yordamchilari ────────────────────────────────────────────────────────

class CachedListMixin:
    """
    ViewSet'ning `list` javobini keshlaydi.
    `retrieve` keshlanmaydi — u ko'rishlar sonini oshiradi (side effect).
    """
    cache_namespace = NS_CATALOG
    cache_ttl: int | None = None

    def list(self, request, *args, **kwargs):
        if not is_cacheable(request):
            return super().list(request, *args, **kwargs)

        key = request_cache_key(request, self.cache_namespace)
        cached = cache.get(key)
        if cached is not None:
            from rest_framework.response import Response
            return Response(cached)

        response = super().list(request, *args, **kwargs)
        if response.status_code == 200:
            cache.set(key, response.data, self.cache_ttl or default_ttl())
        return response


def cached_action(namespace: str = NS_CATALOG, ttl: int | None = None):
    """`@action` metodlari uchun kesh dekoratori (stats, related, …)."""
    def decorator(func):
        @functools.wraps(func)
        def wrapper(self, request, *args, **kwargs):
            if not is_cacheable(request):
                return func(self, request, *args, **kwargs)

            key = request_cache_key(request, namespace)
            cached = cache.get(key)
            if cached is not None:
                from rest_framework.response import Response
                return Response(cached)

            response = func(self, request, *args, **kwargs)
            if getattr(response, 'status_code', 500) == 200:
                cache.set(key, response.data, ttl or default_ttl())
            return response
        return wrapper
    return decorator


# ── Avtomatik bekor qilish (signals) ─────────────────────────────────────────

def register_invalidation() -> None:
    """
    Model saqlanganda/o'chirilganda tegishli namespace versiyasini oshiradi.
    `apps/articles/apps.py` → ready() ichida chaqiriladi.
    """
    from django.db.models.signals import post_delete, post_save

    def _make_handler(namespace):
        def handler(sender, **kwargs):
            bump(namespace)
        return handler

    targets = [
        ('articles.Article',            NS_CATALOG),
        ('articles.Category',           NS_CATALOG),
        ('articles.ArticleAuthor',      NS_CATALOG),
        ('articles.Keyword',            NS_CATALOG),
        ('journals.Journal',            NS_CATALOG),
        ('journals.Issue',              NS_CATALOG),
        ('authors.Author',              NS_AUTHORS),
        ('central_asia.CentralAsiaPost', NS_CENTRAL_ASIA),
    ]

    for label, namespace in targets:
        handler = _make_handler(namespace)
        # dispatch_uid — ikki marta ulanib qolmasligi uchun
        uid = 'cache-invalidate-{}'.format(label)
        post_save.connect(handler, sender=label, weak=False, dispatch_uid=uid + '-save')
        post_delete.connect(handler, sender=label, weak=False, dispatch_uid=uid + '-delete')

    # Maqola muallifga bog'lansa — muallif sahifalari keshi ham eskiradi
    def _articles_changed(sender, **kwargs):
        bump(NS_CATALOG)
        bump(NS_AUTHORS)

    post_save.connect(
        _articles_changed, sender='articles.Article', weak=False,
        dispatch_uid='cache-invalidate-article-authors',
    )

    # Muallif ma'lumoti (ism, avatar) maqola ro'yxatlarida ham chiqadi —
    # profilga rasm yuklangach maqola kartochkalarida ham darhol ko'rinsin.
    def _author_changed(sender, **kwargs):
        bump(NS_AUTHORS)
        bump(NS_CATALOG)

    for signal, suffix in ((post_save, 'save'), (post_delete, 'delete')):
        signal.connect(
            _author_changed, sender='authors.Author', weak=False,
            dispatch_uid=f'cache-invalidate-author-catalog-{suffix}',
        )
