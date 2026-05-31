from django.contrib import admin
from .models import TelegramAdmin


@admin.register(TelegramAdmin)
class TelegramAdminAdmin(admin.ModelAdmin):
    list_display  = ('name', 'chat_id', 'is_active', 'created_at')
    list_filter   = ('is_active',)
    search_fields = ('name', 'chat_id')
    list_editable = ('is_active',)
