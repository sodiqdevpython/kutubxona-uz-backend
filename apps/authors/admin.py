from django.contrib import admin
from .models import Author


@admin.register(Author)
class AuthorAdmin(admin.ModelAdmin):
    list_display    = ('name', 'initials', 'role', 'org', 'article_count')
    search_fields   = ('name', 'org', 'role')
    readonly_fields = ('slug', 'initials')
