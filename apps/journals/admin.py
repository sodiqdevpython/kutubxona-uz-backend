from django.contrib import admin
from .models import Journal, Issue


class IssueInline(admin.TabularInline):
    model  = Issue
    extra  = 0
    fields = ('volume', 'number', 'year', 'season', 'date_label', 'palette', 'is_current', 'is_upcoming')


@admin.register(Journal)
class JournalAdmin(admin.ModelAdmin):
    list_display = ('title', 'issn')
    inlines      = [IssueInline]


@admin.register(Issue)
class IssueAdmin(admin.ModelAdmin):
    list_display  = ('__str__', 'year', 'season', 'is_current', 'is_upcoming', 'article_count')
    list_filter   = ('year', 'season', 'is_current', 'is_upcoming')
    list_editable = ('is_current', 'is_upcoming')
