from django.db.models import Q
from django.utils import timezone
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework_simplejwt.views import TokenObtainPairView
from django.conf import settings

from apps.articles.models import Article, ArticleSubmission, Category, Keyword, ParsedArticle
from apps.authors.models import Author
from apps.journals.models import Journal, Issue
from utils.telegram import send_message as tg_send
from .serializers import (
    AdminAuthorSerializer,
    AdminArticleInIssueSerializer,
    AdminSubmissionSerializer,
    AdminIssueSerializer,
    AdminCategorySerializer,
    ParsedArticleSerializer,
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
    Telegram orqali submission yuborgan mualliflar + qo'lda/parser profillar.
    Pagination: offset/limit (infinite scroll uchun).
    """
    from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
    parser_classes     = [MultiPartParser, FormParser, JSONParser]
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

        # Telegram orqali submission yuborganlar YOKI qo'lda/parser profillari
        qs = (
            Author.objects
            .filter(
                Q(telegram_chat_id__isnull=False, submissions__isnull=False) |
                Q(telegram_chat_id__isnull=True)
            )
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
        data  = AdminAuthorSerializer(page, many=True, context={'request': request}).data

        next_offset = offset + len(data)
        return Response({
            'results':     data,
            'total':       total,
            'has_more':    next_offset < total,
            'next_offset': next_offset,
        })

    def post(self, request):
        """Qo'lda muallif yaratish — to'g'ridan-to'g'ri tasdiqlangan, Telegramsiz."""
        s = AdminAuthorSerializer(data=request.data, context={'request': request})
        s.is_valid(raise_exception=True)
        # Manba 'manual' — Telegram maydonlari hech qachon o'rnatilmaydi (read-only)
        author = s.save(source='manual')
        if 'avatar' in request.FILES:
            author.avatar = request.FILES['avatar']
            author.save(update_fields=['avatar', 'updated_at'])
        return Response(
            AdminAuthorSerializer(author, context={'request': request}).data,
            status=201,
        )


class AdminAuthorDetailView(APIView):
    from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
    parser_classes     = [MultiPartParser, FormParser, JSONParser]
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
        s = AdminAuthorSerializer(obj, data=request.data, partial=True, context={'request': request})
        s.is_valid(raise_exception=True)
        s.save()
        if 'avatar' in request.FILES:
            obj.avatar = request.FILES['avatar']
            obj.save(update_fields=['avatar', 'updated_at'])
        return Response(AdminAuthorSerializer(obj, context={'request': request}).data)

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
    Local LLM (Ollama) yordamida fayldan sarlavha, mualliflar, kalit so'zlar,
    annotatsiya, adabiyotlarni ajratib submissionga yozadi. Fayl (PDF/DOCX)
    to'g'ridan-to'g'ri LLM ga yuboriladi. Category AI ajratmaydi (admin tanlaydi).
    """
    permission_classes = [IsStaff]

    def post(self, request, pk):
        import logging
        logger = logging.getLogger(__name__)

        from utils.local_llm import extract_metadata_from_file

        try:
            sub = ArticleSubmission.objects.get(pk=pk)
        except ArticleSubmission.DoesNotExist:
            return Response({'error': 'Topilmadi'}, status=404)

        if not sub.source_file:
            return Response({'error': 'Fayl topilmadi'}, status=400)

        # Local LLM — har qanday xato (upload, timeout, query) — JSON javob
        try:
            result = extract_metadata_from_file(sub.source_file)
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
        # cover_image / pdf_file multipart bo'lsa
        upd = []
        if 'cover_image' in request.FILES:
            issue.cover_image = request.FILES['cover_image']
            upd.append('cover_image')
        if 'pdf_file' in request.FILES:
            issue.pdf_file = request.FILES['pdf_file']
            upd.append('pdf_file')
        if upd:
            issue.save(update_fields=[*upd, 'updated_at'])
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
        # cover_image / pdf_file fayl (multipart) bo'lsa alohida saqlaymiz
        upd = []
        if 'cover_image' in request.FILES:
            issue.cover_image = request.FILES['cover_image']
            upd.append('cover_image')
        if 'pdf_file' in request.FILES:
            issue.pdf_file = request.FILES['pdf_file']
            upd.append('pdf_file')
        if upd:
            issue.save(update_fields=[*upd, 'updated_at'])
        return Response(AdminIssueSerializer(issue, context={'request': request}).data)

    def delete(self, request, pk):
        issue = self._get(pk)
        if not issue:
            return Response({'error': 'Topilmadi'}, status=404)
        # Bot orqali yuborilgan (submission'li) maqolalar SAQLANADI — faqat uziladi,
        # PDF'dan ajratilgan / qo'lda kiritilgan maqolalar esa TO'LIQ o'chiriladi
        # (aks holda ular profilga bog'liq bo'lib qolib ketadi).
        for art in issue.articles.all():
            if ArticleSubmission.objects.filter(article=art).exists():
                art.issue = None
                art.published_at = None
                art.save(update_fields=['issue', 'published_at', 'updated_at'])
            else:
                art.delete()
        issue.delete()  # qolgan ParsedArticle satrlari CASCADE bilan o'chadi
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


class AdminArticleCreateView(APIView):
    """
    POST /api/admin/articles/  (multipart)
    Maqolani qo'lda yaratish. Muallif ixtiyoriy (noma'lum bo'lishi mumkin).
    Maydonlar:
      title*          — sarlavha
      author_names    — mualliflar (matn, vergul bilan; ixtiyoriy)
      excerpt         — annotatsiya (ixtiyoriy)
      keywords        — kalit so'zlar (vergul bilan; ixtiyoriy)
      category_id / category_name — yo'nalish (ixtiyoriy)
      source_file     — PDF yoki DOCX (ixtiyoriy)
      issue_id        — darhol jurnal soniga biriktirish (ixtiyoriy)
    """
    from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
    parser_classes     = [MultiPartParser, FormParser, JSONParser]
    permission_classes = [IsStaff]

    def post(self, request):
        title = (request.data.get('title') or '').strip()
        if not title:
            return Response({'error': 'Sarlavha talab qilinadi'}, status=400)

        # ── Category ──────────────────────────────────────────────────────────
        category = None
        cat_id   = request.data.get('category_id')
        cat_name = (request.data.get('category_name') or '').strip()
        if cat_id:
            category = Category.objects.filter(pk=cat_id).first()
        elif cat_name:
            category, _ = Category.objects.get_or_create(name=cat_name)

        # ── Jurnal soni (ixtiyoriy) ───────────────────────────────────────────
        issue = None
        issue_id = request.data.get('issue_id')
        if issue_id:
            issue = Issue.objects.filter(pk=issue_id).first()
            if not issue:
                return Response({'error': 'Jurnal soni topilmadi'}, status=404)

        article = Article(
            title=title,
            excerpt=(request.data.get('excerpt') or '').strip(),
            references=(request.data.get('references') or '').strip(),
            author_names=(request.data.get('author_names') or '').strip(),
            category=category,
            status=request.data.get('status') or 'open',
            year=issue.year if issue else timezone.now().year,
        )
        if 'source_file' in request.FILES:
            article.source_file = request.FILES['source_file']
        if issue:
            article.issue = issue
            article.published_at = timezone.now().date()
        article.save()

        # Keywords → Keyword jadvali
        for name in Keyword.parse_csv(request.data.get('keywords') or ''):
            kw = Keyword.objects.filter(name__iexact=name).first() or Keyword.objects.create(name=name)
            article.keywords.add(kw)

        # Fayl → HTML (article detail fallback uchun)
        if article.source_file:
            try:
                html = article.parse_source_file()
                if html:
                    article.content = html
                    article.save(update_fields=['content', 'updated_at'])
            except Exception:
                pass

        return Response({
            'id':        str(article.id),
            'title':     article.title,
            'slug':      article.slug,
            'issue_id':  str(issue.id) if issue else None,
        }, status=201)


class AdminArticleTrainAIView(APIView):
    """
    POST   /api/admin/articles/<uuid:pk>/train-ai/  — maqola faylini local LLM ga yuklab
                                                     doc_id ni saqlaydi (uzoq operatsiya).
    DELETE /api/admin/articles/<uuid:pk>/train-ai/  — saqlangan doc_id ni tozalaydi
                                                     (publik chat o'chadi).
    """
    permission_classes = [IsStaff]

    def post(self, request, pk):
        from utils.local_llm import upload_and_wait
        try:
            article = Article.objects.get(pk=pk)
        except Article.DoesNotExist:
            return Response({'error': 'Maqola topilmadi'}, status=404)

        if not article.source_file:
            return Response({'error': 'Bu maqolada manba fayl yo\'q'}, status=400)

        doc_id, err = upload_and_wait(article.source_file)
        if err:
            return Response({'error': err}, status=502)

        article.llm_document_id = doc_id
        article.save(update_fields=['llm_document_id', 'updated_at'])
        return Response({
            'id':              str(article.pk),
            'slug':            article.slug,
            'llm_document_id': doc_id,
            'ai_ready':        True,
        })

    def delete(self, request, pk):
        try:
            article = Article.objects.get(pk=pk)
        except Article.DoesNotExist:
            return Response({'error': 'Maqola topilmadi'}, status=404)
        article.llm_document_id = ''
        article.save(update_fields=['llm_document_id', 'updated_at'])
        return Response({'id': str(article.pk), 'ai_ready': False})


# ── Jurnal soni PDF'ini parserlash (maqola + muallif ajratish) ────────────────

class AdminIssueParsePdfView(APIView):
    """
    POST /api/admin/issues/<pk>/parse-pdf/
    Jurnal soni PDF'idan (issue.pdf_file yoki request'dagi pdf_file) maqolalarni
    ajratadi va har biri uchun ParsedArticle (pending) yaratadi.
    """
    from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
    parser_classes     = [MultiPartParser, FormParser, JSONParser]
    permission_classes = [IsStaff]

    def post(self, request, pk):
        import logging
        logger = logging.getLogger(__name__)
        from django.core.files.base import ContentFile
        from utils.journal_parser import parse_journal

        try:
            issue = Issue.objects.get(pk=pk)
        except Issue.DoesNotExist:
            return Response({'error': 'Jurnal soni topilmadi'}, status=404)

        src = request.FILES.get('pdf_file') or (issue.pdf_file if issue.pdf_file else None)
        if not src:
            return Response(
                {'error': "PDF topilmadi. Avval jurnal soniga to'liq PDF yuklang."},
                status=400,
            )

        try:
            candidates = parse_journal(src)
        except Exception as exc:
            logger.exception('parse-pdf: kutilmagan xato')
            return Response({'error': f'Parser xatosi: {exc}'}, status=500)

        if not candidates:
            return Response(
                {'error': "Parser maqola ajrata olmadi. PDF mundarija/format mos kelmasligi "
                          "mumkin — maqolalarni qo'lda qo'shing."},
                status=422,
            )

        # Eski (hali saqlanmagan) nomzodlarni tozalab, qaytadan yaratamiz
        issue.parsed_articles.filter(status='pending').delete()

        created = []
        for c in candidates:
            pa = ParsedArticle(
                issue=issue, order=c['order'], section=c['section'] or '',
                title=c['title'] or '', author_name=c['author_name'] or '',
                extra_info=c['extra_info'] or '',
                start_page=c['start_page'], end_page=c['end_page'],
            )
            base = f"issue-{issue.pk}-{c['order']:02d}"
            pa.article_pdf.save(f'{base}.pdf', ContentFile(c['article_pdf_bytes']), save=False)
            if c.get('photo_png_bytes'):
                pa.photo.save(f'{base}.png', ContentFile(c['photo_png_bytes']), save=False)
            pa.save()
            created.append(pa)

        data = ParsedArticleSerializer(created, many=True, context={'request': request}).data
        return Response({'results': data, 'count': len(data)}, status=201)


class AdminIssueParsedListView(APIView):
    """GET /api/admin/issues/<pk>/parsed/ — shu son uchun ajratilgan nomzodlar."""
    permission_classes = [IsStaff]

    def get(self, request, pk):
        try:
            issue = Issue.objects.get(pk=pk)
        except Issue.DoesNotExist:
            return Response({'error': 'Jurnal soni topilmadi'}, status=404)
        qs = issue.parsed_articles.exclude(status='skipped').order_by('order')
        return Response({
            'results': ParsedArticleSerializer(qs, many=True, context={'request': request}).data,
        })


class AdminParsedDetailView(APIView):
    """
    PATCH  /api/admin/parsed/<pk>/  — nomzod maydonlarini tahrirlash (qo'lda to'ldirish).
    DELETE /api/admin/parsed/<pk>/  — nomzodni o'tkazib yuborish (o'chirish).
    """
    permission_classes = [IsStaff]
    EDITABLE = ('title', 'author_name', 'extra_info', 'section')

    def _get(self, pk):
        try:
            return ParsedArticle.objects.get(pk=pk)
        except ParsedArticle.DoesNotExist:
            return None

    def patch(self, request, pk):
        pa = self._get(pk)
        if not pa:
            return Response({'error': 'Topilmadi'}, status=404)
        for f in self.EDITABLE:
            if f in request.data:
                setattr(pa, f, request.data[f])
        pa.save()
        return Response(ParsedArticleSerializer(pa, context={'request': request}).data)

    def delete(self, request, pk):
        pa = self._get(pk)
        if not pa:
            return Response({'error': 'Topilmadi'}, status=404)
        pa.delete()
        return Response(status=204)


class AdminParsedSaveView(APIView):
    """
    POST /api/admin/parsed/<pk>/save/
    Body: {
      author_mode: 'existing' | 'new' | 'none',
      author_id?: uuid,                    # existing uchun
      author?: {name, role, org, degree, bio},  # new uchun
      title?, author_name?, extra_info?    # tahrirlangan maydonlar (ixtiyoriy)
    }
    Nomzoddan Article yaratadi va muallifni biriktiradi (mavjud yoki yangi profil).
    """
    permission_classes = [IsStaff]

    def post(self, request, pk):
        try:
            pa = ParsedArticle.objects.select_related('issue').get(pk=pk)
        except ParsedArticle.DoesNotExist:
            return Response({'error': 'Topilmadi'}, status=404)

        if pa.status == 'saved' and pa.article_id:
            return Response({'error': 'Bu nomzod allaqachon saqlangan'}, status=400)

        # Tahrirlangan maydonlarni qabul qilamiz
        for f in ('title', 'author_name', 'extra_info', 'section'):
            if f in request.data and request.data.get(f) is not None:
                setattr(pa, f, request.data.get(f))

        issue = pa.issue
        mode  = request.data.get('author_mode', 'new')

        # ── Muallifni aniqlash ────────────────────────────────────────────────
        author = None
        if mode == 'existing':
            author = (
                Author.objects
                .filter(pk=request.data.get('author_id'), telegram_chat_id__isnull=True)
                .first()
            )
            if not author:
                return Response(
                    {'error': 'Tanlangan profil topilmadi (yoki Telegramga tegishli)'},
                    status=400,
                )
            # Profilda rasm yo'q bo'lsa — parser ajratgan rasmni qo'yamiz
            if not author.avatar and pa.photo:
                author.avatar = pa.photo.name
                author.save(update_fields=['avatar', 'updated_at'])
        elif mode == 'new':
            ap   = request.data.get('author') or {}
            if not isinstance(ap, dict):
                ap = {}
            name = (ap.get('name') or pa.author_name or '').strip() or "Noma'lum muallif"
            author = Author(
                source='parser',
                name=name,
                role=(ap.get('role') or '').strip(),
                org=(ap.get('org') or '').strip(),
                degree=(ap.get('degree') or '').strip(),
                bio=(ap.get('bio') or pa.extra_info or '').strip(),
            )
            if pa.photo:
                author.avatar = pa.photo.name
            author.save()
        # mode == 'none' -> profil biriktirilmaydi (faqat matn nomi)

        # ── Maqola yaratish ───────────────────────────────────────────────────
        article = Article(
            title=pa.title or (f'{pa.author_name} maqolasi' if pa.author_name else 'Maqola'),
            status='open',
            year=issue.year,
            img_variant=(pa.order or 1) % 4,
            issue=issue,
            published_at=timezone.now().date(),
        )
        if pa.article_pdf:
            article.source_file = pa.article_pdf.name
        if not author:
            article.author_names = pa.author_name or ''
        article.save()

        if author:
            article.authors.add(author)

        # PDF/DOCX -> HTML (detalda fallback; PDF bo'lsa PdfViewer ko'rsatadi)
        try:
            html = article.parse_source_file()
            if html:
                article.content = html
                article.save(update_fields=['content', 'updated_at'])
        except Exception:
            pass

        pa.status  = 'saved'
        pa.article = article
        pa.save()

        return Response(ParsedArticleSerializer(pa, context={'request': request}).data)
