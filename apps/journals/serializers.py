from rest_framework import serializers
from .models import Journal, Issue


class IssueSerializer(serializers.ModelSerializer):
    article_count   = serializers.IntegerField(read_only=True)
    cover_image_url = serializers.SerializerMethodField()

    def get_cover_image_url(self, obj):
        if not obj.cover_image:
            return None
        request = self.context.get('request')
        return request.build_absolute_uri(obj.cover_image.url) if request else obj.cover_image.url

    class Meta:
        model  = Issue
        fields = (
            'id', 'volume', 'number', 'year', 'season',
            'date_label', 'palette', 'is_current', 'is_upcoming',
            'article_count', 'cover_image_url',
        )


class JournalSerializer(serializers.ModelSerializer):
    issues = IssueSerializer(many=True, read_only=True)

    class Meta:
        model  = Journal
        fields = ('id', 'title', 'issn', 'issues')
