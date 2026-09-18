from django.contrib import admin, messages
from django.http import HttpResponseRedirect
from django.shortcuts import render
from django.urls import path, reverse
from django.utils.html import format_html

from .forms import MergeFieldsForm, MergePickForm
from .merge import MergeError, merge_authors, merge_preview
from .models import Author, AuthorAlias


@admin.register(Author)
class AuthorAdmin(admin.ModelAdmin):
    list_display    = ('name', 'initials', 'role', 'org', 'article_count',
                       'telegram_username', 'source')
    list_filter     = ('source',)
    search_fields   = ('name', 'org', 'role', 'telegram_username')
    readonly_fields = ('slug', 'initials')
    actions         = ['merge_selected']

    change_list_template = 'admin/authors/author/change_list.html'

    # ── Qo'shimcha URL ───────────────────────────────────────────────────────

    def get_urls(self):
        return [
            path(
                'merge/',
                self.admin_site.admin_view(self.merge_view),
                name='authors_author_merge',
            ),
        ] + super().get_urls()

    @admin.action(description="Tanlangan 2 profilni birlashtirish")
    def merge_selected(self, request, queryset):
        ids = list(queryset.values_list('pk', flat=True)[:3])
        if len(ids) != 2:
            self.message_user(
                request,
                "Birlashtirish uchun ANIQ 2 ta profil tanlang.",
                level=messages.ERROR,
            )
            return None
        url = reverse('admin:authors_author_merge')
        return HttpResponseRedirect(f'{url}?target={ids[0]}&source={ids[1]}')

    # ── Birlashtirish sahifasi ───────────────────────────────────────────────

    def merge_view(self, request):
        """
        1-qadam — ikkita profil tanlanadi (autocomplete).
        2-qadam — har bir maydon qaysi profildan olinishi tanlanadi.
        3-qadam — tasdiqlash va birlashtirish.
        """
        if not self.has_delete_permission(request) or not self.has_change_permission(request):
            messages.error(request, "Bu amal uchun ruxsatingiz yo'q.")
            return HttpResponseRedirect(reverse('admin:authors_author_changelist'))

        context = {
            **self.admin_site.each_context(request),
            'title': 'Profillarni birlashtirish',
            'opts':  self.model._meta,
        }

        # ── Qaysi profillar? (GET parametr yoki 1-qadam formasi) ─────────────
        target = _get_author(request.GET.get('target') or request.POST.get('target_id'))
        source = _get_author(request.GET.get('source') or request.POST.get('source_id'))

        if request.method == 'POST' and request.POST.get('step') == 'pick':
            pick = MergePickForm(request.POST)
            if pick.is_valid():
                target = pick.cleaned_data['target']
                source = pick.cleaned_data['source']
            else:
                context['pick_form'] = pick
                return render(request, 'admin/authors/merge.html', context)

        if not target or not source or target.pk == source.pk:
            context['pick_form'] = MergePickForm(
                initial={'target': target, 'source': source} if target or source else None
            )
            if target and source and target.pk == source.pk:
                messages.warning(request, "Ikkala maydonda bir xil profil tanlangan.")
            return render(request, 'admin/authors/merge.html', context)

        # ── Maydonlarni tanlash / birlashtirish ─────────────────────────────
        if request.method == 'POST' and request.POST.get('step') == 'merge':
            fields_form = MergeFieldsForm(request.POST, target=target, source=source)
            if fields_form.is_valid():
                try:
                    report = merge_authors(target, source, fields_form.choices())
                except MergeError as exc:
                    messages.error(request, str(exc))
                else:
                    messages.success(request, _report_text(report))
                    return HttpResponseRedirect(
                        reverse('admin:authors_author_change', args=[target.pk])
                    )
        else:
            fields_form = MergeFieldsForm(target=target, source=source)

        context.update({
            'target':       target,
            'source':       source,
            'fields_form':  fields_form,
            'preview':      merge_preview(target, source),
        })
        return render(request, 'admin/authors/merge.html', context)


@admin.register(AuthorAlias)
class AuthorAliasAdmin(admin.ModelAdmin):
    list_display  = ('slug', 'author_link', 'note', 'created_at')
    search_fields = ('slug', 'author__name')
    readonly_fields = ('created_at', 'updated_at')

    @admin.display(description='Muallif')
    def author_link(self, obj):
        url = reverse('admin:authors_author_change', args=[obj.author_id])
        return format_html('<a href="{}">{}</a>', url, obj.author.name)


# ── Yordamchilar ─────────────────────────────────────────────────────────────

def _get_author(pk):
    if not pk:
        return None
    try:
        return Author.objects.get(pk=pk)
    except (Author.DoesNotExist, ValueError, TypeError):
        return None


def _report_text(report: dict) -> str:
    parts = [
        f'«{report["source"]}» profili «{report["target"]}» ga qo\'shildi.',
        f'{report["articles_moved"]} ta maqola ko\'chdi',
    ]
    if report['articles_skipped']:
        parts.append(f'{report["articles_skipped"]} ta takroriy bog\'lanish olib tashlandi')
    if report['submissions_moved']:
        parts.append(f'{report["submissions_moved"]} ta topshiriq ko\'chdi')
    if report['messages_moved']:
        parts.append(f'{report["messages_moved"]} ta chat xabari ko\'chdi')
    elif report['chat_moved']:
        parts.append('chat ko\'chdi')
    if report['alias_slugs']:
        parts.append(f'eski manzil(lar) saqlandi: {", ".join(report["alias_slugs"])}')
    return parts[0] + ' ' + ', '.join(parts[1:]) + '.'
