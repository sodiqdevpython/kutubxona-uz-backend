from rest_framework import viewsets, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.permissions import AllowAny
from django_filters.rest_framework import DjangoFilterBackend
from django.conf import settings
from django.db.models import Q
import django_filters

from utils.telegram import send_message as tg_send
from .models import Category, Article, ArticleSubmission
from .serializers import (
    CategorySerializer,
    ArticleListSerializer,
    ArticleDetailSerializer,
    ArticleSubmissionSerializer,
)


# ── Custom filters ────────────────────────────────────────────────────────────

class _NumberInFilter(django_filters.BaseInFilter, django_filters.NumberFilter):
    pass

class _CharInFilter(django_filters.BaseInFilter, django_filters.CharFilter):
    pass

class ArticleFilter(django_filters.FilterSet):
    """
    Supports:
      ?categories=slug1,slug2   — category slug IN filter
      ?years=2026,2025          — year IN filter
      ?quarters=1,2             — quarter IN filter
      ?author=some-slug         — author slug exact match
      ?status=open              — exact status
    """
    categories = _CharInFilter(field_name='category__slug', lookup_expr='in')
    years      = _NumberInFilter(field_name='year',    lookup_expr='in')
    quarters   = _NumberInFilter(field_name='quarter', lookup_expr='in')
    author     = django_filters.CharFilter(field_name='authors__slug', lookup_expr='exact')
    status     = django_filters.CharFilter(field_name='status', lookup_expr='exact')

    class Meta:
        model  = Article
        fields: list = []


class CategoryViewSet(viewsets.ReadOnlyModelViewSet):
    """Faqat kamida bitta chop etilgan maqolasi bo'lgan yo'nalishlar."""
    queryset = Category.objects.filter(articles__issue__isnull=False).distinct()
    serializer_class = CategorySerializer
    pagination_class = None


