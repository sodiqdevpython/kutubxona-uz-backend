"""
Admin panel chat WebSocket consumer'i.

Endpoint:  ws://<host>/ws/admin/chat/?token=<JWT access>

Faqat `is_staff` foydalanuvchilar ulana oladi. Ulangan har bir admin
`admin_chat` group'ida turadi va barcha chat hodisalarini oladi:
  message.created · chat.updated · chat.deleted · chat.read

Client → server:
  {"action": "ping"}                      → {"event": "pong"}
  {"action": "read", "chat_id": "<uuid>"} → xabarlarni o'qildi qilish
"""
import json
import logging

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer

from .events import ADMIN_GROUP

logger = logging.getLogger(__name__)


class AdminChatConsumer(AsyncWebsocketConsumer):

    async def connect(self):
        user = self.scope.get('user')
        if not user or not user.is_authenticated or not user.is_staff:
            # Avval accept qilamiz, keyin 4401 bilan yopamiz — shundagina
            # brauzer handshake xatosi (403) o'rniga aniq kodni ko'radi va
            # frontend foydalanuvchini /login ga yo'naltira oladi.
            await self.accept()
            await self.send(text_data=json.dumps({'event': 'unauthorized'}))
            await self.close(code=4401)
            return

        await self.channel_layer.group_add(ADMIN_GROUP, self.channel_name)
        await self.accept()
        await self.send(text_data=json.dumps({'event': 'ready'}))

    async def disconnect(self, code):
        try:
            await self.channel_layer.group_discard(ADMIN_GROUP, self.channel_name)
        except Exception:                          # pragma: no cover
            pass

    async def receive(self, text_data=None, bytes_data=None):
        if not text_data:
            return
        try:
            data = json.loads(text_data)
        except (ValueError, TypeError):
            return

        action = data.get('action')
        if action == 'ping':
            await self.send(text_data=json.dumps({'event': 'pong'}))

        elif action == 'read' and data.get('chat_id'):
            ok = await self._mark_read(data['chat_id'])
            if ok:
                # group_send'ni shu yerda — consumer'ning event loop'ida
                # bajaramiz (boshqa loopdan chaqirish Redis'da xatoga olib keladi)
                await self.channel_layer.group_send(ADMIN_GROUP, {
                    'type': 'chat.event',
                    'payload': {'event': 'chat.read', 'chat_id': str(data['chat_id'])},
                })

    # ── Group handler ────────────────────────────────────────────────────────

    async def chat_event(self, event):
        await self.send(text_data=json.dumps(event['payload']))

    # ── DB ───────────────────────────────────────────────────────────────────

    @database_sync_to_async
    def _mark_read(self, chat_id) -> bool:
        from .models import Chat

        try:
            chat = Chat.objects.get(pk=chat_id)
        except (Chat.DoesNotExist, ValueError, TypeError):
            return False
        chat.messages.filter(sender='user', is_read=False).update(is_read=True)
        if chat.unread_count:
            chat.unread_count = 0
            chat.save(update_fields=['unread_count', 'updated_at'])
        return True
