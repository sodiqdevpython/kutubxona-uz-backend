"""
Admin «Boshqaruv paneli» — bitta so'rovda hamma statistika.

GET /api/admin/dashboard/        (60 soniya kesh; ?fresh=1 — yangidan)

  date, counts{...}, queue[...], upcoming_issue, activity[...],
  notifications[...], nav_counts{...}

Alohida "harakatlar jurnali" jadvali yo'q — so'nggi harakatlar mavjud
yozuvlardan (topshirishlar, sonlar, parser natijalari) hosil qilinadi.
"""
from datetime import timedelta

from django.core.cache import cache
from django.db.models import Count, Max, Q, Sum
from django.utils import timezone
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.articles.models import Article, ArticleSubmission, ParsedArticle, ViewDay
from apps.authors.models import Author
from apps.chat.models import Chat
from apps.journals.models import Issue

from .views import IsStaff

CACHE_KEY = 'admin:dashboard:v1'
CACHE_TTL = 60
OVERDUE_DAYS = 5


def short_name(name: str) -> str:
    """«Fayzi Bekkamov» → «F. Bekkamov»."""
    parts = (name or '').split()
    if len(parts) >= 2:
        return f'{parts[0][0]}. {parts[-1]}'
    return name or "Noma'lum"


def issue_label(issue) -> str:
    return f'{issue.year} № {issue.number}'


def _abs(request, field):
    if not field:
        return None
    try:
        return request.build_absolute_uri(field.url)
    except Exception:
        return None


