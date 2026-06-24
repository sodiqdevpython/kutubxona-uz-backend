from rest_framework import serializers
from apps.articles.models import Article, ArticleSubmission, Category, ParsedArticle
from apps.authors.models import Author
from apps.journals.models import Issue


def _abs_url(field, context):
    """ImageField/FileField -> absolute URL (request bor bo'lsa) yoki None."""
    if not field:
        return None
    request = context.get('request') if context else None
    return request.build_absolute_uri(field.url) if request else field.url


class AdminAuthorSerializer(serializers.ModelSerializer):
    article_count = serializers.SerializerMethodField()
    avatar_url    = serializers.SerializerMethodField()

    def get_article_count(self, obj):
        return obj.articles.count()

    def get_avatar_url(self, obj):
        return _abs_url(obj.avatar, self.context)

    class Meta:
        model  = Author
        fields = (
            'id', 'name', 'slug', 'initials', 'role', 'org', 'degree', 'bio',
            'avatar_idx', 'avatar_url', 'source',
            'telegram_chat_id', 'telegram_username',
            'article_count', 'created_at',
        )
        read_only_fields = (
            'id', 'slug', 'created_at', 'source',
            'telegram_chat_id', 'telegram_username',
        )


class AuthorMatchSerializer(serializers.ModelSerializer):
    """Dedup uchun mavjud (qo'lda/parser) profil — admin rasm+ma'lumot bilan ko'radi."""
    article_count = serializers.SerializerMethodField()
    avatar_url    = serializers.SerializerMethodField()

    def get_article_count(self, obj):
        return obj.articles.count()

    def get_avatar_url(self, obj):
        return _abs_url(obj.avatar, self.context)

    class Meta:
        model  = Author
        fields = (
            'id', 'name', 'slug', 'initials', 'role', 'org', 'degree', 'bio',
            'avatar_idx', 'avatar_url', 'source', 'article_count',
        )


class ParsedArticleSerializer(serializers.ModelSerializer):
    article_pdf_url = serializers.SerializerMethodField()
    photo_url       = serializers.SerializerMethodField()
    matches         = serializers.SerializerMethodField()
    article_slug    = serializers.SerializerMethodField()

    def get_article_pdf_url(self, obj):
        return _abs_url(obj.article_pdf, self.context)

    def get_photo_url(self, obj):
        return _abs_url(obj.photo, self.context)

    def get_article_slug(self, obj):
        return obj.article.slug if obj.article else None

    def get_matches(self, obj):
        from .dedup import author_candidates
        cands = author_candidates(obj.author_name)
        return AuthorMatchSerializer(cands, many=True, context=self.context).data

    class Meta:
        model  = ParsedArticle
        fields = (
            'id', 'order', 'section', 'title', 'author_name', 'extra_info',
            'start_page', 'end_page', 'status',
            'article_pdf_url', 'photo_url', 'matches',
            'article_id', 'article_slug', 'created_at',
        )
        read_only_fields = (
            'id', 'order', 'start_page', 'end_page', 'status',
            'article_pdf_url', 'photo_url', 'matches',
            'article_id', 'article_slug', 'created_at',
        )


class AdminArticleInIssueSerializer(serializers.ModelSerializer):
    category_name = serializers.SerializerMethodField()
    authors_label = serializers.SerializerMethodField()

    def get_category_name(self, obj):
        return obj.category.name if obj.category else None

    def get_authors_label(self, obj):
        return obj.author_label

    class Meta:
        model  = Article
        fields = (
            'id', 'title', 'slug', 'status', 'year', 'quarter',
            'pages', 'min_read', 'authors_label', 'category_name', 'published_at',
        )


class AdminSubmissionSerializer(serializers.ModelSerializer):
    author_name      = serializers.SerializerMethodField()
    authors_list     = serializers.SerializerMethodField()
    keywords_list    = serializers.SerializerMethodField()
    article_id       = serializers.SerializerMethodField()
    article_title    = serializers.SerializerMethodField()
    article_slug     = serializers.SerializerMethodField()
    article_category = serializers.SerializerMethodField()
    article_issue    = serializers.SerializerMethodField()
    article_ai_ready = serializers.SerializerMethodField()
    source_file_url  = serializers.SerializerMethodField()
    image_url        = serializers.SerializerMethodField()

    def get_article_ai_ready(self, obj) -> bool:
        return bool(obj.article and obj.article.llm_document_id)

    def get_author_name(self, obj):
        return obj.author.name if obj.author else (obj.tg_name or 'Noma\'lum')

    def get_authors_list(self, obj):
        return obj.authors_list

    def get_keywords_list(self, obj):
        return obj.keywords_list

    def get_article_id(self, obj):
        return str(obj.article.id) if obj.article else None

    def get_article_title(self, obj):
        return obj.article.title if obj.article else None

    def get_article_slug(self, obj):
        return obj.article.slug if obj.article else None

    def get_article_category(self, obj):
        if obj.article and obj.article.category:
            return {'id': str(obj.article.category.id), 'name': obj.article.category.name}
        return None

    def get_article_issue(self, obj):
        if obj.article and obj.article.issue:
            i = obj.article.issue
            return {'id': str(i.id), 'volume': i.volume, 'number': i.number,
                    'year': i.year, 'label': i.date_label}
        return None

    def _abs(self, field):
        if not field:
            return None
        request = self.context.get('request')
        return request.build_absolute_uri(field.url) if request else field.url

    def get_source_file_url(self, obj):
        return self._abs(obj.source_file)

    def get_image_url(self, obj):
        return self._abs(obj.image)

    class Meta:
        model  = ArticleSubmission
        fields = (
            'id', 'chat_id', 'tg_name', 'tg_username',
            'title', 'keywords', 'keywords_list', 'abstract', 'references', 'note',
            'extracted_authors', 'authors_list', 'ai_filled',
            'status', 'reject_reason', 'created_at', 'submitted_at',
            'author_name',
            'article_id', 'article_title', 'article_slug',
            'article_category', 'article_issue', 'article_ai_ready',
            'source_file_url', 'image_url',
        )


class AdminCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model  = Category
        fields = ('id', 'name', 'slug')
        read_only_fields = ('id', 'slug')


class AdminIssueSerializer(serializers.ModelSerializer):
    journal_title   = serializers.SerializerMethodField()
    article_count   = serializers.SerializerMethodField()
    cover_image_url = serializers.SerializerMethodField()
    pdf_file_url    = serializers.SerializerMethodField()

    def get_journal_title(self, obj):
        return obj.journal.title if obj.journal else None

    def get_article_count(self, obj):
        return obj.articles.count()

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

    class Meta:
        model  = Issue
        fields = (
            'id', 'journal', 'journal_title',
            'volume', 'number', 'year', 'season', 'date_label',
            'palette', 'is_current', 'is_upcoming',
            'article_count', 'cover_image_url', 'pdf_file_url', 'created_at',
        )
        read_only_fields = ('id', 'created_at', 'journal_title', 'article_count', 'cover_image_url', 'pdf_file_url')
