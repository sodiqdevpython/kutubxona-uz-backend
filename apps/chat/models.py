"""
Chat (Telegram-orqali):
- Admin sayt admin paneldan istalgan muallif bilan yozishadi.
- Birinchi xabarni HAR DOIM admin yuboradi. User o'z holicha yoza olmaydi:
  agar Chat hali boshlanmagan/ochilmagan bo'lsa — user xabari rad etiladi.
- User bloklansa — yangi xabarlari saqlanmaydi.
- Admin matn + rasm + fayl yuboradi; user faqat matn.
- Tarix DB'da saqlanadi.
- User (Author) o'chsa → unga bog'liq Chat va Messagelar ham o'chadi (CASCADE).
"""
from django.db import models
from utils.models import BaseModel


class Chat(BaseModel):
    """
    Bitta foydalanuvchi (muallif) bilan suhbat.
    `author` orqali kim bilan yozishilayotgani aniqlanadi.
    Author o'chsa → Chat ham o'chadi (CASCADE).
    """
    author = models.OneToOneField(
        'authors.Author',
        on_delete=models.CASCADE,
        related_name='chat',
        verbose_name='Muallif',
    )

    # Bloklangan bo'lsa — user xabarlari saqlanmaydi
    is_blocked = models.BooleanField(default=False, verbose_name='Bloklangan')

    # Cache: oxirgi xabar vaqti (sortlash va "yangi" indikatori uchun)
    last_message_at = models.DateTimeField(null=True, blank=True, verbose_name="Oxirgi xabar vaqti")

    # Admin tomonidan o'qilmagan user xabarlari soni
    unread_count = models.PositiveIntegerField(default=0, verbose_name="O'qilmagan")

    class Meta:
        verbose_name        = 'Chat'
        verbose_name_plural = 'Chatlar'
        ordering            = ['-last_message_at', '-created_at']

    def __str__(self):
        return f'Chat: {self.author.name}'


class Message(BaseModel):
    SENDER_CHOICES = [
        ('admin', 'Admin'),
        ('user',  'User'),
    ]
    KIND_CHOICES = [
        ('text',     'Matn'),
        ('photo',    'Rasm'),
        ('document', 'Fayl'),
    ]

    chat        = models.ForeignKey(Chat, on_delete=models.CASCADE, related_name='messages')
    sender      = models.CharField(max_length=10, choices=SENDER_CHOICES)
    kind        = models.CharField(max_length=10, choices=KIND_CHOICES, default='text')

    text        = models.TextField(blank=True, verbose_name='Matn / caption')
    image       = models.ImageField(
        upload_to='chat/images/%Y/%m/', null=True, blank=True,
        verbose_name='Rasm',
    )
    document    = models.FileField(
        upload_to='chat/files/%Y/%m/', null=True, blank=True,
        verbose_name='Fayl',
    )

    # Admin tomonidan o'qilgan (faqat user xabarlari uchun ahamiyatli)
    is_read     = models.BooleanField(default=False)

    # Telegram'dan kelgan xabar identifikatori (debugging uchun)
    tg_message_id = models.BigIntegerField(null=True, blank=True)

    class Meta:
        verbose_name        = 'Xabar'
        verbose_name_plural = 'Xabarlar'
        ordering            = ['created_at']
        indexes = [
            models.Index(fields=['chat', '-created_at']),
        ]

    def __str__(self):
        return f'{self.get_sender_display()}: {(self.text or "[" + self.kind + "]")[:60]}'