class ArticleViewSet(viewsets.ReadOnlyModelViewSet):
    """Faqat jurnal soniga kiritilgan (chop etilgan) maqolalar."""
    queryset = (
        Article.objects
        .filter(issue__isnull=False)
        .select_related('category', 'issue', 'issue__journal')
        .prefetch_related('authors')
        .distinct()
    )
    filter_backends  = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class  = ArticleFilter
    search_fields    = ['title', 'excerpt', 'author_names', 'authors__name', 'keywords__name']
    ordering_fields  = ['created_at', 'views', 'cites', 'published_at', 'issue__year', 'issue__number']
    # Default: arxiv yili (jurnal soni) bo'yicha — eng yangi yil tepada,
    # create/assign vaqti bo'yicha emas.
    ordering         = ['-issue__year', '-issue__number', '-published_at', '-created_at']
    lookup_field     = 'slug'

    def get_serializer_class(self):
        if self.action == 'retrieve':
            return ArticleDetailSerializer
        return ArticleListSerializer

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        self._unique_view(request, instance)
        return Response(self.get_serializer(instance, context={'request': request}).data)

    @staticmethod
    def _unique_view(request, article):
        """
        Bir IP+article kombinatsiyasi uchun 24 soatda bitta marta hisoblanadi.
        Bu django-hitcount mantiqiga o'xshash, lekin oddiyroq va dependency'siz.
        """
        from django.core.cache import cache

        # Mijoz IP'sini olish (proxy ortida bo'lsa X-Forwarded-For dan)
        xff = request.META.get('HTTP_X_FORWARDED_FOR', '')
        ip  = (xff.split(',')[0].strip() if xff else request.META.get('REMOTE_ADDR', '')) or 'unknown'

        key = f'view:{article.pk}:{ip}'
        # cache.add() True qaytaradi faqat agar kalit yo'q bo'lsa
        if cache.add(key, 1, timeout=86400):  # 24 soat
            article.increment_views()

    @action(detail=False, url_path='search')
    def search_articles(self, request):
        """GET /api/articles/search/?q=… — title, excerpt, keywords, mualliflar bo'yicha."""
        q  = request.query_params.get('q', '').strip()
        qs = self.get_queryset()
        if q:
            qs = qs.filter(
                Q(title__icontains=q) |
                Q(excerpt__icontains=q) |
                Q(author_names__icontains=q) |
                Q(authors__name__icontains=q) |
                Q(keywords__name__icontains=q)
            ).distinct()
        serializer = ArticleListSerializer(qs[:10], many=True, context={'request': request})
        return Response(serializer.data)

    @action(detail=False, url_path='stats', permission_classes=[AllowAny])
    def stats(self, request):
        """
        GET /api/articles/stats/
        Saytdagi umumiy raqamlar — hero qismida ko'rsatish uchun.
        """
        from apps.authors.models import Author
        from apps.journals.models import Issue
        articles_count = Article.objects.filter(issue__isnull=False).count()
        authors_count = (
            Author.objects
            .filter(articles__issue__isnull=False)
            .distinct().count()
        )
        issues_count = Issue.objects.filter(is_upcoming=False).count()
        return Response({
            'articles': articles_count,
            'authors':  authors_count,
            'issues':   issues_count,
        })

    @action(detail=True, methods=['post'], url_path='ask', permission_classes=[AllowAny])
    def ask(self, request, slug=None):
        """
        POST /api/articles/<slug>/ask/  body: {"question": "..."}
        Faqat admin AI ga o'qitgan (llm_document_id mavjud) maqolalar uchun ishlaydi.
        Hujjat upload qilinmaydi — admin /api/admin/articles/<id>/train-ai/ orqali oldindan o'qitadi.
        """
        article  = self.get_object()
        question = (request.data.get('question') or '').strip()

        if not question:
            return Response({'error': 'Savol bo\'sh'}, status=400)
        if len(question) > 500:
            return Response({'error': 'Savol juda uzun (500 belgidan ortiq)'}, status=400)

        doc_id = (article.llm_document_id or '').strip()
        if not doc_id:
            return Response(
                {'error': 'Bu maqola AI bilan o\'qitilmagan. Adminga murojaat qiling.'},
                status=400,
            )

        # Sodda IP rate limit — 1 IP / 15 sekundda 1 ta savol
        from django.core.cache import cache
        xff = request.META.get('HTTP_X_FORWARDED_FOR', '')
        ip  = (xff.split(',')[0].strip() if xff else request.META.get('REMOTE_ADDR', '')) or 'unknown'
        rl_key = f'ask:{article.pk}:{ip}'
        if not cache.add(rl_key, 1, timeout=15):
            return Response({'error': 'Juda tez-tez savol berayapsiz. Bir oz kuting.'}, status=429)

        from utils.local_llm import ask as llm_ask
        answer, err = llm_ask(doc_id, question, source_language='uz')

        if err == 'not_found':
            # LLM hujjatni unutgan — admin qayta o'qitishi kerak
            article.llm_document_id = ''
            article.save(update_fields=['llm_document_id', 'updated_at'])
            return Response(
                {'error': 'AI hujjati eskirgan. Admin qayta o\'qitishi kerak.'},
                status=410,
            )

        if err:
            return Response({'error': err}, status=502)

        return Response({'answer': answer})

    @action(detail=True, url_path='related')
    def related(self, request, slug=None):
        """
        GET /api/articles/<slug>/related/
        Kalit so'zlar bo'yicha yaqin maqolalar — eng ko'p umumiy keyword'ga ko'ra.
        Kamida 1 umumiy keyword bo'lishi shart.
        """
        from django.db.models import Count
        article = self.get_object()
        kw_ids = list(article.keywords.values_list('id', flat=True))

        if not kw_ids:
            return Response([])

        qs = (
            self.get_queryset()
            .exclude(pk=article.pk)
            .filter(keywords__in=kw_ids)
            .annotate(shared=Count('keywords', filter=Q(keywords__in=kw_ids), distinct=True))
            .order_by('-shared', '-published_at')
        )[:6]

        return Response(ArticleListSerializer(qs, many=True, context={'request': request}).data)


# ── Bot submission endpointlari (draft → finalize) ────────────────────────────

from datetime import timedelta
from django.utils import timezone

# Bitta foydalanuvchi bir kunda yubora oladigan maksimal maqola soni
DAILY_SUBMIT_LIMIT = 10


def _check_secret(request):
    secret = request.data.get('secret') or request.query_params.get('secret', '')
    return secret == getattr(settings, 'BOT_SECRET', '')


def _active_draft(chat_id):
    """Foydalanuvchining ochiq qoralamasi (yoki None)."""
    return (
        ArticleSubmission.objects
        .filter(chat_id=chat_id, status='draft')
        .order_by('-created_at')
        .first()
    )


