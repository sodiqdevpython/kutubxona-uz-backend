"""
Chat endpointlar:
- GET    /api/admin/chat/                    — admin: chatlar ro'yxati
- GET    /api/admin/chat/by-author/<slug>/   — admin: muallif uchun chat (yaratiladi yo'q bo'lsa)
- GET    /api/admin/chat/<chat_id>/messages/ — admin: chat tarixi
- POST   /api/admin/chat/<chat_id>/send/     — admin: yangi xabar (text/photo/document)
- POST   /api/admin/chat/<chat_id>/block/    — admin: bloklash/aktivlash toggle
- POST   /api/admin/chat/<chat_id>/read/     — admin: barchasini o'qildi qilish

- POST   /api/chat/bot-message/              — bot: userdan kelgan xabar (secret)

Har bir o'zgarish WebSocket orqali admin panelga push qilinadi (`events.py`),
shuning uchun frontendda polling (setInterval) kerak emas.
"""
import logging

from django.conf import settings
from django.db.models import Q
from django.shortcuts import get_object_or_404

from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.authors.models import Author
from utils.telegram import send_message, send_photo, send_document

from . import events
from .models import Chat, Message
from .serializers import ChatListSerializer, MessageSerializer

logger = logging.getLogger(__name__)


# ── Ruxsat ────────────────────────────────────────────────────────────────────

class IsStaff(IsAuthenticated):
    def has_permission(self, request, view):
        return super().has_permission(request, view) and bool(request.user.is_staff)


# ── Admin: chat list ──────────────────────────────────────────────────────────

class AdminChatListView(APIView):
    """
    GET /api/admin/chat/?offset=0&limit=20&search=…

    Ro'yxatga tushadi:
      • Telegram bot orqali kamida bitta submission yuborgan mualliflar
        (ular uchun Chat avtomatik yaratiladi — admin suhbatni boshlashi mumkin);
      • allaqachon suhbat ochilgan (foydalanuvchi yozgan yoki admin ochgan) chatlar.

    Pagination: offset/limit. Response: { results, has_more, next_offset, total }
    """
    permission_classes = [IsStaff]

    DEFAULT_LIMIT = 20
    MAX_LIMIT     = 100

    def get(self, request):
        try:
            offset = max(0, int(request.query_params.get('offset', 0)))
        except (TypeError, ValueError):
            offset = 0
        try:
            limit = int(request.query_params.get('limit', self.DEFAULT_LIMIT))
        except (TypeError, ValueError):
            limit = self.DEFAULT_LIMIT
        limit = max(1, min(limit, self.MAX_LIMIT))

        # ── Submission yuborgan har bir Telegram muallif uchun Chat yaratamiz ──
        # Bu idempotent: mavjud bo'lsa qayta yaratilmaydi.
        eligible_authors = (
            Author.objects
            .filter(telegram_chat_id__isnull=False, submissions__isnull=False)
            .distinct()
        )
        existing_author_ids = set(Chat.objects.values_list('author_id', flat=True))
        new_chats = [
            Chat(author=a) for a in eligible_authors
            if a.id not in existing_author_ids
        ]
        if new_chats:
            Chat.objects.bulk_create(new_chats)

        # ── Asosiy query ──────────────────────────────────────────────────────
        # Telegram'ga ulangan barcha mualliflar chatlari. Ilgari faqat
        # submission yuborganlar chiqardi — natijada bot orqali yozgan, lekin
        # hali maqola topshirmagan foydalanuvchining chati ko'rinmay qolardi.
        qs = (
            Chat.objects
            .filter(author__telegram_chat_id__isnull=False)
            .select_related('author')
            .order_by('-last_message_at', '-created_at')
        )

        search = (request.query_params.get('search') or '').strip()
        if search:
            qs = qs.filter(
                Q(author__name__icontains=search) |
                Q(author__telegram_username__icontains=search)
            )

        total = qs.count()
        page  = qs[offset:offset + limit]
        data  = ChatListSerializer(page, many=True, context={'request': request}).data

        next_offset = offset + len(data)
        return Response({
            'results':     data,
            'total':       total,
            'has_more':    next_offset < total,
            'next_offset': next_offset,
        })


class AdminChatByAuthorView(APIView):
    """
    GET /api/admin/chat/by-author/<author_slug>/
    Mavjud bo'lsa qaytaradi, bo'lmasa yangi yaratadi.
    """
    permission_classes = [IsStaff]

    def get(self, request, slug):
        author = get_object_or_404(Author, slug=slug)
        if not author.telegram_chat_id:
            return Response({'error': "Bu muallifda Telegram chat_id yo'q"}, status=400)
        chat, created = Chat.objects.get_or_create(author=author)
        if created:
            events.chat_updated(chat)
        data = ChatListSerializer(chat, context={'request': request}).data
        return Response(data)


# ── Admin: messages tarix + yuborish ──────────────────────────────────────────

class AdminChatMessagesView(APIView):
    permission_classes = [IsStaff]

    def get(self, request, chat_id):
        chat = get_object_or_404(Chat, pk=chat_id)
        msgs = chat.messages.all().order_by('created_at')
        return Response(MessageSerializer(msgs, many=True, context={'request': request}).data)


