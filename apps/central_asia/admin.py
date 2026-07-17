from django.contrib import admin, messages
from django.urls import path
from django.shortcuts import redirect
from django.utils.html import format_html

from .models import CentralAsiaPost
from .services import run_scrape


@admin.register(CentralAsiaPost)
class CentralAsiaPostAdmin(admin.ModelAdmin):
    list_display    = ('title', 'source', 'views_scraped', 'views_local',
                       'total_views_col', 'quote_number', 'is_published', 'last_scraped_at')
    list_filter     = ('source', 'is_published', 'last_scraped_at')
    search_fields   = ('title', 'author_line', 'source_url', 'source_slug', 'excerpt')
    readonly_fields = ('slug', 'source_slug', 'views_scraped', 'views_local',
                       'quote_number', 'last_scraped_at', 'content_preview',
                       'source_link', 'total_views_col')
    save_on_top     = True
    list_per_page   = 30
    ordering        = ('-created_at',)

    fieldsets = (
        ('Asosiy', {
            'fields': ('title', 'slug', 'is_published', 'author_line',
                       'excerpt', 'image', 'published_at'),
        }),
        ('Manba', {
            'fields': ('source', 'source_url', 'source_link',
                       'source_slug', 'source_category', 'doi', 'last_scraped_at'),
        }),
        ('Tarkib (HTML)', {
            'fields': ('content', 'content_preview'),
            'classes': ('collapse',),
        }),
        ('Statistika', {
            'fields': ('views_scraped', 'views_local', 'total_views_col', 'quote_number'),
        }),
    )

    # ── Kalkulyatsiya ustunlari ──────────────────────────────────────────────

    @admin.display(description='Jami view')
    def total_views_col(self, obj):
        return obj.total_views

    @admin.display(description='Manba havola')
    def source_link(self, obj):
        if obj.source_url:
            return format_html('<a href="{u}" target="_blank">{u}</a>', u=obj.source_url)
        return '—'

    @admin.display(description="Tarkib ko'rinishi")
    def content_preview(self, obj):
        if not obj.content:
            return "Tarkib yo'q"
        return format_html(
            '<div style="max-height:340px;overflow:auto;border:1px solid #ddd;'
            'padding:10px;font-size:13px">{}</div>',
            format_html(obj.content[:4000]),
        )

    # ── Admin panelidagi "Yangilash" tugmasi ──────────────────────────────────
    change_list_template = 'admin/central_asia/centralasiapost/change_list.html'

    def get_urls(self):
        urls = super().get_urls()
        custom = [
            path(
                'scrape/',
                self.admin_site.admin_view(self.scrape_view),
                name='central_asia_centralasiapost_scrape',
            ),
        ]
        return custom + urls

    def scrape_view(self, request):
        try:
            summary = run_scrape()
        except Exception as e:
            self.message_user(request, f"Parse muvaffaqiyatsiz: {e}", level=messages.ERROR)
            return redirect('..')

        msg = (
            f"Sahifa: {summary.pages_visited}, topilgan: {summary.cards_found}, "
            f"yangi: {summary.created}, yangilangan: {summary.updated}."
        )
        level = messages.SUCCESS if not summary.errors else messages.WARNING
        self.message_user(request, msg, level=level)
        for err in summary.errors[:5]:
            self.message_user(request, err, level=messages.WARNING)
        return redirect('..')
