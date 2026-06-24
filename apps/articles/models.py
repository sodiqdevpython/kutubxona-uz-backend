import os
from django.db import models
from django.utils import timezone
from slugify import slugify
from utils.models import BaseModel


class Category(BaseModel):
    name = models.CharField(max_length=200, verbose_name='Nomi')
    slug = models.SlugField(max_length=220, unique=True, blank=True)

    class Meta:
        verbose_name        = "Yo'nalish"
        verbose_name_plural = "Yo'nalishlar"
        ordering            = ['name']

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name, max_length=210)
        super().save(*args, **kwargs)

    @property
    def article_count(self):
        return self.articles.count()


class Keyword(BaseModel):
    """Kalit so'z — faqat tasdiqlangan maqolalardagilar saqlanadi."""
    name = models.CharField(max_length=120, unique=True, verbose_name='Kalit so\'z')
    slug = models.SlugField(max_length=140, unique=True, blank=True)

    class Meta:
        verbose_name        = 'Kalit so\'z'
        verbose_name_plural = 'Kalit so\'zlar'
        ordering            = ['name']

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            base = slugify(self.name, max_length=130) or 'kw'
            slug, n = base, 1
            while Keyword.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                slug = f'{base}-{n}'
                n += 1
            self.slug = slug
        super().save(*args, **kwargs)

    @property
    def article_count(self):
        return self.articles.filter(issue__isnull=False).count()

    @staticmethod
    def parse_csv(raw: str) -> list[str]:
        """'a, b ,c' → ['a','b','c'] (bo'sh va takrorlanmaslarni filtrlaydi)."""
        seen, out = set(), []
        for part in (raw or '').replace(';', ',').split(','):
            name = part.strip()
            key = name.lower()
            if name and key not in seen:
                seen.add(key)
                out.append(name)
        return out


class ArticleAuthor(BaseModel):
    """Maqola ↔ Muallif (tartibli)"""
    article = models.ForeignKey('Article',        on_delete=models.CASCADE)
    author  = models.ForeignKey('authors.Author', on_delete=models.CASCADE)
    order   = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering            = ['order']
        verbose_name        = 'Maqola muallifi'
        verbose_name_plural = 'Maqola mualliflari'


