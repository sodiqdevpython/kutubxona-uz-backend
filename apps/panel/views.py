from django.db.models import Q
from django.utils import timezone
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework_simplejwt.views import TokenObtainPairView
from django.conf import settings

from apps.articles.models import Article, ArticleSubmission, Category, Keyword
from apps.authors.models import Author
from apps.journals.models import Journal, Issue
from utils.telegram import send_message as tg_send
from .serializers import (
    AdminAuthorSerializer,
    AdminArticleInIssueSerializer,
    AdminSubmissionSerializer,
    AdminIssueSerializer,
    AdminCategorySerializer,
)


# ── Ruxsat ────────────────────────────────────────────────────────────────────

class IsStaff(IsAuthenticated):
    """Faqat is_staff=True bo'lgan foydalanuvchilarga ruxsat."""
    def has_permission(self, request, view):
        return super().has_permission(request, view) and bool(request.user.is_staff)


# ── Auth ──────────────────────────────────────────────────────────────────────

class AdminTokenObtainPairSerializer(TokenObtainPairSerializer):
    def validate(self, attrs):
        data = super().validate(attrs)
        if not self.user.is_staff:
            raise AuthenticationFailed(
                'Faqat adminlar kirishiga ruxsat berilgan.',
                code='not_admin',
            )
        data['username'] = self.user.username
        data['is_superuser'] = self.user.is_superuser
        return data


class AdminLoginView(TokenObtainPairView):
    serializer_class = AdminTokenObtainPairSerializer


class CurrentUserView(APIView):
    permission_classes = [IsStaff]

    def get(self, request):
        u = request.user
        return Response({
            'id': u.id, 'username': u.username,
            'email': u.email,
            'is_staff': u.is_staff, 'is_superuser': u.is_superuser,
        })


# ── Mualliflar ────────────────────────────────────────────────────────────────