class SubmissionDraftView(APIView):
    """
    POST /api/submit/draft/ — qoralama yaratish yoki yangilash (har bir bosqichda).
    Bot bitta maydonni yuboradi, biz uni DB dagi draftga yozamiz.
    RAM da emas — DB da saqlanadi, shuning uchun user uzoq tanaffusdan keyin ham davom etadi.
    """
    parser_classes     = [MultiPartParser, FormParser]
    permission_classes = [AllowAny]

    # Bot yuboradigan, yangilanishi mumkin bo'lgan maydonlar
    TEXT_FIELDS = ('title', 'keywords', 'abstract', 'references', 'tg_name', 'tg_username')

    def post(self, request):
        if not _check_secret(request):
            return Response({'error': 'Forbidden'}, status=403)

        chat_id = request.data.get('chat_id')
        if not chat_id:
            return Response({'error': 'chat_id talab qilinadi'}, status=400)

        try:
            chat_id = int(chat_id)
        except (TypeError, ValueError):
            return Response({'error': 'chat_id noto\'g\'ri'}, status=400)

        sub = _active_draft(chat_id)
        if sub is None:
            sub = ArticleSubmission(chat_id=chat_id, status='draft')

        # Matn maydonlari (faqat kelganlari)
        for f in self.TEXT_FIELDS:
            if f in request.data:
                setattr(sub, f, request.data[f])

        # Rasm
        if 'image' in request.FILES:
            sub.image = request.FILES['image']

        # Manba fayl + matn ajratish
        file_changed = 'source_file' in request.FILES
        if file_changed:
            sub.source_file = request.FILES['source_file']

        sub.save()

        # Fayl kelgan bo'lsa — matnni ajratib saqlaymiz (AI keyin shuni ishlatadi)
        if file_changed:
            from utils.extract import extract_text
            try:
                text = extract_text(sub.source_file)
                if text:
                    sub.extracted_text = text
                    sub.save(update_fields=['extracted_text', 'updated_at'])
            except Exception:
                pass

        return Response(ArticleSubmissionSerializer(sub, context={'request': request}).data, status=200)


class SubmissionFinalizeView(APIView):
    """
    POST /api/submit/finalize/ — qoralamani 'pending' holatiga o'tkazadi.
    Faqat shu paytda admin ko'radi va foydalanuvchiga tasdiqlangan hisoblanadi.
    """
    permission_classes = [AllowAny]

    def post(self, request):
        if not _check_secret(request):
            return Response({'error': 'Forbidden'}, status=403)

        chat_id = request.data.get('chat_id')
        try:
            chat_id = int(chat_id)
        except (TypeError, ValueError):
            return Response({'error': 'chat_id noto\'g\'ri'}, status=400)

        sub = _active_draft(chat_id)
        if sub is None:
            return Response({'error': 'Qoralama topilmadi'}, status=404)

        # Bot faqat rasm + fayl talab qiladi (qolganini AI ajratadi)
        missing = []
        if not sub.image:
            missing.append('image')
        if not sub.source_file:
            missing.append('source_file')
        if missing:
            return Response({'error': 'To\'ldirilmagan', 'missing': missing}, status=400)

        # ── Kunlik limit (oxirgi 24 soatda yuborilgan, draft bo'lmaganlar) ────
        day_ago = timezone.now() - timedelta(hours=24)
        sent_today = ArticleSubmission.objects.filter(
            chat_id=chat_id,
            submitted_at__gte=day_ago,
        ).exclude(status='draft').count()
        if sent_today >= DAILY_SUBMIT_LIMIT:
            return Response(
                {'error': 'daily_limit', 'limit': DAILY_SUBMIT_LIMIT},
                status=429,
            )

        sub.status = 'pending'
        sub.submitted_at = timezone.now()

        # ── Author yaratish (yo'q bo'lsa) — endi AdminAuthor/Chat'da ko'rinadi ─
        from apps.authors.models import Author
        if not sub.author and sub.chat_id:
            author, _ = Author.objects.get_or_create(
                telegram_chat_id=sub.chat_id,
                defaults={
                    'name':              sub.tg_name or "Noma'lum muallif",
                    'telegram_username': sub.tg_username or '',
                },
            )
            sub.author = author

        sub.save(update_fields=['status', 'submitted_at', 'author', 'updated_at'])

        # ── Adminlarga rasm + fayl bilan bildirishnoma ───────────────────────
        self._notify_admins(sub)

        return Response(ArticleSubmissionSerializer(sub, context={'request': request}).data, status=200)

    def _notify_admins(self, sub):
        from apps.panel.models import TelegramAdmin
        from utils.telegram import send_photo, send_document

        sender = sub.tg_name or 'Noma\'lum'
        uname  = f"@{sub.tg_username}" if sub.tg_username else '—'

        # Foydalanuvchining oldingi statistikasi
        user_qs   = ArticleSubmission.objects.filter(chat_id=sub.chat_id).exclude(status='draft')
        total     = user_qs.count()
        approved  = user_qs.filter(status='approved').count()

        caption = (
            f"📄 <b>Yangi maqola topshirildi!</b>\n\n"
            f"👤 <b>Yuboruvchi:</b> {sender}\n"
            f"💬 <b>Username:</b> {uname}\n\n"
            f"📊 Ushbu foydalanuvchi: jami <b>{total}</b> ta yuborgan, "
            f"<b>{approved}</b> tasi tasdiqlangan.\n\n"
            f"Tasdiqlash yoki rad etish uchun tizimga o'ting."
        )

        # Inline tugmalar: foydalanuvchi maqolalari (bot ichida) + saytda ko'rish
        markup = {'inline_keyboard': [
            [{'text': '📚 Foydalanuvchi maqolalari', 'callback_data': f'uarts:{sub.chat_id}:1'}],
        ]}

        admin_ids = TelegramAdmin.active_ids()
        if not admin_ids:
            admin_ids = getattr(settings, 'TELEGRAM_ADMIN_IDS', [])

        img_path = sub.image.path if sub.image else None
        doc_path = sub.source_file.path if sub.source_file else None

        for aid in admin_ids:
            sent_caption = False
            if img_path:
                # Rasm + caption + tugmalar
                send_photo(aid, img_path, caption, reply_markup=markup)
                sent_caption = True
            if doc_path:
                # Fayl — caption faqat rasm yuborilmagan bo'lsa
                send_document(aid, doc_path, '' if sent_caption else caption,
                              reply_markup=None if sent_caption else markup)
            if not img_path and not doc_path:
                from utils.telegram import send_message
                send_message(aid, caption)


