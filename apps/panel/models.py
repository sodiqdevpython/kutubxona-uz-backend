from django.db import models
from utils.models import BaseModel


class TelegramAdmin(BaseModel):
    """
    Yangi maqola kelganda bildirishnoma oladigan adminlar.
    Django admin orqali qo'shiladi. Admin botga /start bosgan bo'lishi kerak.
    """
    chat_id   = models.BigIntegerField(unique=True, verbose_name='Telegram chat ID')
    name      = models.CharField(max_length=200, blank=True, verbose_name='Ism (eslatma uchun)')
    is_active = models.BooleanField(default=True, verbose_name='Faol')

    class Meta:
        verbose_name        = 'Telegram admin'
        verbose_name_plural = 'Telegram adminlar (bildirishnoma)'
        ordering            = ['name']

    def __str__(self):
        return f'{self.name or "Admin"} ({self.chat_id})'

    @classmethod
    def active_ids(cls) -> list[int]:
        return list(cls.objects.filter(is_active=True).values_list('chat_id', flat=True))
