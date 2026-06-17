from django.contrib import admin
from .models import Journal, Issue


class IssueInline(admin.TabularInline):
    model  = Issue
    extra  = 0
    fields = ('volume', 'number', 'year', 'season', 'date_label', 'palette', 'pdf_file', 'is_current', 'is_upcoming')


@admin.register(Journal)
class JournalAdmin(admin.ModelAdmin):
    list_display = ('title', 'issn')
    inlines      = [IssueInline]


@admin.register(Issue)
class IssueAdmin(admin.ModelAdmin):
    list_display  = ('__str__', 'year', 'season', 'has_pdf', 'is_current', 'is_upcoming', 'article_count')
    list_filter   = ('year', 'season', 'is_current', 'is_upcoming')
    list_editable = ('is_current', 'is_upcoming')

    @admin.display(description='PDF', boolean=True)
    def has_pdf(self, obj):
        return bool(obj.pdf_file)
