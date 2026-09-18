import re
from collections import OrderedDict

from rest_framework import serializers

from .models import Journal, Issue


class IssueSerializer(serializers.ModelSerializer):
    article_count   = serializers.IntegerField(read_only=True)
    cover_image_url = serializers.SerializerMethodField()
    pdf_file_url    = serializers.SerializerMethodField()
    journal_id      = serializers.SerializerMethodField()
    journal_title   = serializers.SerializerMethodField()

    def _abs(self, f):
        if not f:
            return None
        request = self.context.get('request')
        return request.build_absolute_uri(f.url) if request else f.url

    def get_cover_image_url(self, obj) -> str | None:
        return self._abs(obj.cover_image)

    def get_pdf_file_url(self, obj) -> str | None:
        return self._abs(obj.pdf_file)

    def get_journal_id(self, obj) -> str | None:
        return str(obj.journal_id) if obj.journal_id else None

    def get_journal_title(self, obj) -> str | None:
        return obj.journal.title if obj.journal_id else None

    class Meta:
        model  = Issue
        fields = (
            'id', 'volume', 'number', 'year', 'season',
            'date_label', 'palette', 'is_current', 'is_upcoming',
            'article_count', 'total_pages', 'views',
            'cover_image_url', 'pdf_file_url',
            'journal_id', 'journal_title',
        )


def _lang_code(title: str) -> str:
    """Sarlavhadan til kodi — jadvalda «UZ · RU · EN» ko'rinishida chiqadi."""
    if re.search(r'[ўқғҳЎҚҒҲ]', title):
        return 'ЎЗ'
    if re.search(r'[а-яА-ЯёЁ]', title):
        return 'RU'
    if re.search(r"[‘’']|\b(va|bilan|uchun|kutubxona)\b", title, re.I):
        return 'UZ'
    if re.search(r'\b(the|and|of|in|for|with|study|library)\b', title, re.I):
        return 'EN'
    return 'UZ'


class IssueDetailSerializer(IssueSerializer):
    """
    Son sahifasi (Figma: «Jurnal arxiv detail»).

    Qo'shimcha:
      • tahririyat so'zi va muharrir
      • mundarija — yo'nalishlar bo'yicha guruhlangan, bet oralig'i bilan
      • sondagi yo'nalishlar soni, tillar
      • oldingi / keyingi son (navigatsiya tugmalari uchun)
      • jurnal ISSN va PDF hajmi
    """
    editorial_note = serializers.CharField(read_only=True)
    editor_name    = serializers.CharField(read_only=True)
    issn           = serializers.SerializerMethodField()
    pdf_size       = serializers.SerializerMethodField()
    sections       = serializers.SerializerMethodField()
    categories     = serializers.SerializerMethodField()
    languages      = serializers.SerializerMethodField()
    prev_issue     = serializers.SerializerMethodField()
    next_issue     = serializers.SerializerMethodField()

    class Meta(IssueSerializer.Meta):
        fields = IssueSerializer.Meta.fields + (
            'editorial_note', 'editor_name', 'issn', 'pdf_size',
            'sections', 'categories', 'languages', 'prev_issue', 'next_issue',
        )

    def get_issn(self, obj) -> str:
        return obj.journal.issn if obj.journal_id else ''

    def get_pdf_size(self, obj) -> int | None:
        if not obj.pdf_file:
            return None
        try:
            return obj.pdf_file.size
        except (OSError, ValueError):
            return None

    # ── Mundarija ────────────────────────────────────────────────────────────

    def _articles(self, obj):
        # Bet boshlanishi bo'yicha, bo'lmasa yaratilish tartibida
        return (
            obj.articles
            .select_related('category')
            .prefetch_related('authors')
            .order_by('page_start', 'created_at')
        )

    def get_sections(self, obj) -> list:
        from apps.articles.serializers import ArticleTocSerializer

        groups: OrderedDict[str, dict] = OrderedDict()
        for art in self._articles(obj):
            key = art.category.name if art.category_id else 'Boshqa'
            g = groups.setdefault(key, {
                'category': key, 'articles': [], 'page_start': None, 'page_end': None,
            })
            g['articles'].append(art)
            if art.page_start:
                g['page_start'] = art.page_start if g['page_start'] is None else min(g['page_start'], art.page_start)
            if art.page_end:
                g['page_end'] = art.page_end if g['page_end'] is None else max(g['page_end'], art.page_end)

        return [{
            'category':   g['category'],
            'page_start': g['page_start'],
            'page_end':   g['page_end'],
            'articles':   ArticleTocSerializer(g['articles'], many=True, context=self.context).data,
        } for g in groups.values()]

    def get_categories(self, obj) -> list:
        counts: dict[str, int] = {}
        for art in obj.articles.select_related('category'):
            key = art.category.name if art.category_id else 'Boshqa'
            counts[key] = counts.get(key, 0) + 1
        return [{'name': k, 'count': v} for k, v in sorted(counts.items(), key=lambda x: -x[1])]

    def get_languages(self, obj) -> list:
        langs: list[str] = []
        for art in obj.articles.all():
            code = _lang_code(art.title)
            if code not in langs:
                langs.append(code)
        return langs

    # ── Navigatsiya ──────────────────────────────────────────────────────────

    def _neighbor(self, obj, forward: bool):
        base = Issue.objects.filter(journal_id=obj.journal_id)
        if forward:
            qs = base.filter(year__gt=obj.year) | base.filter(year=obj.year, number__gt=obj.number)
            n = qs.order_by('year', 'number').first()
        else:
            qs = base.filter(year__lt=obj.year) | base.filter(year=obj.year, number__lt=obj.number)
            n = qs.order_by('-year', '-number').first()
        if not n:
            return None
        return {'id': str(n.id), 'number': n.number, 'year': n.year, 'is_upcoming': n.is_upcoming}

    def get_prev_issue(self, obj) -> dict | None:
        return self._neighbor(obj, forward=False)

    def get_next_issue(self, obj) -> dict | None:
        return self._neighbor(obj, forward=True)


class JournalSerializer(serializers.ModelSerializer):
    issues = IssueSerializer(many=True, read_only=True)

    class Meta:
        model  = Journal
        fields = ('id', 'title', 'issn', 'issues')
