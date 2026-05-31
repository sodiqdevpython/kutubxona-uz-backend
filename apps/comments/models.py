from django.db import models
from utils.models import BaseModel


class Comment(BaseModel):
    article  = models.ForeignKey(
        'articles.Article', on_delete=models.CASCADE,
        related_name='comments', verbose_name='Maqola'
    )
    parent   = models.ForeignKey(
        'self', on_delete=models.CASCADE, null=True, blank=True,
        related_name='replies', verbose_name='Yuqori izoh'
    )
    name     = models.CharField(max_length=150, verbose_name='Ism')
    text     = models.TextField(verbose_name='Matn')
    is_approved = models.BooleanField(default=False, verbose_name='Tasdiqlangan')

    class Meta:
        verbose_name        = 'Izoh'
        verbose_name_plural = 'Izohlar'
        ordering            = ['created_at']

    def __str__(self):
        return f'{self.name}: {self.text[:60]}'