class SubmissionCancelDraftView(APIView):
    """POST /api/submit/cancel/ — foydalanuvchi qoralamani bekor qildi → o'chiriladi."""
    permission_classes = [AllowAny]

    def post(self, request):
        if not _check_secret(request):
            return Response({'error': 'Forbidden'}, status=403)

        chat_id = request.data.get('chat_id')
        try:
            chat_id = int(chat_id)
        except (TypeError, ValueError):
            return Response({'error': 'chat_id noto\'g\'ri'}, status=400)

        deleted, _ = ArticleSubmission.objects.filter(chat_id=chat_id, status='draft').delete()
        return Response({'deleted': deleted}, status=200)


class BotCheckAdminView(APIView):
    """GET /api/submit/check-admin/?chat_id=&secret= → {is_admin: bool}"""
    permission_classes = [AllowAny]

    def get(self, request):
        if request.query_params.get('secret') != getattr(settings, 'BOT_SECRET', ''):
            return Response({'error': 'Forbidden'}, status=403)
        from apps.panel.models import TelegramAdmin
        try:
            chat_id = int(request.query_params.get('chat_id', ''))
        except (TypeError, ValueError):
            return Response({'is_admin': False})
        is_admin = (
            chat_id in (getattr(settings, 'TELEGRAM_ADMIN_IDS', []))
            or TelegramAdmin.objects.filter(chat_id=chat_id, is_active=True).exists()
        )
        return Response({'is_admin': is_admin})


class BotUserArticlesView(APIView):
    """
    GET /api/submit/user-articles/?chat_id=&secret=&page=
    Foydalanuvchining barcha topshirishlari (paginate, nom + holat).
    Adminlar bot ichida ko'rish uchun.
    """
    permission_classes = [AllowAny]
    PAGE_SIZE = 5

    STATUS_LABEL = {
        'pending': '⏳ Kutilmoqda', 'approved': '✅ Tasdiqlangan',
        'rejected': '❌ Rad etilgan', 'draft': '✏️ Qoralama',
    }

    def get(self, request):
        if request.query_params.get('secret') != getattr(settings, 'BOT_SECRET', ''):
            return Response({'error': 'Forbidden'}, status=403)
        try:
            chat_id = int(request.query_params.get('chat_id', ''))
        except (TypeError, ValueError):
            return Response({'error': 'chat_id noto\'g\'ri'}, status=400)
        try:
            page = max(1, int(request.query_params.get('page', 1)))
        except ValueError:
            page = 1

        qs = (
            ArticleSubmission.objects
            .filter(chat_id=chat_id)
            .exclude(status='draft')
            .order_by('-submitted_at', '-created_at')
        )
        total = qs.count()
        start = (page - 1) * self.PAGE_SIZE
        items = qs[start:start + self.PAGE_SIZE]

        # Foydalanuvchi ma'lumoti (oxirgi topshirishdan)
        latest = qs.first()
        user_info = None
        if latest:
            user_info = {'name': latest.tg_name, 'username': latest.tg_username}

        results = [{
            'title':  s.title or '(sarlavsiz)',
            'status': s.status,
            'status_label': self.STATUS_LABEL.get(s.status, s.status),
            'date':   (s.submitted_at or s.created_at).strftime('%d.%m.%Y'),
        } for s in items]

        return Response({
            'count':     total,
            'page':      page,
            'num_pages': max(1, (total + self.PAGE_SIZE - 1) // self.PAGE_SIZE),
            'user':      user_info,
            'results':   results,
        })
