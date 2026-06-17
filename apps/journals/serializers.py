from rest_framework import serializers
from .models import Journal, Issue


class IssueSerializer(serializers.ModelSerializer):
    article_count   = serializers.IntegerField(read_only=True)
    cover_image_url = serializers.SerializerMethodField()
    pdf_file_url    = serializers.SerializerMethodField()
    journal_id      = serializers.SerializerMethodField()
    journal_title   = serializers.SerializerMethodField()

    def get_cover_image_url(self, obj):
        if not obj.cover_image:
            return None
        request = self.context.get('request')
        return request.build_absolute_uri(obj.cover_image.url) if request else obj.cover_image.url

    def get_pdf_file_url(self, obj):
        if not obj.pdf_file:
            return None
        request = self.context.get('request')
        return request.build_absolute_uri(obj.pdf_file.url) if request else obj.pdf_file.url

    def get_journal_id(self, obj):
        return str(obj.journal_id) if obj.journal_id else None

    def get_journal_title(self, obj):
        return obj.journal.title if obj.journal_id else None

    class Meta:
        model  = Issue
        fields = (
            'id', 'volume', 'number', 'year', 'season',
            'date_label', 'palette', 'is_current', 'is_upcoming',
            'article_count', 'cover_image_url', 'pdf_file_url',
            'journal_id', 'journal_title',
        )


class JournalSerializer(serializers.ModelSerializer):
    issues = IssueSerializer(many=True, read_only=True)

    class Meta:
        model  = Journal
        fields = ('id', 'title', 'issn', 'issues')