class Article(BaseModel):
    STATUS_CHOICES = [('open', 'Ochiq kirish'), ('lock', 'Obunachi')]

    # ── Asosiy matn ──────────────────────────────────────────────────────────
    title        = models.CharField(max_length=500, verbose_name='Sarlavha')
    slug         = models.SlugField(max_length=520, unique=True, blank=True, verbose_name='Slug (URL)')
    excerpt      = models.TextField(blank=True, verbose_name='Qisqacha mazmun (abstract)')
    references   = models.TextField(blank=True, verbose_name='Adabiyotlar (References)')
    content      = models.TextField(blank=True, verbose_name="Tarkib (HTML — avtomatik to'ldiriladi)")
    author_names = models.TextField(blank=True, verbose_name='Mualliflar (matn, AI, vergul bilan)')

    image = models.ImageField(
        upload_to='articles/images/%Y/%m/', null=True, blank=True,
        verbose_name='Maqola rasmi (muallif yuborgan)'
    )

    keywords = models.ManyToManyField(
        Keyword, blank=True, related_name='articles', verbose_name='Kalit so\'zlar'
    )

    # ── Manba fayl ────────────────────────────────────────────────────────────
    source_file = models.FileField(
        upload_to='articles/sources/%Y/%m/',
        blank=True, null=True,
        verbose_name='Manba fayl (.docx yoki .pdf)',
        help_text='Faylni saqlashda tarkib (HTML) avtomatik parse qilinadi.'
    )

    # ── Munosabatlar ──────────────────────────────────────────────────────────
    category = models.ForeignKey(
        Category, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='articles', verbose_name="Yo'nalish"
    )
    authors = models.ManyToManyField(
        'authors.Author', through=ArticleAuthor,
        blank=True, related_name='articles', verbose_name='Mualliflar'
    )
    issue = models.ForeignKey(
        'journals.Issue', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='articles',
        verbose_name='Jurnal soni'
    )

    # ── Meta ──────────────────────────────────────────────────────────────────
    # Local LLM hujjat IDsi — birinchi savol berilganda upload qilinadi va shu yerga yoziladi.
    # Keyingi savollar shu IDga query qilib, qayta upload qilmaydi.
    llm_document_id = models.CharField(
        max_length=200, blank=True, default='',
        verbose_name='Local LLM document ID'
    )

    status      = models.CharField(max_length=10, choices=STATUS_CHOICES, default='open', verbose_name='Holat')
    year        = models.PositiveIntegerField(verbose_name='Yil', default=2026)
    quarter     = models.PositiveSmallIntegerField(default=1, verbose_name='Chorak (1–4)')
    pages       = models.PositiveIntegerField(default=0, verbose_name='Sahifalar soni')
    min_read    = models.PositiveIntegerField(default=5,  verbose_name="O'qish (daqiqa)")
    cites       = models.PositiveIntegerField(default=0,  verbose_name='Iqtiboslar')
    views       = models.PositiveIntegerField(default=0,  verbose_name="Ko'rishlar")
    img_variant = models.PositiveSmallIntegerField(default=0, verbose_name='Thumbnail varianti (0–3)')
    published_at = models.DateField(null=True, blank=True, verbose_name='Nashr sanasi')

    class Meta:
        verbose_name        = 'Maqola'
        verbose_name_plural = 'Maqolalar'
        ordering            = ['-created_at']

    def __str__(self):
        return self.title

    def _generate_slug(self) -> str:
        base = slugify(self.title, max_length=490)
        if not base:
            base = str(self.id)
        slug, n = base, 1
        while Article.objects.filter(slug=slug).exclude(pk=self.pk).exists():
            slug = f'{base}-{n}'
            n += 1
        return slug

    def parse_source_file(self) -> str:
        """DOCX yoki PDF faylini HTML ga o'giradi."""
        if not self.source_file:
            return ''
        ext = os.path.splitext(self.source_file.name)[1].lower()
        try:
            if ext == '.docx':
                return self._parse_docx()
            elif ext == '.pdf':
                return self._parse_pdf()
        except Exception as exc:
            return f'<p class="parse-error">Fayl parse qilinmadi: {exc}</p>'
        return ''

    def _parse_docx(self) -> str:
        import mammoth
        self.source_file.open('rb')
        result = mammoth.convert_to_html(self.source_file)
        self.source_file.close()
        return result.value

    def _parse_pdf(self) -> str:
        import fitz  # PyMuPDF
        self.source_file.open('rb')
        raw = self.source_file.read()
        self.source_file.close()
        doc = fitz.open(stream=raw, filetype='pdf')
        paragraphs = []
        for page in doc:
            for b in page.get_text('blocks'):
                text = b[4].strip()
                if text:
                    paragraphs.append(f'<p>{text}</p>')
        return '\n'.join(paragraphs)

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = self._generate_slug()
        super().save(*args, **kwargs)

    @property
    def author_label(self) -> str:
        auths = list(self.authors.all().order_by('articleauthor__order')[:3])
        if not auths:
            return ''

        def fmt(a):
            parts = a.name.split()
            return f'{parts[0][0]}. {parts[-1]}' if len(parts) > 1 else a.name

        shown = auths[:2]
        extra = len(auths) - 2
        label = ', '.join(fmt(a) for a in shown)
        if extra > 0:
            label += f' + {extra}'
        return label

    def increment_views(self):
        Article.objects.filter(pk=self.pk).update(views=models.F('views') + 1)

    @property
    def author_names_list(self) -> list[str]:
        """AI ajratgan mualliflar (matn, profilsiz)."""
        seen, out = set(), []
        for part in (self.author_names or '').replace(';', ',').split(','):
            name = part.strip()
            if name and name.lower() not in seen:
                seen.add(name.lower())
                out.append(name)
        return out


# ── Telegram orqali yuborilgan maqolalar ──────────────────────────────────────