class AdminAuthorListView(APIView):
    """
    GET /api/admin/authors/?offset=0&limit=20&search=…
    Faqat Telegram bot orqali submission yuborgan mualliflarni qaytaradi.
    Pagination: offset/limit (infinite scroll uchun).
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

        # Faqat Telegram orqali kelganlar (chat_id bor) VA submission yuborganlar
        qs = (
            Author.objects
            .filter(telegram_chat_id__isnull=False, submissions__isnull=False)
            .distinct()
            .prefetch_related('articles')
            .order_by('-created_at')
        )

        search = (request.query_params.get('search') or '').strip()
        if search:
            qs = qs.filter(
                Q(name__icontains=search) |
                Q(telegram_username__icontains=search) |
                Q(org__icontains=search)
            )

        total = qs.count()
        page  = qs[offset:offset + limit]
        data  = AdminAuthorSerializer(page, many=True).data

        next_offset = offset + len(data)
        return Response({
            'results':     data,
            'total':       total,
            'has_more':    next_offset < total,
            'next_offset': next_offset,
        })

    def post(self, request):
        s = AdminAuthorSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        author = s.save()
        return Response(
            AdminAuthorSerializer(author).data,
            status=201,
        )


class AdminAuthorDetailView(APIView):
    permission_classes = [IsStaff]

    def _get(self, pk):
        try:
            return Author.objects.prefetch_related('articles').get(pk=pk)
        except Author.DoesNotExist:
            return None

    def patch(self, request, pk):
        obj = self._get(pk)
        if not obj:
            return Response({'error': 'Topilmadi'}, status=404)
        s = AdminAuthorSerializer(obj, data=request.data, partial=True)
        s.is_valid(raise_exception=True)
        s.save()
        return Response(s.data)

    def delete(self, request, pk):
        obj = self._get(pk)
        if not obj:
            return Response({'error': 'Topilmadi'}, status=404)
        mode = request.query_params.get('mode', 'soft')
        if mode == 'full':
            # U muallif bo'lgan BARCHA maqolalarni o'chirish
            Article.objects.filter(authors=obj).delete()
        obj.delete()
        return Response(status=204)


# ── Topshirishlar ─────────────────────────────────────────────────────────────

class AdminSubmissionListView(APIView):
    """
    GET /api/admin/submissions/?status=&search=&page=&page_size=
    Draft holatidagilar admin ro'yxatida ko'rinmaydi.
    """
    permission_classes = [IsStaff]

    def get(self, request):
        qs = (
            ArticleSubmission.objects
            .exclude(status='draft')
            .select_related('author', 'article', 'article__issue', 'article__category')
            .order_by('-submitted_at', '-created_at')
        )

        st = request.query_params.get('status')
        if st and st != 'all':
            qs = qs.filter(status=st)

        search = (request.query_params.get('search') or '').strip()
        if search:
            qs = qs.filter(
                Q(title__icontains=search) |
                Q(tg_name__icontains=search) |
                Q(tg_username__icontains=search) |
                Q(keywords__icontains=search)
            )

        # Pagination
        try:
            page      = max(1, int(request.query_params.get('page', 1)))
            page_size = min(50, max(1, int(request.query_params.get('page_size', 10))))
        except ValueError:
            page, page_size = 1, 10

        total = qs.count()
        start = (page - 1) * page_size
        items = qs[start:start + page_size]

        return Response({
            'count':    total,
            'page':     page,
            'page_size': page_size,
            'num_pages': (total + page_size - 1) // page_size,
            'results':  AdminSubmissionSerializer(items, many=True, context={'request': request}).data,
        })


class AdminSubmissionApproveView(APIView):
    """
    POST /api/admin/submissions/<pk>/approve/
    Body: { category_id?: uuid, category_name?: str }
    Maqola yaratadi, keywords ni Keyword jadvaliga ko'chiradi, category belgilaydi.
    """
    permission_classes = [IsStaff]

    def post(self, request, pk):
        try:
            sub = ArticleSubmission.objects.select_related('author').get(pk=pk)
        except ArticleSubmission.DoesNotExist:
            return Response({'error': 'Topilmadi'}, status=404)

        if sub.status != 'pending':
            return Response({'error': 'Faqat kutilayotgan topshirishni tasdiqlash mumkin'}, status=400)

        # ── Category ──────────────────────────────────────────────────────────
        category = None
        cat_id   = request.data.get('category_id')
        cat_name = (request.data.get('category_name') or '').strip()
        if cat_id:
            category = Category.objects.filter(pk=cat_id).first()
        elif cat_name:
            category, _ = Category.objects.get_or_create(name=cat_name)

        # ── Telegram egasi (profil) ───────────────────────────────────────────
        tg_author = sub.author
        if not tg_author and sub.chat_id:
            tg_author, _ = Author.objects.get_or_create(
                telegram_chat_id=sub.chat_id,
                defaults={
                    'name': sub.tg_name or "Noma'lum muallif",
                    'telegram_username': sub.tg_username or '',
                },
            )
            sub.author = tg_author

        # ── Maqola yaratish ───────────────────────────────────────────────────
        if not sub.article:
            article = Article(
                title=sub.title or (f"{tg_author.name}ning maqolasi" if tg_author else 'Maqola'),
                excerpt=sub.abstract or '',
                references=sub.references or '',
                author_names=sub.extracted_authors or '',   # AI mualliflar — matn (profilsiz)
                category=category,
                status='open',
                year=timezone.now().year,
            )
            if sub.source_file:
                article.source_file = sub.source_file.name
            # Muallif yuborgan rasmni maqolaga ko'chirish
            if sub.image:
                article.image = sub.image.name
            article.save()

            # Profil egasi = Telegram orqali yuborgan shaxs (AI mualliflarga profil ochilmaydi)
            if tg_author:
                article.authors.add(tg_author)

            # Keywords → Keyword jadvali (faqat tasdiqlangan maqolalardagilar)
            for name in sub.keywords_list:
                kw = Keyword.objects.filter(name__iexact=name).first()
                if kw is None:
                    kw = Keyword.objects.create(name=name)
                article.keywords.add(kw)

            # DOCX/PDF → HTML (fallback uchun)
            try:
                html = article.parse_source_file()
                if html:
                    article.content = html
                    article.save(update_fields=['content', 'updated_at'])
            except Exception:
                pass

            sub.article = article
        else:
            # Maqola allaqachon bor — category ni yangilash
            if category:
                sub.article.category = category
                sub.article.save(update_fields=['category', 'updated_at'])

        sub.status = 'approved'
        sub.save()

        if sub.chat_id:
            tg_send(
                sub.chat_id,
                "✅ <b>Maqolangiz tasdiqlandi!</b>\n\n"
                "Tahrir tomonidan ko'rib chiqildi va arxivga qabul qilindi. "
                "Jurnal soniga kiritilgandan so'ng saytda e'lon qilinadi.",
            )

        return Response(AdminSubmissionSerializer(sub, context={'request': request}).data)


class AdminSubmissionAIExtractView(APIView):
    """
    POST /api/admin/submissions/<pk>/ai-extract/
    Gemini yordamida fayldan sarlavha, mualliflar, kalit so'zlar, annotatsiya,
    adabiyotlarni ajratib submissionga yozadi. Category AI ajratmaydi (admin tanlaydi).
    """
    permission_classes = [IsStaff]

    def post(self, request, pk):
        import logging
        logger = logging.getLogger(__name__)

        from utils.gemini import extract_metadata
        from utils.extract import extract_text

        try:
            sub = ArticleSubmission.objects.get(pk=pk)
        except ArticleSubmission.DoesNotExist:
            return Response({'error': 'Topilmadi'}, status=404)

        # Matn — saqlangan bo'lsa o'shani, bo'lmasa fayldan qayta ajratamiz
        try:
            text = sub.extracted_text
            if not text and sub.source_file:
                text = extract_text(sub.source_file)
                if text:
                    sub.extracted_text = text
                    sub.save(update_fields=['extracted_text', 'updated_at'])
        except Exception as exc:
            logger.exception("AI extract: faylni o‘qib bo‘lmadi")
            return Response({'error': f'Faylni o‘qib bo‘lmadi: {exc}'}, status=500)

        if not text:
            return Response({'error': 'Fayldan matn ajratib bo‘lmadi'}, status=400)

        # Gemini API — har qanday xato (timeout, key, quota) — JSON javob
        try:
            result = extract_metadata(text)
        except Exception as exc:
            logger.exception("AI extract: kutilmagan xato")
            return Response({'error': f'Server xatosi: {exc}'}, status=500)

        if not result.get('ok'):
            logger.warning("AI extract: %s", result.get('error'))
            return Response({'error': result.get('error', 'AI xatosi')}, status=502)

        # Submissionga yozish
        try:
            sub.title             = result['title'] or sub.title
            sub.keywords          = ', '.join(result['keywords'])
            sub.abstract          = result['abstract']
            sub.references        = result['references']
            sub.extracted_authors = ', '.join(result['authors'])
            sub.ai_filled         = True
            sub.save()
        except Exception as exc:
            logger.exception("AI extract: submissionga yozib bo‘lmadi")
            return Response({'error': f'Saqlashda xato: {exc}'}, status=500)

        return Response(AdminSubmissionSerializer(sub, context={'request': request}).data)


class AdminSubmissionUpdateView(APIView):
    """
    PATCH  /api/admin/submissions/<pk>/  — AI ajratgan ma'lumotlarni tahrirlash.
    DELETE /api/admin/submissions/<pk>/  — submissionni butunlay o'chirish.
    """
    permission_classes = [IsStaff]

    EDITABLE = ('title', 'keywords', 'abstract', 'references', 'extracted_authors')

    def patch(self, request, pk):
        try:
            sub = ArticleSubmission.objects.get(pk=pk)
        except ArticleSubmission.DoesNotExist:
            return Response({'error': 'Topilmadi'}, status=404)

        for f in self.EDITABLE:
            if f in request.data:
                setattr(sub, f, request.data[f])
        sub.save()
        return Response(AdminSubmissionSerializer(sub, context={'request': request}).data)

    def delete(self, request, pk):
        try:
            sub = ArticleSubmission.objects.get(pk=pk)
        except ArticleSubmission.DoesNotExist:
            return Response({'error': 'Topilmadi'}, status=404)

        # Bog'langan article'ni topib o'chiramiz (OneToOne related yoki revert qilingan eski)
        if sub.article_id:
            Article.objects.filter(pk=sub.article_id).delete()
        # Ehtiyot uchun: submission orqali yaratilgan, lekin field None bo'lib qolgan article'lar
        Article.objects.filter(submission=sub).delete()

        sub.delete()
        return Response(status=204)


class AdminSubmissionRejectView(APIView):
    """POST /api/admin/submissions/<pk>/reject/ — kutilayotganni rad etadi."""
    permission_classes = [IsStaff]

    def post(self, request, pk):
        try:
            sub = ArticleSubmission.objects.get(pk=pk)
        except ArticleSubmission.DoesNotExist:
            return Response({'error': 'Topilmadi'}, status=404)

        if sub.status != 'pending':
            return Response({'error': 'Faqat kutilayotgan topshirishni rad etish mumkin'}, status=400)

        reason = (request.data.get('reason') or '').strip()
        sub.status = 'rejected'
        sub.reject_reason = reason
        sub.save()

        if sub.chat_id:
            msg = f"❌ <b>Maqolangiz rad etildi.</b>\n\nSabab: {reason}\nXatoni to'g'irlab qayta urinib ko'ring" if reason \
                  else "❌ <b>Maqolangiz rad etildi.</b>\n\nBatafsil ma'lumot uchun tahririyat bilan bog'laning."
            tg_send(sub.chat_id, msg)

        return Response(AdminSubmissionSerializer(sub, context={'request': request}).data)


class AdminSubmissionRevertView(APIView):
    """
    POST /api/admin/submissions/<pk>/revert/
    Tasdiqlangan topshirishni ortga qaytaradi (sabab bilan).
    Yaratilgan maqola o'chiriladi, status → 'rejected'. Foydalanuvchiga xabar boradi.
    """
    permission_classes = [IsStaff]

    def post(self, request, pk):
        try:
            sub = ArticleSubmission.objects.select_related('article').get(pk=pk)
        except ArticleSubmission.DoesNotExist:
            return Response({'error': 'Topilmadi'}, status=404)

        if sub.status != 'approved':
            return Response({'error': 'Faqat tasdiqlangan topshirishni qaytarish mumkin'}, status=400)

        reason = (request.data.get('reason') or '').strip()

        # Yaratilgan maqolani o'chirish (jurnaldan ham chiqib ketadi)
        if sub.article:
            sub.article.delete()
            sub.article = None

        sub.status = 'rejected'
        sub.reject_reason = reason
        sub.save()

        if sub.chat_id:
            msg = (
                f"⚠️ <b>Maqolangiz tasdiqdan qaytarildi.</b>\n\nSabab: {reason}"
                if reason else
                "⚠️ <b>Maqolangiz tasdiqdan qaytarildi.</b>\n\n"
                "Batafsil ma'lumot uchun tahririyat bilan bog'laning."
            )
            tg_send(sub.chat_id, msg)

        return Response(AdminSubmissionSerializer(sub, context={'request': request}).data)


# ── Yo'nalishlar (category) ───────────────────────────────────────────────────

class AdminCategoryListView(APIView):
    permission_classes = [IsStaff]

    def get(self, request):
        qs = Category.objects.all().order_by('name')
        return Response(AdminCategorySerializer(qs, many=True).data)

    def post(self, request):
        name = (request.data.get('name') or '').strip()
        if not name:
            return Response({'error': 'Nom talab qilinadi'}, status=400)
        cat, _ = Category.objects.get_or_create(name=name)
        return Response(AdminCategorySerializer(cat).data, status=201)


# ── Jurnal sonlari ────────────────────────────────────────────────────────────

class AdminJournalListView(APIView):
    permission_classes = [IsStaff]

    def get(self, request):
        journals = Journal.objects.all()
        return Response([{'id': str(j.id), 'title': j.title, 'issn': j.issn} for j in journals])


class AdminIssueListView(APIView):
    from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
    parser_classes     = [MultiPartParser, FormParser, JSONParser]
    permission_classes = [IsStaff]

    def get(self, request):
        qs = Issue.objects.select_related('journal').prefetch_related('articles').order_by('-year', '-number')
        return Response(AdminIssueSerializer(qs, many=True, context={'request': request}).data)

    def post(self, request):
        journal_id = request.data.get('journal_id')
        if journal_id:
            try:
                journal = Journal.objects.get(pk=journal_id)
            except Journal.DoesNotExist:
                return Response({'error': 'Jurnal topilmadi'}, status=404)
        else:
            journal = Journal.objects.first()
            if not journal:
                journal = Journal.objects.create(title='Kutubxona Arxivi')

        data = {k: v for k, v in request.data.items() if k != 'journal_id'}
        data['journal'] = str(journal.id)

        s = AdminIssueSerializer(data=data, context={'request': request})
        s.is_valid(raise_exception=True)
        issue = s.save(journal=journal)
        # cover_image multipart bo'lsa
        if 'cover_image' in request.FILES:
            issue.cover_image = request.FILES['cover_image']
            issue.save(update_fields=['cover_image', 'updated_at'])
        return Response(AdminIssueSerializer(issue, context={'request': request}).data, status=201)


class AdminIssueDetailView(APIView):
    from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
    parser_classes     = [MultiPartParser, FormParser, JSONParser]
    permission_classes = [IsStaff]

    def _get(self, pk):
        try:
            return Issue.objects.select_related('journal').prefetch_related('articles__authors', 'articles__category').get(pk=pk)
        except Issue.DoesNotExist:
            return None

    def get(self, request, pk):
        issue = self._get(pk)
        if not issue:
            return Response({'error': 'Topilmadi'}, status=404)
        articles = issue.articles.prefetch_related('authors', 'category').all()
        return Response({
            **AdminIssueSerializer(issue, context={'request': request}).data,
            'articles': AdminArticleInIssueSerializer(articles, many=True).data,
        })

    def patch(self, request, pk):
        issue = self._get(pk)
        if not issue:
            return Response({'error': 'Topilmadi'}, status=404)
        s = AdminIssueSerializer(issue, data=request.data, partial=True, context={'request': request})
        s.is_valid(raise_exception=True)
        s.save()
        # cover_image fayl (multipart) bo'lsa alohida saqlaymiz
        if 'cover_image' in request.FILES:
            issue.cover_image = request.FILES['cover_image']
            issue.save(update_fields=['cover_image', 'updated_at'])
        return Response(AdminIssueSerializer(issue, context={'request': request}).data)

    def delete(self, request, pk):
        issue = self._get(pk)
        if not issue:
            return Response({'error': 'Topilmadi'}, status=404)
        # Maqolalarni issue dan uzish (ular saqlanib qoladi, lekin ko'rinmaydi)
        issue.articles.update(issue=None, published_at=None)
        issue.delete()
        return Response(status=204)


class AdminIssueAssignArticleView(APIView):
    """Maqolani jurnal soniga qo'shish (drag-drop endpointı)."""
    permission_classes = [IsStaff]

    def post(self, request, pk):
        try:
            issue = Issue.objects.get(pk=pk)
        except Issue.DoesNotExist:
            return Response({'error': 'Jurnal soni topilmadi'}, status=404)

        article_id = request.data.get('article_id')
        if not article_id:
            return Response({'error': 'article_id talab qilinadi'}, status=400)

        try:
            article = Article.objects.get(pk=article_id)
        except Article.DoesNotExist:
            return Response({'error': 'Maqola topilmadi'}, status=404)

        prev_issue_id = article.issue_id
        article.issue       = issue
        article.published_at = article.published_at or timezone.now().date()
        article.year        = issue.year
        article.save(update_fields=['issue', 'published_at', 'year', 'updated_at'])

        # ── Foydalanuvchiga Telegram orqali xabar ────────────────────────────
        # Faqat boshqa jurnaldan kelmagan bo'lsa (yangi nashr)
        if prev_issue_id != issue.pk:
            self._notify_author(article, issue)

        return Response({'success': True, 'article_id': str(article.id), 'issue_id': str(issue.id)})

    def _notify_author(self, article, issue):
        """Maqolaga bog'liq Telegram chat_id'ni topib xabar yuboradi."""
        import logging
        logger = logging.getLogger(__name__)

        chat_ids = set()
        # 1) Submission orqali
        try:
            sub = article.submission
            if sub and sub.chat_id:
                chat_ids.add(sub.chat_id)
        except ArticleSubmission.DoesNotExist:
            pass
        # 2) Author.telegram_chat_id orqali (article.authors)
        for a in article.authors.filter(telegram_chat_id__isnull=False):
            chat_ids.add(a.telegram_chat_id)

        if not chat_ids:
            logger.info("Article '%s' jurnal soniga qo'shildi, lekin chat_id topilmadi", article.title)
            return

        site_url    = getattr(settings, 'SITE_URL', 'http://localhost:5173').rstrip('/')
        article_url = f"{site_url}/articles/{article.slug}"
        issue_label = f"Vol.{issue.volume} №{issue.number} ({issue.year})"
        text = (
            f"📰 <b>Maqolangiz jurnalda chiqdi!</b>\n\n"
            f"📄 <i>{article.title}</i>\n"
            f"📚 {issue_label}\n\n"
            f"🔗 <a href=\"{article_url}\">Saytda o'qish</a>"
        )
        for cid in chat_ids:
            ok = tg_send(cid, text)
            logger.info("Jurnal notification → chat_id=%s | ok=%s", cid, ok)


class AdminIssueRemoveArticleView(APIView):
    """Maqolani jurnal sonidan olib tashlash."""
    permission_classes = [IsStaff]

    def delete(self, request, pk, article_id):
        try:
            issue = Issue.objects.get(pk=pk)
        except Issue.DoesNotExist:
            return Response({'error': 'Jurnal soni topilmadi'}, status=404)
        try:
            article = Article.objects.get(pk=article_id, issue=issue)
        except Article.DoesNotExist:
            return Response({'error': 'Maqola topilmadi'}, status=404)

        article.issue = None
        article.published_at = None
        article.save(update_fields=['issue', 'published_at', 'updated_at'])
        return Response(status=204)
