from rest_framework import serializers
from drf_spectacular.utils import extend_schema_field
from apps.authors.models import Author
from .models import Category, Article, ArticleAuthor, ArticleSubmission


class CategorySerializer(serializers.ModelSerializer):
    article_count = serializers.IntegerField(read_only=True)

    class Meta:
        model  = Category
        fields = ('id', 'name', 'slug', 'article_count')


class AuthorBriefSerializer(serializers.ModelSerializer):
    class Meta:
        model  = Author
        fields = ('id', 'name', 'slug', 'initials', 'avatar_idx')


class ArticleListSerializer(serializers.ModelSerializer):
    category      = CategorySerializer(read_only=True)
    authors       = serializers.SerializerMethodField()
    author_label  = serializers.CharField(read_only=True)
    author_names  = serializers.SerializerMethodField()
    image_url     = serializers.SerializerMethodField()
    keywords      = serializers.SerializerMethodField()

    class Meta:
        model  = Article
        fields = (
            'id', 'title', 'slug', 'excerpt',
            'category', 'authors', 'author_label', 'author_names',
            'status', 'year', 'quarter',
            'pages', 'min_read', 'cites', 'views',
            'img_variant', 'image_url', 'keywords', 'published_at',
        )

    @extend_schema_field({'type': 'array', 'items': {'type': 'string'}})
    def get_keywords(self, obj):
        return list(obj.keywords.values_list('name', flat=True))

    @extend_schema_field(AuthorBriefSerializer(many=True))
    def get_authors(self, obj):
        ordered = obj.authors.all().order_by('articleauthor__order')
        return AuthorBriefSerializer(ordered, many=True).data

    @extend_schema_field({'type': 'array', 'items': {'type': 'string'}})
    def get_author_names(self, obj):
        return obj.author_names_list

    @extend_schema_field({'type': 'string', 'nullable': True})
    def get_image_url(self, obj) -> str | None:
        if not obj.image:
            return None
        request = self.context.get('request')
        return request.build_absolute_uri(obj.image.url) if request else obj.image.url


class ArticleDetailSerializer(ArticleListSerializer):
    issue           = serializers.SerializerMethodField()
    source_file_url = serializers.SerializerMethodField()
    keywords        = serializers.SerializerMethodField()
    references      = serializers.CharField(read_only=True)

    class Meta(ArticleListSerializer.Meta):
        fields = ArticleListSerializer.Meta.fields + (
            'content', 'source_file_url', 'keywords', 'references', 'issue',
        )

    @extend_schema_field({'type': 'array', 'items': {'type': 'object'}})
    def get_keywords(self, obj):
        return [
            {'name': k.name, 'slug': k.slug}
            for k in obj.keywords.all().order_by('name')
        ]

    @extend_schema_field({'type': 'string', 'nullable': True})
    def get_source_file_url(self, obj) -> str | None:
        if not obj.source_file:
            return None
        request = self.context.get('request')
        if request:
            return request.build_absolute_uri(obj.source_file.url)
        return obj.source_file.url

    @extend_schema_field({
        'type': 'object',
        'nullable': True,
        'properties': {
            'id':         {'type': 'string'},
            'volume':     {'type': 'integer'},
            'number':     {'type': 'integer'},
            'year':       {'type': 'integer'},
            'season':     {'type': 'string'},
            'date_label': {'type': 'string'},
        },
    })
    def get_issue(self, obj):
        if not obj.issue:
            return None
        i = obj.issue
        cover = None
        if i.cover_image:
            request = self.context.get('request')
            cover = request.build_absolute_uri(i.cover_image.url) if request else i.cover_image.url
        return {
            'id':              str(i.id),
            'volume':          i.volume,
            'number':          i.number,
            'year':            i.year,
            'season':          i.season,
            'date_label':      i.date_label,
            'cover_image_url': cover,
        }


# ── Submission ────────────────────────────────────────────────────────────────

class ArticleSubmissionSerializer(serializers.ModelSerializer):
    has_image = serializers.SerializerMethodField()
    has_file  = serializers.SerializerMethodField()

    @extend_schema_field({'type': 'boolean'})
    def get_has_image(self, obj):
        return bool(obj.image)

    @extend_schema_field({'type': 'boolean'})
    def get_has_file(self, obj):
        return bool(obj.source_file)

    class Meta:
        model  = ArticleSubmission
        fields = (
            'id', 'chat_id', 'tg_name', 'tg_username',
            'title', 'keywords', 'abstract', 'references',
            'source_file', 'image', 'note',
            'status', 'has_image', 'has_file',
            'created_at',
        )
        read_only_fields = ('id', 'status', 'created_at')