def build_dashboard(request) -> dict:
    now   = timezone.now()
    today = timezone.localdate()

    # ── Topshirishlar ──────────────────────────────────────────────────────
    pending_qs = ArticleSubmission.objects.filter(status='pending')
    pending    = pending_qs.count()
    limit      = now - timedelta(days=OVERDUE_DAYS)
    overdue    = pending_qs.filter(
        Q(submitted_at__lt=limit) | Q(submitted_at__isnull=True, created_at__lt=limit)
    ).count()
    oldest_days = 0
    oldest = pending_qs.order_by('submitted_at', 'created_at').first()
    if oldest:
        oldest_days = max(0, (now - (oldest.submitted_at or oldest.created_at)).days)

    # ── Nashr etilgan maqolalar ───────────────────────────────────────────
    published = Article.objects.filter(issue__isnull=False)
    q_month   = ((today.month - 1) // 3) * 3 + 1
    q_start   = today.replace(month=q_month, day=1)
    published_quarter = published.filter(published_at__gte=q_start).count()

    # ── Mualliflar ────────────────────────────────────────────────────────
    authors_total      = Author.objects.count()
    authors_incomplete = Author.objects.filter(Q(org='') | Q(orcid='')).count()

    # ── Ko'rishlar (30 kun) ───────────────────────────────────────────────
    d30 = today - timedelta(days=29)
    d60 = today - timedelta(days=59)
    views_30   = ViewDay.objects.filter(date__gte=d30).aggregate(s=Sum('views'))['s'] or 0
    views_prev = ViewDay.objects.filter(date__gte=d60, date__lt=d30).aggregate(s=Sum('views'))['s'] or 0
    views_delta = round((views_30 - views_prev) / views_prev * 100) if views_prev else None

    # ── Xabarlar ──────────────────────────────────────────────────────────
    unread_chats = Chat.objects.filter(unread_count__gt=0)
    unread_count = unread_chats.count()
    oldest_chat  = unread_chats.order_by('last_message_at').first()
    unread_hours = 0
    if oldest_chat and oldest_chat.last_message_at:
        unread_hours = max(0, int((now - oldest_chat.last_message_at).total_seconds() // 3600))

    # ── Tayyorlanayotgan son ──────────────────────────────────────────────
    drafts   = Issue.objects.filter(is_upcoming=True).order_by('-created_at')
    upcoming = drafts.first()
    upcoming_data = None
    if upcoming:
        n_art = Article.objects.filter(issue=upcoming).count()
        steps = [n_art > 0, bool(upcoming.cover_image), bool(upcoming.pdf_file)]
        upcoming_data = {
            'id':         str(upcoming.id),
            'label':      f'{upcoming.year} · № {upcoming.number}',
            'status':     'Tayyorlanmoqda',
            'cover_url':  _abs(request, upcoming.cover_image),
            'articles':   n_art,
            'has_cover':  steps[1],
            'has_pdf':    steps[2],
            'steps_done': sum(steps),
            'steps':      len(steps),
            'note':       'PDF hali yuklanmagan' if not steps[2] else 'PDF yuklangan',
            'days':       max(0, (now - upcoming.created_at).days),
        }

    # ── Ish navbati ───────────────────────────────────────────────────────
    queue = [{
        'key':   'submissions',
        'title': 'Botdan kelgan yangi maqolalar',
        'sub':   "Ko'rib chiqib songa biriktirish kerak",
        'meta':  f'eng eskisi {oldest_days} kun' if pending else '—',
        'count': pending, 'unit': 'ta', 'color': 'accent', 'to': '/admin/submissions',
    }]
    if unread_count:
        queue.append({
            'key':   'chats',
            'title': 'Javob berilmagan xabarlar',
            'sub':   'Mualliflar savoliga javob kutilmoqda',
            'meta':  f'{unread_hours} soat' if unread_hours else 'hozirgina',
            'count': unread_count, 'unit': 'ta', 'color': 'blue', 'to': '/admin/chat',
        })
    if upcoming_data:
        queue.append({
            'key':   'draft-issue',
            'title': f"{upcoming.year} № {upcoming.number} soni qoralama holatida",
            'sub':   f"{upcoming_data['articles']} maqola biriktirilgan, "
                     f"PDF {'yuklangan' if upcoming_data['has_pdf'] else 'yuklanmagan'}",
            'meta':  f"{upcoming_data['days']} kun",
            'count': drafts.count(), 'unit': 'son', 'color': 'ink', 'to': '/admin/journals',
        })
    if authors_incomplete:
        queue.append({
            'key':   'authors',
            'title': "To'liqsiz muallif profillari",
            'sub':   'Tashkilot yoki ORCID kiritilmagan',
            'meta':  '–',
            'count': authors_incomplete, 'unit': 'ta', 'color': 'muted', 'to': '/admin/authors',
        })

    # ── So'nggi harakatlar (mavjud yozuvlardan) ───────────────────────────
    events = []
    subs = (ArticleSubmission.objects.exclude(status='draft')
            .select_related('author', 'article', 'article__issue').order_by('-updated_at')[:20])
    for s in subs:
        title = s.title or 'Sarlavhasiz maqola'
        arrived = s.submitted_at or s.created_at
        sender = s.tg_name or (s.author.name if s.author else '')
        events.append({
            'kind': 'submitted', 'time': arrived,
            'text': f'{short_name(sender)} botdan yangi maqola yubordi',
            'who':  'Telegram bot',
        })
        if s.status == 'approved':
            extra = ''
            if s.article and s.article.issue:
                extra = f' va {issue_label(s.article.issue)} soniga qo\'shildi'
            events.append({'kind': 'approved', 'time': s.updated_at,
                           'text': f'«{title}» tasdiqlandi{extra}', 'who': 'Tahririyat'})
        elif s.status == 'rejected':
            reason = (s.reject_reason or '').strip()
            extra  = f' — {reason[:70]}' if reason else ''
            events.append({'kind': 'rejected', 'time': s.updated_at,
                           'text': f'«{title}» rad etildi{extra}', 'who': 'Tahririyat'})
    for i in Issue.objects.order_by('-created_at')[:6]:
        events.append({'kind': 'issue', 'time': i.created_at,
                       'text': f"{issue_label(i)} soni {'qoralama sifatida ' if i.is_upcoming else ''}yaratildi",
                       'who': 'Tahririyat'})
    try:
        batches = (ParsedArticle.objects.values('issue_id')
                   .annotate(n=Count('id'), t=Max('created_at')).order_by('-t')[:6])
        issues_by_id = {str(i.id): i for i in Issue.objects.filter(id__in=[b['issue_id'] for b in batches])}
        for b in batches:
            iss = issues_by_id.get(str(b['issue_id']))
            label = issue_label(iss) if iss else 'Jurnal soni'
            events.append({'kind': 'parsed', 'time': b['t'],
                           'text': f"{label} PDF'idan {b['n']} maqola avtomatik ajratildi",
                           'who': 'PDF parser'})
    except Exception:
        pass
    events = [e for e in events if e['time']]
    events.sort(key=lambda e: e['time'], reverse=True)
    activity = [{**e, 'time': e['time'].isoformat()} for e in events[:8]]

    # ── Bildirishnomalar (so'nggi 7 kun) ─────────────────────────────────
    week = now - timedelta(days=7)
    notes = []
    for s in pending_qs.filter(Q(submitted_at__gte=week) | Q(created_at__gte=week)).order_by('-submitted_at', '-created_at')[:6]:
        notes.append({'id': f'sub:{s.id}', 'kind': 'submission',
                      'text': f'{short_name(s.tg_name)} yangi maqola yubordi',
                      'time': (s.submitted_at or s.created_at).isoformat(), 'to': f'/admin/submissions/{s.id}'})
    for c in unread_chats.select_related('author').order_by('-last_message_at')[:6]:
        notes.append({'id': f'chat:{c.id}', 'kind': 'chat',
                      'text': f'{short_name(c.author.name)} xabariga javob berilmagan',
                      'time': (c.last_message_at or c.created_at).isoformat(),
                      'to': f'/admin/chat?author={c.author.slug}'})
    for e in [e for e in events if e['kind'] == 'parsed' and e['time'] >= week][:3]:
        notes.append({'id': f"parsed:{e['time'].isoformat()}", 'kind': 'parsed',
                      'text': e['text'], 'time': e['time'].isoformat(), 'to': '/admin/journals'})
    notes.sort(key=lambda n: n['time'], reverse=True)

    return {
        'date': today.isoformat(),
        'counts': {
            'pending':            pending,
            'pending_overdue':    overdue,
            'pending_oldest_days': oldest_days,
            'published':          published.count(),
            'published_quarter':  published_quarter,
            'authors':            authors_total,
            'authors_incomplete': authors_incomplete,
            'views_30d':          views_30,
            'views_delta_pct':    views_delta,
            'issues':             Issue.objects.count(),
            'unread_chats':       unread_count,
        },
        'queue':          queue,
        'upcoming_issue': upcoming_data,
        'activity':       activity,
        'notifications':  notes[:10],
    }


class AdminDashboardView(APIView):
    permission_classes = [IsStaff]

    def get(self, request):
        fresh = request.query_params.get('fresh') == '1'
        data = None if fresh else cache.get(CACHE_KEY)
        if data is None:
            data = build_dashboard(request)
            cache.set(CACHE_KEY, data, CACHE_TTL)
        return Response(data)


def invalidate_dashboard() -> None:
    cache.delete(CACHE_KEY)
