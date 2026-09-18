"""
CAPTCHA tekshiruvi (admin login uchun).

Uch provayder qo'llab-quvvatlanadi — `.env` da kalitlarni qo'yish kifoya,
kodni o'zgartirish shart emas:

    CAPTCHA_PROVIDER=turnstile          # turnstile | hcaptcha | recaptcha
    CAPTCHA_SITE_KEY=0x4AAAAAAA...      # frontendga beriladi
    CAPTCHA_SECRET_KEY=0x4AAAAAAA...    # faqat serverda qoladi

Kalitlar bo'sh bo'lsa CAPTCHA butunlay o'chiq bo'ladi (lokal ishlab chiqish
uchun) — login odatdagidek ishlayveradi.

Cloudflare Turnstile tavsiya etiladi: sayt allaqachon Cloudflare ortida,
bepul va foydalanuvchini bezovta qilmaydi.
"""
import logging

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

# Har bir provayder uchun: tekshirish manzili, brauzer skripti, widget klassi
# va brauzer yuboradigan maydon nomi.
PROVIDERS = {
    'turnstile': {
        'verify_url': 'https://challenges.cloudflare.com/turnstile/v0/siteverify',
        'script_url': 'https://challenges.cloudflare.com/turnstile/v0/api.js',
        'widget_class': 'cf-turnstile',
        'response_field': 'cf-turnstile-response',
        'label': 'Cloudflare Turnstile',
    },
    'hcaptcha': {
        'verify_url': 'https://api.hcaptcha.com/siteverify',
        'script_url': 'https://js.hcaptcha.com/1/api.js',
        'widget_class': 'h-captcha',
        'response_field': 'h-captcha-response',
        'label': 'hCaptcha',
    },
    'recaptcha': {
        'verify_url': 'https://www.google.com/recaptcha/api/siteverify',
        'script_url': 'https://www.google.com/recaptcha/api.js',
        'widget_class': 'g-recaptcha',
        'response_field': 'g-recaptcha-response',
        'label': 'Google reCAPTCHA',
    },
}

VERIFY_TIMEOUT = (5, 10)


def _provider_name() -> str:
    return (getattr(settings, 'CAPTCHA_PROVIDER', '') or 'turnstile').strip().lower()


def _provider() -> dict | None:
    return PROVIDERS.get(_provider_name())


def is_enabled() -> bool:
    """Ikkala kalit ham to'ldirilgan va provayder tanilgan bo'lsa — yoqilgan."""
    return bool(
        getattr(settings, 'CAPTCHA_SITE_KEY', '')
        and getattr(settings, 'CAPTCHA_SECRET_KEY', '')
        and _provider() is not None
    )


def public_config() -> dict:
    """Frontendga beriladigan sozlama (maxfiy kalitsiz)."""
    provider = _provider()
    if not is_enabled() or provider is None:
        return {'enabled': False}
    return {
        'enabled':        True,
        'provider':       _provider_name(),
        'label':          provider['label'],
        'site_key':       settings.CAPTCHA_SITE_KEY,
        'script_url':     provider['script_url'],
        'widget_class':   provider['widget_class'],
        'response_field': provider['response_field'],
    }


def verify(token: str, remote_ip: str = '') -> tuple[bool, str]:
    """
    CAPTCHA javobini provayderda tekshiradi.
    Qaytaradi: (muvaffaqiyatli, xato_kodi)

    CAPTCHA o'chiq bo'lsa har doim (True, '').
    """
    if not is_enabled():
        return True, ''

    provider = _provider()
    token = (token or '').strip()
    if not token:
        return False, 'captcha_missing'

    payload = {
        'secret':   settings.CAPTCHA_SECRET_KEY,
        'response': token,
    }
    if remote_ip:
        payload['remoteip'] = remote_ip

    try:
        resp = requests.post(
            provider['verify_url'], data=payload, timeout=VERIFY_TIMEOUT,
        )
        data = resp.json()
    except Exception as exc:
        logger.warning('CAPTCHA tekshirib bo\'lmadi (%s): %s', _provider_name(), exc)
        # Provayder javob bermayapti — loginni butunlay to'sib qo'ymaymiz,
        # lekin buni logda qoldiramiz. (Xohlasangiz bu yerda False qaytaring.)
        return True, ''

    if data.get('success'):
        return True, ''

    codes = data.get('error-codes') or []
    logger.info('CAPTCHA rad etildi: %s', codes)
    return False, (codes[0] if codes else 'captcha_failed')