class AdminChatSendView(APIView):
    """
    POST /api/admin/chat/<chat_id>/send/
    multipart/form-data:
      text           — matn (caption ham)
      image          — File (rasm)
      document       — File (fayl)
    """
    permission_classes = [IsStaff]
    parser_classes     = [MultiPartParser, FormParser, JSONParser]

    def post(self, request, chat_id):
        chat = get_object_or_404(Chat.objects.select_related('author'), pk=chat_id)

        text     = (request.data.get('text') or '').strip()
        image    = request.FILES.get('image')
        document = request.FILES.get('document')

        if not text and not image and not document:
            return Response({'error': "Xabar bo'sh bo'lmasligi kerak"}, status=400)

        # Saqlash
        if image:
            kind = 'photo'
        elif document:
            kind = 'document'
        else:
            kind = 'text'

        msg = Message.objects.create(
            chat=chat, sender='admin', kind=kind,
            text=text, image=image, document=document,
            is_read=True,
        )

        # Telegram'ga yuborish — admin javobi foydalanuvchiga boradi
        delivered  = False
        chat_tg_id = chat.author.telegram_chat_id
        if chat_tg_id:
            try:
                if kind == 'photo' and msg.image:
                    delivered = send_photo(chat_tg_id, msg.image.path, caption=text)
                elif kind == 'document' and msg.document:
                    delivered = send_document(chat_tg_id, msg.document.path, caption=text)
                else:
                    delivered = send_message(chat_tg_id, text)
            except Exception as exc:
                logger.warning('Telegram yetkazib berilmadi (chat=%s): %s', chat.id, exc)

        # Chat metasini yangilash
        chat.last_message_at = msg.created_at
        chat.save(update_fields=['last_message_at', 'updated_at'])

        # Real-time: boshqa ochiq admin oynalari ham darhol ko'radi
        events.message_created(chat, msg)

        payload = MessageSerializer(msg, context={'request': request}).data
        payload['tg_delivered'] = delivered
        return Response(payload, status=201)


class AdminChatBlockView(APIView):
    permission_classes = [IsStaff]

    def post(self, request, chat_id):
        chat = get_object_or_404(Chat, pk=chat_id)
        chat.is_blocked = not chat.is_blocked
        chat.save(update_fields=['is_blocked', 'updated_at'])
        events.chat_updated(chat)
        return Response({'is_blocked': chat.is_blocked})


class AdminChatDeleteView(APIView):
    """
    DELETE /api/admin/chat/<chat_id>/
    Chat va unga tegishli barcha xabarlarni o'chiradi (CASCADE).
    """
    permission_classes = [IsStaff]

    def delete(self, request, chat_id):
        chat = get_object_or_404(Chat, pk=chat_id)
        deleted_id = str(chat.id)
        chat.delete()
        events.chat_deleted(deleted_id)
        return Response(status=204)


class AdminChatReadView(APIView):
    """Barcha user xabarlarini o'qildi qilish."""
    permission_classes = [IsStaff]

    def post(self, request, chat_id):
        chat = get_object_or_404(Chat, pk=chat_id)
        chat.messages.filter(sender='user', is_read=False).update(is_read=True)
        chat.unread_count = 0
        chat.save(update_fields=['unread_count', 'updated_at'])
        events.chat_read(chat.id)
        return Response({'ok': True})


# ── Bot: userdan kelgan xabar ─────────────────────────────────────────────────

class BotMessageView(APIView):
    """
    POST /api/chat/bot-message/   (multipart yoki JSON)
    Bot bizga foydalanuvchi xabarini yuboradi (secret bilan himoyalangan).

    Maydonlar:
      secret        — BOT_SECRET
      chat_id       — Telegram user chat_id (Author.telegram_chat_id)
      text          — matn / caption
      image         — File (ixtiyoriy, rasm)
      document      — File (ixtiyoriy, hujjat)
      tg_message_id — Telegram msg id (ixtiyoriy)

    Qoidalar:
      - Author topilmasa → 404 (bot foydalanuvchiga "ro'yxatdan o'tmagansiz" deydi)
      - Chat mavjud bo'lmasa — avtomatik yaratiladi
      - is_blocked=True → 403
    """
    permission_classes = [AllowAny]
    parser_classes     = [MultiPartParser, FormParser, JSONParser]

    def post(self, request):
        if request.data.get('secret') != getattr(settings, 'BOT_SECRET', ''):
            return Response({'error': 'Forbidden'}, status=403)

        try:
            chat_id = int(request.data.get('chat_id'))
        except (TypeError, ValueError):
            return Response({'error': 'chat_id required'}, status=400)

        text     = (request.data.get('text') or '').strip()
        image    = request.FILES.get('image')
        document = request.FILES.get('document')

        if not text and not image and not document:
            return Response({'error': 'text required'}, status=400)

        # 1) Muallifni topish
        try:
            author = Author.objects.get(telegram_chat_id=chat_id)
        except Author.DoesNotExist:
            return Response({'error': 'author_not_found'}, status=404)

        # 2) Chat — yo'q bo'lsa yaratamiz (foydalanuvchi suhbatni boshlashi mumkin)
        chat, _ = Chat.objects.select_related('author').get_or_create(author=author)

        # 3) Bloklangan
        if chat.is_blocked:
            return Response({'error': 'blocked'}, status=403)

        # 4) Saqlash
        tg_msg_id = request.data.get('tg_message_id')
        try:
            tg_msg_id = int(tg_msg_id) if tg_msg_id else None
        except (TypeError, ValueError):
            tg_msg_id = None

        kind = 'photo' if image else ('document' if document else 'text')

        msg = Message.objects.create(
            chat=chat, sender='user', kind=kind,
            text=text, image=image, document=document,
            tg_message_id=tg_msg_id,
        )

        # 5) Chat meta + unread inkrement
        chat.last_message_at = msg.created_at
        chat.unread_count   = chat.unread_count + 1
        chat.save(update_fields=['last_message_at', 'unread_count', 'updated_at'])

        # 6) Real-time: admin panel darhol ko'radi (polling'siz)
        events.message_created(chat, msg)

        return Response({'ok': True, 'message_id': str(msg.id)}, status=201)
