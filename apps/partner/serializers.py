"""
Hamkor API serializerlari.

DIQQAT: bu yerda maqolaning faqat identifikatori, sarlavhasi, sanasi va
fayli beriladi. Abstrakt, tarkib, mualliflar, kalit so'zlar, ko'rishlar soni
va boshqa ichki ma'lumotlar tashqariga CHIQMAYDI.
"""
import os

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

class ArticleFileSerializer(serializers.Serializer):
    name   = serializers.CharField(help_text='Fayl nomi')
    format = serializers.CharField(help_text='pdf | docx | doc')
    size   = serializers.IntegerField(help_text='Bayt')
    url    = serializers.URLField(help_text='Yuklab olish manzili (token talab qiladi)')


class PartnerArticleListSerializer(serializers.ModelSerializer):
    """Ro'yxat elementi — slug, sarlavha va sana."""
    published_at = serializers.SerializerMethodField()

    class Meta:
        model  = Article
        fields = ('slug', 'title', 'published_at')

    def get_published_at(self, obj) -> str | None:
        date = obj.published_at or obj.created_at.date()
        return date.isoformat()


class PartnerArticleDetailSerializer(serializers.ModelSerializer):
    """Detal — sarlavha va maqolaning haqiqiy fayli, boshqa hech narsa."""
    published_at = serializers.SerializerMethodField()
    file         = serializers.SerializerMethodField()

    class Meta:
        model  = Article
        fields = ('slug', 'title', 'published_at', 'file')

    def get_published_at(self, obj) -> str | None:
        date = obj.published_at or obj.created_at.date()
        return date.isoformat()

    def get_file(self, obj) -> dict | None:
        f = obj.source_file
        if not f:
            return None

        name = os.path.basename(f.name)
        ext  = os.path.splitext(name)[1].lstrip('.').lower()

        try:
            size = f.size
        except (OSError, ValueError):
            size = 0

        request  = self.context.get('request')
        rel_path = f'/api/partner/articles/{obj.slug}/file/'
        url      = request.build_absolute_uri(rel_path) if request else rel_path

        return {
            'name':   name,
            'format': ext or 'bin',
            'size':   size,
            'url':    url,
        }
