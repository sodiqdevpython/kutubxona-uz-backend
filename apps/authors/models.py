from django.db import models
from slugify import slugify
from utils.models import BaseModel


class Author(BaseModel):
    name             = models.CharField(max_length=200, verbose_name='F.I.Sh.')
    slug             = models.SlugField(max_length=220, unique=True, blank=True)
    initials         = models.CharField(max_length=5,   verbose_name='Bosh harflar', blank=True)
    role             = models.CharField(max_length=200, blank=True, verbose_name='Lavozim')
    org              = models.CharField(max_length=300, blank=True, verbose_name='Tashkilot')
    degree           = models.CharField(max_length=200, blank=True, verbose_name='Ilmiy daraja')
    bio              = models.TextField(blank=True, verbose_name='Tarjimai hol')
    avatar_idx       = models.PositiveSmallIntegerField(default=0, verbose_name='Avatar rangi (0–4)')
    avatar           = models.ImageField(
        upload_to='authors/avatars/', null=True, blank=True,
        verbose_name='Rasm (Telegram orqali yuklangan)'
    )
    profile_views    = models.PositiveIntegerField(
        default=0, verbose_name="Profil ko'rilishi soni"
    )

    # ── Telegram ──────────────────────────────────────────────────────────────
    telegram_chat_id = models.BigIntegerField(
        null=True, blank=True, unique=True, db_index=True,
        verbose_name='Telegram chat ID'
    )
    telegram_username = models.CharField(
        max_length=150, blank=True,
        verbose_name='Telegram @username'
    )

    class Meta:
        verbose_name        = 'Muallif'
        verbose_name_plural = 'Mualliflar'
        ordering            = ['name']

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.initials and self.name:
            parts = self.name.split()
            self.initials = ''.join(p[0].upper() for p in parts[:2])
        if not self.slug:
            base = slugify(self.name, max_length=210)
            slug = base
            n = 1
            while Author.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                slug = f'{base}-{n}'
                n += 1
            self.slug = slug
        super().save(*args, **kwargs)

    @property
    def article_count(self):
        return self.articles.filter(status='open').count()

    @property
    def total_views(self):
        return self.articles.aggregate(
            total=models.Sum('views')
        )['total'] or 0

    def increment_profile_views(self):
        Author.objects.filter(pk=self.pk).update(profile_views=models.F('profile_views') + 1)
