"""Telegram Bot API helper — Django admin actions uchun."""
import json
import logging
import requests
from django.conf import settings

logger = logging.getLogger(__name__)


def _token() -> str:
    return getattr(settings, 'TELEGRAM_BOT_TOKEN', '')


def send_message(chat_id: int, text: str, parse_mode: str = 'HTML') -> bool:
    """Telegram foydalanuvchisiga xabar yuboradi. Token yo'q bo'lsa, jim qaytadi."""
    token = _token()
    if not token:
        logger.warning('TELEGRAM_BOT_TOKEN sozlanmagan — xabar yuborilmadi.')
        return False
    try:
        resp = requests.post(
            f'https://api.telegram.org/bot{token}/sendMessage',
            json={'chat_id': chat_id, 'text': text, 'parse_mode': parse_mode},
            timeout=5,
        )
        if not resp.ok:
            logger.warning('Telegram sendMessage muvaffaqiyatsiz: %s', resp.text)
        return resp.ok
    except Exception as exc:
        logger.error('Telegram xabar yuborishda xatolik: %s', exc)
        return False


def send_photo(chat_id: int, photo_path: str, caption: str = '',
               parse_mode: str = 'HTML', reply_markup: dict | None = None) -> bool:
    """Diskdagi rasmni yuboradi (caption + ixtiyoriy inline tugmalar)."""
    token = _token()
    if not token or not photo_path:
        return False
    try:
        data = {'chat_id': chat_id, 'caption': caption[:1024], 'parse_mode': parse_mode}
        if reply_markup:
            data['reply_markup'] = json.dumps(reply_markup)
        with open(photo_path, 'rb') as fh:
            resp = requests.post(
                f'https://api.telegram.org/bot{token}/sendPhoto',
                data=data, files={'photo': fh}, timeout=20,
            )
        return resp.ok
    except Exception as exc:
        logger.error('Telegram sendPhoto xatolik: %s', exc)
        return False


def send_document(chat_id: int, doc_path: str, caption: str = '',
                  parse_mode: str = 'HTML', reply_markup: dict | None = None) -> bool:
    """Diskdagi faylni yuboradi (caption + ixtiyoriy inline tugmalar)."""
    token = _token()
    if not token or not doc_path:
        return False
    try:
        data = {'chat_id': chat_id, 'caption': caption[:1024], 'parse_mode': parse_mode}
        if reply_markup:
            data['reply_markup'] = json.dumps(reply_markup)
        with open(doc_path, 'rb') as fh:
            resp = requests.post(
                f'https://api.telegram.org/bot{token}/sendDocument',
                data=data, files={'document': fh}, timeout=30,
            )
        return resp.ok
    except Exception as exc:
        logger.error('Telegram sendDocument xatolik: %s', exc)
        return False
