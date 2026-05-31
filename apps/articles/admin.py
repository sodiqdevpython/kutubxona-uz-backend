from django.contrib import admin
from django.utils.html import format_html

from .models import Category, Article, ArticleAuthor, ArticleSubmission


# ── Category ──────────────────────────────────────────────────────────────────

@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display  = ('name', 'slug', 'article_count')
    search_fields = ('name',)


# ── Article ───────────────────────────────────────────────────────────────────

class ArticleAuthorInline(admin.TabularInline):
    model  = ArticleAuthor
    extra  = 1
    fields = ('author', 'order')


@admin.register(Article)
class ArticleAdmin(admin.ModelAdmin):
    list_display    = ('title', 'category', 'issue', 'status', 'year', 'views', 'has_file', 'has_content')
    list_filter     = ('status', 'year', 'quarter', 'category')
    search_fields   = ('title', 'excerpt')
    readonly_fields = ('slug', 'views', 'content_preview')
    inlines         = [ArticleAuthorInline]
    save_on_top     = True
    actions         = ['parse_source_files']

    fieldsets = (
        ('Asosiy', {'fields': ('title', 'slug', 'excerpt', 'category', 'issue')}),
        ('Manba fayl', {
            'fields': ('source_file',),
            'description': 'DOCX yoki PDF yuklang. Saqlashda avtomatik parse qilinadi.',
        }),
        ('Tarkib (HTML)', {'fields': ('content', 'content_preview'), 'classes': ('collapse',)}),
        ('Meta', {'fields': ('status', 'year', 'quarter', 'pages', 'min_read', 'cites', 'img_variant', 'published_at')}),
        ('Statistika', {'fields': ('views',), 'classes': ('collapse',)}),
    )

    @admin.action(description='Tanlangan maqolalarning faylini parse qilish')
    def parse_source_files(self, request, queryset):
        updated = errors = 0
        for article in queryset:
            if not article.source_file:
                continue
            html = article.parse_source_file()
            if html:
                article.content = html
                article.save(update_fields=['content', 'updated_at'])
                updated += 1
            else:
                errors += 1
        msg = f'{updated} ta maqola tarkibi yangilandi.'
        if errors:
            msg += f' {errors} ta faylda xatolik.'
        self.message_user(request, msg)

    @admin.display(description='Fayl', boolean=True)
    def has_file(self, obj):
        return bool(obj.source_file)

    @admin.display(description='HTML', boolean=True)
    def has_content(self, obj):
        return bool(obj.content.strip())

    @admin.display(description="Tarkib ko'rinishi")
    def content_preview(self, obj):
        if not obj.content:
            return "Tarkib yo'q"
        return format_html(
            '<div style="max-height:300px;overflow:auto;border:1px solid #ddd;padding:8px;font-size:13px">{}</div>',
            format_html(obj.content[:2000])
        )

    def save_model(self, request, obj, form, change):
        old_file = None
        if change:
            try:
                old_file = Article.objects.get(pk=obj.pk).source_file.name
            except Article.DoesNotExist:
                pass
        super().save_model(request, obj, form, change)
        new_file = obj.source_file.name if obj.source_file else None
        if new_file and new_file != old_file:
            html = obj.parse_source_file()
            if html:
                obj.content = html
                obj.save(update_fields=['content', 'updated_at'])
                self.message_user(request, f'"{obj.title}" uchun fayl parse qilindi.')


# ── ArticleSubmission ─────────────────────────────────────────────────────────
# Tasdiqlash / rad etish endi sayt admin paneli orqali bo'ladi.
# Django admin'da faqat ko'rish va o'chirish.

@admin.register(ArticleSubmission)
class ArticleSubmissionAdmin(admin.ModelAdmin):
    list_display  = ('title_or_file', 'tg_name', 'tg_username_link', 'status', 'ai_filled', 'submitted_at', 'article_link')
    list_filter   = ('status', 'ai_filled', 'created_at')
    search_fields = ('tg_name', 'tg_username', 'title', 'keywords')
    ordering      = ('-created_at',)
    list_per_page = 30

    readonly_fields = (
        'chat_id', 'tg_name', 'tg_username',
        'title', 'keywords', 'abstract', 'references',
        'extracted_authors', 'ai_filled',
        'image_preview', 'source_file', 'note',
        'status', 'reject_reason', 'submitted_at',
        'article', 'author', 'created_at',
    )
    fields = readonly_fields

    # ── List ustunlari ──────────────────────────────────────────────────────

    @admin.display(description='@username')
    def tg_username_link(self, obj):
        if obj.tg_username:
            return format_html('<a href="https://t.me/{u}" target="_blank">@{u}</a>', u=obj.tg_username)
        return '—'

    @admin.display(description='Sarlavha / Fayl')
    def title_or_file(self, obj):
        if obj.title:
            return obj.title[:60]
        if obj.source_file:
            return obj.source_file.name.split('/')[-1]
        return '(bo\'sh)'

    @admin.display(description='Maqola')
    def article_link(self, obj):
        if obj.article:
            return format_html(
                '<a href="/admin/articles/article/{}/change/">{}</a>',
                obj.article.pk, obj.article.title[:40],
            )
        return '—'

    @admin.display(description='Rasm')
    def image_preview(self, obj):
        if obj.image:
            return format_html(
                '<img src="{}" style="max-height:200px;border-radius:8px;border:1px solid #ddd"/>',
                obj.image.url,
            )
        return 'Rasm yo\'q'
