from django.contrib import admin
from .models import Comment


@admin.register(Comment)
class CommentAdmin(admin.ModelAdmin):
    list_display  = ('name', 'article', 'issue', 'parent', 'is_approved', 'created_at')
    list_filter   = ('is_approved',)
    list_editable = ('is_approved',)
    search_fields = ('name', 'text')
    actions       = ['approve_comments']

    @admin.action(description='Tanlangan izohlarni tasdiqlash')
    def approve_comments(self, request, queryset):
        updated = queryset.update(is_approved=True)
        self.message_user(request, f'{updated} ta izoh tasdiqlandi.')
