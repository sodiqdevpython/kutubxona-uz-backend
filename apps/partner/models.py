"""
Tashqi (hamkor) xizmatlar uchun mijoz hisoblari.

Har bir hamkorga `client_id` + `client_secret` juftligi beriladi. Secret
bazada faqat xesh ko'rinishida saqlanadi — ochiq matni yaratilgan paytda
bir marta ko'rsatiladi va boshqa tiklab bo'lmaydi (yangisini generatsiya
qilish mumkin).

Hamkor bu juftlikni access/refresh tokenga almashtiradi va faqat
`/api/partner/…` endpointlariga kira oladi (admin paneli emas).
"""
import secrets
from datetime import timedelta

from django.contrib.auth.hashers import check_password, make_password
from django.db import models
from django.utils import timezone

from utils.models import BaseModel


def generate_client_id() -> str:
    return 'kb_' + secrets.token_hex(12)


def generate_client_secret() -> str:
    return secrets.token_urlsafe(40)


class PartnerRequestDay(models.Model):
    """
    Hamkor so'rovlari — kunlik yig'indi. `PartnerClient.request_count` umumiy
    (hech qachon nolga tushmaydigan) hisoblagich bo'lib qolaveradi; bu jadval
    esa «bugun» va «so'nggi 7 kun» ko'rsatkichlari uchun. 90 kundan eski
    yozuvlar avtomatik tozalanadi (yangi kun boshlanganda).
    """
    KEEP_DAYS = 90

    client = models.ForeignKey(
        'partner.PartnerClient', on_delete=models.CASCADE,
        related_name='days', verbose_name='Hamkor',
    )
    date  = models.DateField(verbose_name='Sana')
    count = models.PositiveIntegerField(default=0, verbose_name="So'rovlar")

    class Meta:
        unique_together     = ('client', 'date')
        ordering            = ['-date']
        verbose_name        = "Hamkor so'rovlari (kunlik)"
        verbose_name_plural = "Hamkor so'rovlari (kunlik)"

    def __str__(self):
        return f'{self.date}: {self.count}'


class PartnerClient(BaseModel):
    name = models.CharField(
        max_length=200, verbose_name='Hamkor nomi',
        help_text='Masalan: "Ilmiy indekslash xizmati"',
    )
    client_id = models.CharField(
        max_length=64, unique=True, db_index=True,
        default=generate_client_id, verbose_name='client_id',
    )
    secret_hash = models.CharField(
        max_length=256, blank=True, verbose_name='client_secret (xesh)',
    )
    is_active = models.BooleanField(default=True, verbose_name='Faol')
    contact = models.CharField(
        max_length=300, blank=True, verbose_name='Aloqa (email/telefon)',
    )
    note = models.TextField(blank=True, verbose_name='Izoh')

    # Tokenlarni bekor qilish uchun: raqam oshsa, eski tokenlar darhol
    # yaroqsiz bo'ladi (mijozni o'chirmasdan).
    token_version = models.PositiveIntegerField(
        default=1, verbose_name='Token versiyasi',
    )

    last_used_at = models.DateTimeField(
        null=True, blank=True, verbose_name='Oxirgi murojaat',
    )
    request_count = models.PositiveBigIntegerField(
        default=0, verbose_name="So'rovlar soni",
    )

    class Meta:
        verbose_name        = 'Hamkor mijoz (API)'
        verbose_name_plural = 'Hamkor mijozlar (API)'
        ordering            = ['name']

    def __str__(self):
        return f'{self.name} ({self.client_id})'

    # ── Secret ───────────────────────────────────────────────────────────────

    def set_secret(self, raw: str) -> None:
        self.secret_hash = make_password(raw)

    def check_secret(self, raw: str) -> bool:
        if not self.secret_hash or not raw:
            return False
        return check_password(raw, self.secret_hash)

    def rotate_secret(self) -> str:
        """Yangi secret yaratadi va ochiq matnini QAYTARADI (bir martalik)."""
        raw = generate_client_secret()
        self.set_secret(raw)
        self.save(update_fields=['secret_hash', 'updated_at'])
        return raw

    def revoke_tokens(self) -> int:
        """Berilgan barcha access/refresh tokenlarni bekor qiladi."""
        self.token_version = (self.token_version or 1) + 1
        self.save(update_fields=['token_version', 'updated_at'])
        return self.token_version

    # ── Statistika ───────────────────────────────────────────────────────────

    def touch(self) -> None:
        """
        Har bir muvaffaqiyatli so'rovda chaqiriladi: umumiy hisoblagich va
        kunlik yig'indi (ikkalasi ham yengil UPDATE, o'qib-yozish poygasisiz).
        """
        today = timezone.localdate()
        PartnerClient.objects.filter(pk=self.pk).update(
            last_used_at=timezone.now(),
            request_count=models.F('request_count') + 1,
        )
        day, created = PartnerRequestDay.objects.get_or_create(client_id=self.pk, date=today)
        PartnerRequestDay.objects.filter(pk=day.pk).update(count=models.F('count') + 1)
        if created:   # kuniga bir marta — eski kunlik yozuvlarni tozalaymiz
            PartnerRequestDay.objects.filter(
                client_id=self.pk, date__lt=today - timedelta(days=PartnerRequestDay.KEEP_DAYS),
            ).delete()
