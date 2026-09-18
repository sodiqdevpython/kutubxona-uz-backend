from django.contrib import admin, messages
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import path, reverse
from django.utils.html import format_html

from .models import PartnerClient, generate_client_secret
from .tokens import issue_pair
from .utils import partner_api_base


@admin.register(PartnerClient)
class PartnerClientAdmin(admin.ModelAdmin):
    list_display  = ('name', 'client_id', 'is_active', 'request_count',
                     'last_used_at', 'token_button')
    list_filter   = ('is_active',)
    search_fields = ('name', 'client_id', 'contact')
    readonly_fields = (
        'client_id', 'secret_hash', 'token_version', 'request_count',
        'last_used_at', 'created_at', 'updated_at', 'usage_hint',
    )
    fieldsets = (
        (None, {
            'fields': ('name', 'contact', 'note', 'is_active'),
        }),
        ('Kirish maʼlumotlari', {
            'fields': ('client_id', 'secret_hash', 'usage_hint'),
            'description': (
                "client_secret faqat yaratilgan paytda bir marta ko'rsatiladi. "
                "Yo'qotilsa — «Yangi client_secret generatsiya qilish» amalidan foydalaning. "
                "Tayyor access/refresh tokenni ulashish uchun «Token berish» tugmasini bosing."
            ),
        }),
        ('Statistika', {
            'fields': ('token_version', 'request_count', 'last_used_at',
                       'created_at', 'updated_at'),
        }),
    )
    actions = ['rotate_secrets', 'revoke_all_tokens']

    # ── Qo'shimcha admin sahifasi: token berish ──────────────────────────────

    def get_urls(self):
        urls = super().get_urls()
        custom = [
            path(
                '<uuid:pk>/tokens/',
                self.admin_site.admin_view(self.issue_tokens_view),
                name='partner_partnerclient_tokens',
            ),
        ]
        return custom + urls

    @admin.display(description='Tokenlar')
    def token_button(self, obj):
        url = reverse('admin:partner_partnerclient_tokens', args=[obj.pk])
        return format_html('<a class="button" href="{}">Token berish</a>', url)

    def issue_tokens_view(self, request, pk):
        """
        Hamkorga berish uchun tayyor access + refresh tokenni ko'rsatadi.
        GET  — sahifa (tokensiz, faqat tushuntirish)
        POST — yangi juftlik generatsiya qilinadi va ekranda ko'rsatiladi
        """
        client = get_object_or_404(PartnerClient, pk=pk)
        if not self.has_change_permission(request, client):
            raise Http404()

        tokens = None
        if request.method == 'POST' and request.POST.get('action') == 'revoke':
            client.revoke_tokens()
            messages.warning(
                request,
                f'{client.name} uchun berilgan barcha tokenlar bekor qilindi.',
            )
            return redirect(request.path)

        if request.method == 'POST':
            if not client.is_active:
                messages.error(request, 'Mijoz faol emas — avval «Faol» belgisini yoqing.')
                return redirect(request.path)
            tokens = issue_pair(client)
            messages.success(
                request,
                f'{client.name} uchun yangi token juftligi berildi. '
                'Access token 1 soat, refresh token 30 kun amal qiladi.',
            )

        context = {
            **self.admin_site.each_context(request),
            'title':       f'{client.name} — API tokenlari',
            'opts':        self.model._meta,
            'client':      client,
            'tokens':      tokens,
            'api_base':    partner_api_base(request),
            'has_view_permission': True,
        }
        return render(request, 'admin/partner/issue_tokens.html', context)

    # ── Secret ───────────────────────────────────────────────────────────────

    @admin.display(description='Foydalanish')
    def usage_hint(self, obj):
        if not obj.pk:
            return '—'
        return format_html(
            '<code>POST /api/partner/auth/token/</code><br>'
            '<code>{{"client_id": "{}", "client_secret": "…"}}</code>',
            obj.client_id,
        )

    def save_model(self, request, obj, form, change):
        """Yangi mijoz yaratilganda secret generatsiya qilib, bir marta ko'rsatamiz."""
        new_secret = None
        if not obj.secret_hash:
            new_secret = generate_client_secret()
            obj.set_secret(new_secret)
        super().save_model(request, obj, form, change)
        if new_secret:
            messages.warning(
                request,
                f'client_id: {obj.client_id}  ·  client_secret: {new_secret} — '
                'bu qiymat boshqa ko\'rsatilmaydi, hoziroq nusxalab oling!',
            )

    @admin.action(description='Berilgan barcha tokenlarni bekor qilish')
    def revoke_all_tokens(self, request, queryset):
        for client in queryset:
            client.revoke_tokens()
            messages.warning(
                request,
                f'{client.name} — barcha access/refresh tokenlar bekor qilindi. '
                'Hamkorga yangi token bering.',
            )

    @admin.action(description='Yangi client_secret generatsiya qilish')
    def rotate_secrets(self, request, queryset):
        for client in queryset:
            raw = client.rotate_secret()
            messages.warning(
                request,
                f'{client.name} → client_id: {client.client_id}  ·  '
                f'yangi client_secret: {raw} — hoziroq nusxalab oling!',
            )
