from django.db import models
from utils.models import BaseModel


class Journal(BaseModel):
    title = models.CharField(max_length=200, default='Kutubxona Arxivi', verbose_name='Jurnal nomi')
    issn  = models.CharField(max_length=20, blank=True, verbose_name='ISSN')

    class Meta:
        verbose_name        = 'Jurnal'
        verbose_name_plural = 'Jurnallar'

    def __str__(self):
        return self.title


class Issue(BaseModel):
    SEASON_CHOICES = [
        ('Bahor', 'Bahor'), ('Yoz', 'Yoz'),
        ('Kuz', 'Kuz'),    ('Qish', 'Qish'),
    ]

    journal     = models.ForeignKey(Journal, on_delete=models.CASCADE, related_name='issues', verbose_name='Jurnal')
    volume      = models.PositiveIntegerField(verbose_name='Jild')
    number      = models.PositiveIntegerField(verbose_name='Son')
    year        = models.PositiveIntegerField(verbose_name='Yil')
    season      = models.CharField(max_length=10, choices=SEASON_CHOICES, verbose_name='Mavsum')
    date_label  = models.CharField(max_length=100, blank=True, verbose_name='Sana (ko\'rinishi)')
    palette     = models.PositiveSmallIntegerField(default=0, verbose_name='Rang palitasi (0–5)')
    is_current  = models.BooleanField(default=False, verbose_name='Joriy son')
    is_upcoming = models.BooleanField(default=False, verbose_name='Tayyorlanmoqda')
    cover_image = models.ImageField(
        upload_to='journals/covers/%Y/', null=True, blank=True,
        verbose_name='Muqova rasmi (ixtiyoriy)',
        help_text='Yuklanmasa, palette ranglari asosida default cover ko\'rsatiladi.'
    )
    pdf_file = models.FileField(
        upload_to='journals/pdfs/%Y/', null=True, blank=True,
        verbose_name='PDF fayl (to\'liq son)',
        help_text='Jurnal sonining to\'liq PDF nusxasi. Yuklansa, son sahifasida ochiladi.'
    )

    class Meta:
        verbose_name        = 'Jurnal soni'
        verbose_name_plural = 'Jurnal sonlari'
        ordering            = ['-year', '-number']
        unique_together     = [('journal', 'volume', 'number')]

    def __str__(self):
        return f'{self.journal.title} — {self.volume}-jild, {self.number}-son ({self.year})'

    @property
    def article_count(self):
        return self.articles.count()
