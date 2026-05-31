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
        )

    def get_avatar_url(self, obj) -> str | None:
        if not obj.avatar:
            return None
        request = self.context.get('request')
        if request:
            return request.build_absolute_uri(obj.avatar.url)
        return obj.avatar.url


class AuthorDetailSerializer(AuthorListSerializer):
    class Meta(AuthorListSerializer.Meta):
        fields = AuthorListSerializer.Meta.fields + ('bio',)
