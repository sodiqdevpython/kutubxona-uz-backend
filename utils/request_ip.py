"""
Mijoz IP manzilini aniqlash (Cloudflare + nginx ortida).

Ustuvorlik:
  1) CF-Connecting-IP  — Cloudflare har doim haqiqiy mijoz IP'sini shu yerga yozadi
  2) X-Forwarded-For   — birinchi element (nginx qo'shadi)
  3) REMOTE_ADDR       — to'g'ridan-to'g'ri ulanish

DIQQAT: bu sarlavhalarga faqat proksi ortida ishonish mumkin. nginx
konfiguratsiyasida `real_ip_header CF-Connecting-IP` va `set_real_ip_from`
Cloudflare diapazonlari bilan cheklangan (nginx/cloudflare-realip.conf).
"""


def client_ip(request) -> str:
    cf = (request.META.get('HTTP_CF_CONNECTING_IP') or '').strip()
    if cf:
        return cf

    xff = request.META.get('HTTP_X_FORWARDED_FOR', '')
    if xff:
        first = xff.split(',')[0].strip()
        if first:
            return first

    return request.META.get('REMOTE_ADDR', '') or 'unknown'
