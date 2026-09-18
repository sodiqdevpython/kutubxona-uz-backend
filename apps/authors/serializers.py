from collections import Counter

from rest_framework import serializers

from .models import Author


class AuthorListSerializer(serializers.ModelSerializer):
    article_count = serializers.IntegerField(read_only=True)
    total_views   = serializers.IntegerField(read_only=True)
    avatar_url    = serializers.SerializerMethodField()

    class Meta:
        model  = Author
        fields = (
            'id', 'name', 'slug', 'initials',
            'role', 'org', 'degree',
            'avatar_idx', 'avatar_url',
            'article_count', 'total_views', 'profile_views',
            'orcid',
        )

    def get_avatar_url(self, obj) -> str | None:
        if not obj.avatar:
            return None
        request = self.context.get('request')
        if request:
            return request.build_absolute_uri(obj.avatar.url)
        return obj.avatar.url


class AuthorDetailSerializer(AuthorListSerializer):
    """
    Muallif sahifasi (Figma: «Muallif detail»).

    Qo'shimcha:
      • bio, email, scopus_id
      • categories — muallif yozgan yo'nalishlar (chiplar uchun)
      • years      — yillar bo'yicha maqolalar soni (diagramma uchun)
      • coauthors  — birgalikda yozgan mualliflar va umumiy maqolalar soni
    """
    categories = serializers.SerializerMethodField()
    years      = serializers.SerializerMethodField()
    coauthors  = serializers.SerializerMethodField()

    class Meta(AuthorListSerializer.Meta):
        fields = AuthorListSerializer.Meta.fields + (
            'bio', 'email', 'scopus_id', 'categories', 'years', 'coauthors',
        )

    def _published(self, obj):
        return (
            obj.articles
            .filter(issue__isnull=False)
            .select_related('category', 'issue')
            .prefetch_related('authors')
        )

    def get_categories(self, obj) -> list:
        counts = Counter(
            a.category.name for a in self._published(obj) if a.category_id
        )
        return [name for name, _ in counts.most_common(4)]

    def get_years(self, obj) -> list:
        """[{year, count}] — bo'sh yillar ham kiradi (diagrammada «–» chiqadi)."""
        arts = list(self._published(obj))
        if not arts:
            return []
        counts = Counter(a.issue.year if a.issue_id else a.year for a in arts)
        lo, hi = min(counts), max(counts)
        return [{'year': y, 'count': counts.get(y, 0)} for y in range(lo, hi + 1)]

    def get_coauthors(self, obj) -> list:
        shared: Counter = Counter()
        seen: dict = {}
        for art in self._published(obj):
            for co in art.authors.all():
                if co.pk == obj.pk:
                    continue
                shared[co.pk] += 1
                seen[co.pk] = co
        request = self.context.get('request')
        out = []
        for pk, n in shared.most_common(6):
            co = seen[pk]
            avatar = None
            if co.avatar:
                avatar = request.build_absolute_uri(co.avatar.url) if request else co.avatar.url
            out.append({
                'id': str(co.pk), 'name': co.name, 'slug': co.slug,
                'initials': co.initials, 'avatar_idx': co.avatar_idx,
                'avatar_url': avatar, 'shared': n,
            })
        return out
