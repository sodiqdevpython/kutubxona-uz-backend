"""
So'rov chegaralari.

DRF standart `AnonRateThrottle` mijozni `REMOTE_ADDR` bo'yicha ajratadi —
Cloudflare va nginx ortida bu proksining IP'si bo'lib qoladi va hamma
foydalanuvchi bitta hisobga tushadi. Shuning uchun `utils.request_ip.client_ip`
dan foydalanamiz.
"""
from rest_framework.throttling import SimpleRateThrottle

from .request_ip import client_ip


class ClientIPThrottle(SimpleRateThrottle):
    """Haqiqiy mijoz IP'si bo'yicha cheklaydigan baza sinf."""

    def get_cache_key(self, request, view):
        return self.cache_format % {
            'scope': self.scope,
            'ident': client_ip(request),
        }


class WriteOnlyThrottle(ClientIPThrottle):
    """Faqat yozuv so'rovlarini cheklaydi — o'qish erkin qoladi."""

    write_methods = ('POST', 'PUT', 'PATCH', 'DELETE')

    def allow_request(self, request, view):
        if request.method not in self.write_methods:
            return True
        return super().allow_request(request, view)


# ── Izohlar ──────────────────────────────────────────────────────────────────
# Ikki qatlam: ketma-ket spam uchun qisqa "burst", kun davomidagi oqim uchun
# uzunroq chegara. Ikkalasi ham faqat POST ga tegishli.

class CommentBurstThrottle(WriteOnlyThrottle):
    scope = 'comment_burst'


class CommentSustainedThrottle(WriteOnlyThrottle):
    scope = 'comment'
