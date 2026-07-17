from django.db import models
from slugify import slugify

from utils.models import BaseModel


class CentralAsiaPost(BaseModel):
    """
    einfolib.uz `Central Asia` bo'limidan parse qilib olingan yoki
    admin qo'lda qo'shgan maqola.

    View'lar ikkiga bo'linadi:
      - views_scraped — manba saytdagi ko'rishlar soni (parse'da yangilanadi)
      - views_local   — bizning saytdagi ko'rishlar soni (unique IP, 24 soat)
    UI'da esa `total_views = views_scraped + views_local` ko'rsatiladi.
    """

    SOURCE_CHOICES = [
        ('scraped', 'einfolib.uz (parse)'),
        ('manual',  "Qo'lda qo'shilgan"),
    ]

    # ── Manba ma'lumoti ──────────────────────────────────────────────────────
    source        = models.CharField(max_length=10, choices=SOURCE_CHOICES, default='manual', verbose_name='Manba')
    source_url    = models.URLField(max_length=800, unique=True, null=True, blank=True,
                                    verbose_name='Manba URL')
    source_slug   = models.CharField(max_length=500, blank=True, db_index=True,
                                     verbose_name='Manba slug (einfolib.uz)')
    source_category = models.CharField(max_length=200, blank=True,
                                       default='Central Asia',
                                       verbose_name='Manba bo\'limi')

    # ── Sahifada ko'rinadigan matn ───────────────────────────────────────────
    title       = models.CharField(max_length=500, verbose_name='Sarlavha')
    slug        = models.SlugField(max_length=520, unique=True, blank=True, verbose_name='Slug (URL)')
    author_line = models.CharField(max_length=500, blank=True, verbose_name='Muallif (matn)')
    excerpt     = models.TextField(blank=True, verbose_name='Qisqacha mazmun')
    content     = models.TextField(blank=True, verbose_name='Tarkib (HTML)')
    doi         = models.CharField(max_length=200, blank=True, verbose_name='DOI')

    image = models.ImageField(
        upload_to='central_asia/%Y/%m/', null=True, blank=True,
        verbose_name='Rasm (ixtiyoriy)',
    )

    # ── Statistika ────────────────────────────────────────────────────────────
    views_scraped  = models.PositiveIntegerField(default=0, verbose_name='Manba view')
    views_local    = models.PositiveIntegerField(default=0, verbose_name='Bizning view')
    quote_number   = models.PositiveIntegerField(default=0, verbose_name='Iqtiboslar (quote)')

    # ── Nashr ma'lumoti ──────────────────────────────────────────────────────
    published_at  = models.DateField(null=True, blank=True, verbose_name='Nashr sanasi')
    is_published  = models.BooleanField(default=True, verbose_name='E\'lon qilingan')

    # ── Kuzatuv ──────────────────────────────────────────────────────────────
    last_scraped_at = models.DateTimeField(null=True, blank=True, verbose_name='Oxirgi parse')

    # Manba saytdagi tartib bo'yicha global pozitsiya (0 = eng yangi, 1-sahifada birinchi).
    # Har parse'da qayta yoziladi — shu tufayli einfolib.uz'dagi tartib bizda ham saqlanadi.
    sort_order = models.IntegerField(default=0, db_index=True, verbose_name='Tartib (parse)')

    class Meta:
        verbose_name        = 'Central Asia maqolasi'
        verbose_name_plural = 'Central Asia maqolalari'
        ordering            = ['sort_order', '-created_at']
        indexes = [
            models.Index(fields=['-created_at']),
            models.Index(fields=['is_published']),
        ]

    def __str__(self):
        return self.title

    # ── Slug ──────────────────────────────────────────────────────────────────
    def _generate_slug(self) -> str:
        base = slugify(self.title, max_length=490) or 'post'
        slug, n = base, 1
        while CentralAsiaPost.objects.filter(slug=slug).exclude(pk=self.pk).exists():
            slug = f'{base}-{n}'
            n += 1
        return slug

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = self._generate_slug()
        super().save(*args, **kwargs)

    # ── Helpers ──────────────────────────────────────────────────────────────
    @property
    def total_views(self) -> int:
        return int(self.views_scraped) + int(self.views_local)

    def increment_views(self):
        CentralAsiaPost.objects.filter(pk=self.pk).update(
            views_local=models.F('views_local') + 1,
        )
