from rest_framework import serializers

from .models import CentralAsiaPost


class CentralAsiaPostListSerializer(serializers.ModelSerializer):
    image_url    = serializers.SerializerMethodField()
    total_views  = serializers.IntegerField(read_only=True)

    class Meta:
        model  = CentralAsiaPost
        fields = (
            'id', 'title', 'slug', 'author_line', 'excerpt', 'image_url',
            'views_scraped', 'views_local', 'total_views', 'quote_number',
            'doi', 'source_category', 'source_url', 'published_at', 'created_at',
        )

    def get_image_url(self, obj):
        if not obj.image:
            return None
        request = self.context.get('request')
        url = obj.image.url
        return request.build_absolute_uri(url) if request else url


class CentralAsiaPostDetailSerializer(CentralAsiaPostListSerializer):
    content = serializers.CharField(read_only=True)

    class Meta(CentralAsiaPostListSerializer.Meta):
        fields = CentralAsiaPostListSerializer.Meta.fields + ('content', 'source_slug')
