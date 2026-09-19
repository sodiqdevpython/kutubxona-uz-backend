from datetime import timedelta

from django.conf import settings
from django.contrib import admin, messages
from django.db.models import Q, Sum
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import path, reverse
from django.utils import timezone
from django.utils.html import format_html

from .models import PartnerClient, PartnerRequestDay, generate_client_secret
from .tokens import issue_pair
from .utils import partner_api_base


class RequestDayInline(admin.TabularInline):
    """So'nggi 14 kun — kunlik so'rovlar (faqat ko'rish uchun)."""
    model           = PartnerRequestDay
    extra           = 0
    can_delete      = False
    max_num         = 0
    fields          = ('date', 'count')
    readonly_fields = ('date', 'count')
    verbose_name_plural = "So'nggi 14 kun — kunlik so'rovlar"

    def get_queryset(self, request):
        since = timezone.localdate() - timedelta(days=13)
        return super().get_queryset(request).filter(date__gte=since).order_by('-date')

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(PartnerClient)
class PartnerClientAdmin(admin.ModelAdmin):
    list_display  = ('name', 'client_id', 'is_active', 'today_count', 'week_count',
                     'request_count', 'last_used_at', 'token_button')
    list_filter   = ('is_active',)
    search_fields = ('name', 'client_id', 'contact')
    readonly_fields = (
        'client_id', 'secret_hash', 'token_version', 'today_count', 'week_count',
        'request_count', 'last_used_at', 'created_at', 'updated_at', 'usage_hint',
    )
    inlines = [RequestDayInline]

    # Ro'yxat va tahrirlash sahifasi uchun «bugun» / «7 kun» yig'indilari — bitta so'rovda
    def get_queryset(self, request):
        today = timezone.localdate()
        return super().get_queryset(request).annotate(
            _today=Sum('days__count', filter=Q(days__date=today)),
            _week=Sum('days__count', filter=Q(days__date__gte=today - timedelta(days=6))),
        )

    @admin.display(description='Bugun', ordering='_today')
    def today_count(self, obj):
        return getattr(obj, '_today', None) or 0

    @admin.display(description="So'nggi 7 kun", ordering='_week')
    def week_count(self, obj):
        return getattr(obj, '_week', None) or 0
    fieldsets = (
        (None, {
            'fields': ('name', 'contact', 'note', 'is_active'),
        }),
        ('Kirish maʼlumotlari (ixtiyoriy)', {
            'classes': ('collapse',),
            'fields': ('client_id', 'secret_hash', 'usage_hint'),
            'description': (
                "Odatda kerak emas: hamkorga ro'yxatdagi «Tokenlarni olish» sahifasidan "
                "tayyor access/refresh berasiz. client_id + client_secret faqat hamkor "
                "tokenni o'zi olmoqchi bo'lsa kerak; secret yaratilganda bir marta ko'rsatiladi, "
                "yo'qolsa — «Yangi client_secret generatsiya qilish» amali."
            ),
        }),
        ('Statistika', {
            'fields': ('today_count', 'week_count', 'request_count', 'last_used_at',
                       'token_version', 'created_at', 'updated_at'),
            'description': (
                "«So'rovlar soni» — umumiy hisoblagich (64-bit, nolga tushmaydi); "
                "«Bugun» va «So'nggi 7 kun» kunlik yig'indilardan olinadi (90 kun saqlanadi)."
            ),
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
        return format_html('<a class="button" href="{}">Tokenlarni olish</a>', url)

    def issue_tokens_view(self, request, pk):
        """
        Hamkorga beriladigan 3 ta narsa: endpoint manzillari, access, refresh.
        Tokenlar holatsiz (JWT) — sahifa har ochilganda yangi juftlik beriladi,
        admin faqat nusxalab yuboradi.
        POST action=revoke — berilgan barcha tokenlarni bekor qilish.
        """
        client = get_object_or_404(PartnerClient, pk=pk)
        if not self.has_change_permission(request, client):
            raise Http404()

        secret_key = f'partner_secret_{client.pk}'

        if request.method == 'POST' and request.POST.get('action') == 'revoke':
            client.revoke_tokens()
            messages.warning(
                request,
                f'{client.name} uchun berilgan barcha tokenlar bekor qilindi.',
            )
            return redirect(request.path)

        if request.method == 'POST' and request.POST.get('action') == 'rotate':
            # Yangi parol (client_secret) — bir marta ko'rsatish uchun sessiyada
            request.session[secret_key] = client.rotate_secret()
            messages.success(request, f'{client.name} uchun yangi client_secret berildi.')
            return redirect(request.path)

        # Yaratilganda yoki yangilanganda saqlangan secret — faqat shu safar ko'rinadi
        new_secret = request.session.pop(secret_key, None)

        tokens = None
        if client.is_active:
            tokens = issue_pair(client)
            if request.method == 'POST':
                messages.success(request, f'{client.name} uchun yangi token juftligi berildi.')
        else:
            messages.error(request, 'Mijoz faol emas — «Faol» belgisini yoqing, keyin tokenlar chiqadi.')

        base = partner_api_base(request)
        context = {
            **self.admin_site.each_context(request),
            'title':        f'{client.name} — API tokenlari',
            'opts':         self.model._meta,
            'client':       client,
            'tokens':       tokens,
            'api_base':     base,
            'list_url':     f'{base}/api/partner/articles/',
            'detail_url':   f'{base}/api/partner/articles/<id>/',
            'refresh_url':  f'{base}/api/partner/auth/refresh/',
            'docs_url':     f'{base}/api/partner/docs/',
            'new_secret':   new_secret,
            'access_hours': round(settings.PARTNER_ACCESS_LIFETIME.total_seconds() / 3600, 1),
            'refresh_days': settings.PARTNER_REFRESH_LIFETIME.days,
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

    def response_add(self, request, obj, post_url_continue=None):
        """«Saqlash» bosilsa to'g'ridan-to'g'ri tokenlar sahifasiga — 3 ta narsa shu yerda."""
        if '_continue' not in request.POST and '_addanother' not in request.POST:
            return redirect(reverse('admin:partner_partnerclient_tokens', args=[obj.pk]))
        return super().response_add(request, obj, post_url_continue)

    def save_model(self, request, obj, form, change):
        """Yangi mijoz yaratilganda secret generatsiya qilib, bir marta ko'rsatamiz."""
        new_secret = None
        if not obj.secret_hash:
            new_secret = generate_client_secret()
            obj.set_secret(new_secret)
        super().save_model(request, obj, form, change)
        if new_secret:
            # Tokenlar sahifasida bir marta ko'rsatiladi (login/parol sifatida)
            request.session[f'partner_secret_{obj.pk}'] = new_secret
            messages.success(request, f'{obj.name} yaratildi — quyida hamkorga beriladigan ma\'lumotlar.')

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
