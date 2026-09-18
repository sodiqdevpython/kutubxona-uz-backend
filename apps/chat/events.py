"""
Chat real-time hodisalari (WebSocket orqali admin panelga yuboriladi).

Ilgari frontend har 5 sekundda `GET /api/admin/chat/` va `…/messages/` ni
qayta so'rar edi (polling). Endi har bir o'zgarish shu yerdan Channels
group'iga push qilinadi — frontend faqat ulanib turadi.

Redis (channel layer) ishlamay qolsa ham API javoblari buzilmasligi kerak,
shuning uchun har bir yuborish `try/except` ichida.
"""
import logging

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

logger = logging.getLogger(__name__)

# Barcha admin ulanishlari shu bitta group'da turadi
ADMIN_GROUP = 'admin_chat'


def _send(payload: dict) -> None:
    try:
        layer = get_channel_layer()
        if layer is None:
            return
        async_to_sync(layer.group_send)(
            ADMIN_GROUP,
            {'type': 'chat.event', 'payload': payload},
        )
    except Exception as exc:                      # pragma: no cover
        logger.warning('WebSocket broadcast yuborilmadi: %s', exc)


# ── Public helperlar ─────────────────────────────────────────────────────────

def chat_serialized(chat):
    """Sidebar uchun qisqa chat ko'rinishi (request'siz — URL'lar nisbiy)."""
    from .serializers import ChatListSerializer
    return ChatListSerializer(chat).data


def message_serialized(message):
    from .serializers import MessageSerializer
    return MessageSerializer(message).data


def message_created(chat, message) -> None:
    """Yangi xabar (admin yoki user) — xabar oynasi + sidebar yangilanadi."""
    _send({
        'event':   'message.created',
        'chat_id': str(chat.id),
        'message': message_serialized(message),
        'chat':    chat_serialized(chat),
    })


def chat_updated(chat) -> None:
    """Chat metasi o'zgardi (blok, o'qildi, yangi chat yaratildi)."""
    _send({
        'event':   'chat.updated',
        'chat_id': str(chat.id),
        'chat':    chat_serialized(chat),
    })


def chat_deleted(chat_id) -> None:
    _send({'event': 'chat.deleted', 'chat_id': str(chat_id)})


def chat_read(chat_id) -> None:
    _send({'event': 'chat.read', 'chat_id': str(chat_id)})