class ArticleSubmission(BaseModel):
    STATUS_CHOICES = [
        ('draft',    'Qoralama'),       # Bot to'ldirayotgan vaqt — hali yuborilmagan
        ('pending',  'Kutilmoqda'),     # Yuborildi, admin ko'rib chiqmoqda
        ('approved', 'Tasdiqlandi'),
        ('rejected', 'Rad etildi'),
    ]

    # Telegram foydalanuvchi ma'lumotlari
    chat_id       = models.BigIntegerField(verbose_name='Telegram chat ID', db_index=True)
    tg_name       = models.CharField(max_length=200, blank=True, verbose_name='Ism (Telegram)')
    tg_username   = models.CharField(max_length=150, blank=True, verbose_name='@username')

    # ── Yuborilgan material ───────────────────────────────────────────────────
    # Bot faqat rasm + fayl yuboradi. Qolgani AI orqali fayldan ajratiladi.
    title       = models.CharField(max_length=500, blank=True, verbose_name='Sarlavha')
    keywords    = models.TextField(blank=True, verbose_name='Kalit so\'zlar (vergul bilan)')
    abstract    = models.TextField(blank=True, verbose_name='Annotatsiya (abstract)')
    references  = models.TextField(blank=True, verbose_name='Adabiyotlar (references)')
    image       = models.ImageField(
        upload_to='submissions/images/%Y/%m/', null=True, blank=True,
        verbose_name='Maqola rasmi'
    )
    source_file = models.FileField(
        upload_to='submissions/%Y/%m/', null=True, blank=True,
        verbose_name='Yuborilgan fayl'
    )
    note        = models.TextField(blank=True, verbose_name="Muallif izohi")

    # ── AI ajratish ────────────────────────────────────────────────────────────
    extracted_text    = models.TextField(blank=True, verbose_name='Fayldan ajratilgan xom matn')
    extracted_authors = models.TextField(blank=True, verbose_name='Mualliflar (AI, vergul bilan)')
    ai_filled         = models.BooleanField(default=False, verbose_name='AI to\'ldirgan')

    # ── Ko'rib chiqish ────────────────────────────────────────────────────────
    status        = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft', verbose_name='Holat')
    reject_reason = models.TextField(blank=True, verbose_name='Rad etish / bekor qilish sababi')
    submitted_at  = models.DateTimeField(null=True, blank=True, verbose_name='Yuborilgan vaqt')

    # ── Bog'liqliklar (tasdiqlangandan so'ng o'rnatiladi) ─────────────────────
    article = models.OneToOneField(
        Article, null=True, blank=True, on_delete=models.SET_NULL,
        related_name='submission', verbose_name='Yaratilgan maqola'
    )
    author = models.ForeignKey(
        'authors.Author', null=True, blank=True, on_delete=models.SET_NULL,
        related_name='submissions', verbose_name='Muallif profili'
    )

    class Meta:
        verbose_name        = 'Yuborilgan maqola'
        verbose_name_plural = 'Yuborilgan maqolalar'
        ordering            = ['-created_at']

    def __str__(self):
        return f'{self.tg_name or self.chat_id} — {self.title or "(sarlavsiz)"}'

    @property
    def keywords_list(self) -> list[str]:
        return Keyword.parse_csv(self.keywords)

    @property
    def authors_list(self) -> list[str]:
        """AI ajratgan mualliflar (vergul bilan)."""
        seen, out = set(), []
        for part in (self.extracted_authors or '').replace(';', ',').split(','):
            name = part.strip()
            if name and name.lower() not in seen:
                seen.add(name.lower())
                out.append(name)
        return out


# ── Jurnal soni PDF'idan parser ajratgan maqola nomzodlari ─────────────────────

class ParsedArticle(BaseModel):
    """
    Jurnal soni (Issue) PDF'idan `utils.journal_parser` ajratgan maqola nomzodi.
    Admin ko'rib chiqib, muallifni moslashtirib (mavjud profil yoki yangi),
    "Saqlash" bosgandagina `Article` ga aylanadi.
    """
    STATUS_CHOICES = [
        ('pending', 'Kutilmoqda'),     # admin hali ko'rib chiqmagan
        ('saved',   'Saqlangan'),      # Article yaratildi
        ('skipped', "O'tkazib yuborilgan"),
    ]

    issue       = models.ForeignKey(
        'journals.Issue', on_delete=models.CASCADE,
        related_name='parsed_articles', verbose_name='Jurnal soni'
    )
    order       = models.PositiveSmallIntegerField(default=0, verbose_name='Tartib')
    section     = models.CharField(max_length=300, blank=True, verbose_name="Bo'lim")
    title       = models.CharField(max_length=500, blank=True, verbose_name='Sarlavha')
    author_name = models.CharField(max_length=200, blank=True, verbose_name='Ism familiya')
    extra_info  = models.TextField(blank=True, verbose_name="Qo'shimcha ma'lumot")
    start_page  = models.PositiveIntegerField(null=True, blank=True, verbose_name='Boshlanish bet')
    end_page    = models.PositiveIntegerField(null=True, blank=True, verbose_name='Tugash bet')

    article_pdf = models.FileField(
        upload_to='parsed/%Y/%m/', null=True, blank=True,
        verbose_name='Ajratilgan maqola PDF'
    )
    photo       = models.ImageField(
        upload_to='parsed/photos/%Y/%m/', null=True, blank=True,
        verbose_name='Muallif rasmi'
    )

    status      = models.CharField(max_length=10, choices=STATUS_CHOICES, default='pending', verbose_name='Holat')
    article     = models.OneToOneField(
        Article, null=True, blank=True, on_delete=models.SET_NULL,
        related_name='parsed_source', verbose_name='Yaratilgan maqola'
    )

    class Meta:
        verbose_name        = 'Ajratilgan maqola (parser)'
        verbose_name_plural = 'Ajratilgan maqolalar (parser)'
        ordering            = ['order']

    def __str__(self):
        return f'{self.order}. {self.author_name} — {self.title[:40]}'
