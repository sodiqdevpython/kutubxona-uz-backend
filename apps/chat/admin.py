from django.contrib import admin
from .models import Chat, Message


@admin.register(Chat)
class ChatAdmin(admin.ModelAdmin):
    list_display  = ('author', 'is_blocked', 'last_message_at', 'unread_count')
    list_filter   = ('is_blocked',)
    search_fields = ('author__name', 'author__telegram_username')
    readonly_fields = ('last_message_at', 'unread_count')


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display  = ('chat', 'sender', 'kind', 'short_text', 'is_read', 'created_at')
    list_filter   = ('sender', 'kind', 'is_read')
    search_fields = ('chat__author__name', 'text')

    @admin.display(description='Matn')
    def short_text(self, obj):
        return (obj.text or '')[:60]
