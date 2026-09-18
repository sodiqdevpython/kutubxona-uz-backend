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

from django.contrib.auth.hashers import check_password, make_password
from django.db import models
from django.utils import timezone

from utils.models import BaseModel


def generate_client_id() -> str:
    return 'kb_' + secrets.token_hex(12)


def generate_client_secret() -> str:
    return secrets.token_urlsafe(40)


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
        """Har bir muvaffaqiyatli so'rovda chaqiriladi (yengil UPDATE)."""
        PartnerClient.objects.filter(pk=self.pk).update(
            last_used_at=timezone.now(),
            request_count=models.F('request_count') + 1,
        )
