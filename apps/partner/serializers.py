"""
Hamkor API serializerlari.

DIQQAT: bu yerda maqolaning faqat identifikatori, sarlavhasi, sanasi va
fayli beriladi. Abstrakt, tarkib, mualliflar, kalit so'zlar, ko'rishlar soni
va boshqa ichki ma'lumotlar tashqariga CHIQMAYDI.
"""
import os
from urllib.parse import quote

from rest_framework import serializers

from apps.articles.models import Article


# ── Autentifikatsiya ─────────────────────────────────────────────────────────

class TokenRequestSerializer(serializers.Serializer):
    client_id     = serializers.CharField(max_length=64)
    client_secret = serializers.CharField(max_length=128, write_only=True)


class TokenRefreshRequestSerializer(serializers.Serializer):
    refresh = serializers.CharField()


class TokenPairSerializer(serializers.Serializer):
    """Javob shakli (faqat hujjat uchun)."""
    token_type         = serializers.CharField(default='Bearer')
    access             = serializers.CharField()
    refresh            = serializers.CharField()
    access_expires_in  = serializers.IntegerField(help_text='Sekundlarda')
    refresh_expires_in = serializers.IntegerField(help_text='Sekundlarda')


# ── Maqolalar ────────────────────────────────────────────────────────────────

def _published(obj) -> str:
    date = obj.published_at or obj.created_at.date()
    return date.isoformat()


class PartnerArticleListSerializer(serializers.ModelSerializer):
    """Ro'yxat elementi — id, sarlavha va sana."""
    published_at = serializers.SerializerMethodField()

    class Meta:
        model  = Article
        fields = ('id', 'title', 'published_at')

    def get_published_at(self, obj) -> str:
        return _published(obj)


class PartnerArticleDetailSerializer(serializers.ModelSerializer):
    """
    Detal — sarlavha va maqolaning haqiqiy fayli, boshqa hech narsa.
    `file_url` — to'liq, tayyor manzil (fayl nomi bilan); o'sha token bilan
    to'g'ridan-to'g'ri yuklab olinadi.
    """
    published_at = serializers.SerializerMethodField()
    file_url     = serializers.SerializerMethodField()
    file_name    = serializers.SerializerMethodField()
    file_format  = serializers.SerializerMethodField()
    file_size    = serializers.SerializerMethodField()

    class Meta:
        model  = Article
        fields = ('id', 'title', 'published_at', 'file_url', 'file_name', 'file_format', 'file_size')

    def get_published_at(self, obj) -> str:
        return _published(obj)

    def _name(self, obj) -> str:
        return os.path.basename(obj.source_file.name) if obj.source_file else ''

    def get_file_name(self, obj) -> str | None:
        return self._name(obj) or None

    def get_file_format(self, obj) -> str | None:
        name = self._name(obj)
        if not name:
            return None
        return os.path.splitext(name)[1].lstrip('.').lower() or 'bin'

    def get_file_size(self, obj) -> int | None:
        if not obj.source_file:
            return None
        try:
            return obj.source_file.size
        except (OSError, ValueError):
            return 0

    def get_file_url(self, obj) -> str | None:
        name = self._name(obj)
        if not name:
            return None
        rel_path = f'/api/partner/articles/{obj.pk}/file/{quote(name)}'
        request  = self.context.get('request')
        return request.build_absolute_uri(rel_path) if request else rel_path
