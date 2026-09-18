"""
Ikki muallif profilini bitta qilib birlashtirish.

Nega kerak: bitta odam ba'zan kirill, ba'zan lotin yozuvida kelib qoladi
("Абдуллаев Ботир" va "Abdullayev Botir") — natijada ikkita alohida profil
paydo bo'ladi. Bu modul ularni yagona profilga qo'shadi.

Nima ko'chadi:
  • maqolalar (ArticleAuthor) — takrorlanmasdan, tartibi saqlanib
  • Telegram topshiriqlari (ArticleSubmission)
  • chat va undagi barcha xabarlar
  • profil ko'rishlari soni — qo'shiladi
  • eski slug — `AuthorAlias` ga yoziladi, shuning uchun eski havolalar
    ishlashda davom etadi

Qaysi maydon qaysi profildan olinishini admin o'zi tanlaydi
(`field_choices` — har bir maydon uchun 'target' yoki 'source').
"""
import logging

from django.db import transaction
from django.db.models import F

from .models import Author, AuthorAlias

logger = logging.getLogger(__name__)

# Admin tanlovi qo'llaniladigan maydonlar: (kod, ko'rinadigan nom)
MERGE_FIELDS = [
    ('name',              'F.I.Sh.'),
    ('slug',              'Slug (URL)'),
    ('initials',          'Bosh harflar'),
    ('role',              'Lavozim'),
    ('org',               'Tashkilot'),
    ('degree',            'Ilmiy daraja'),
    ('bio',               'Tarjimai hol'),
    ('avatar',            'Rasm'),
    ('avatar_idx',        'Avatar rangi'),
    ('source',            'Manba'),
    ('telegram_chat_id',  'Telegram chat ID'),
    ('telegram_username', 'Telegram @username'),
]

# Bu maydonlar bazada unique — konflikt bo'lmasligi uchun avval
# yo'qoladigan profildan tozalanadi
UNIQUE_FIELDS = ('slug', 'telegram_chat_id')


class MergeError(Exception):
    pass


def merge_preview(target: Author, source: Author) -> dict:
    """Birlashtirishdan oldin nima ko'chishini ko'rsatadi (hech narsa o'zgarmaydi)."""
    from apps.articles.models import ArticleAuthor, ArticleSubmission
    from apps.chat.models import Chat, Message

    target_article_ids = set(
        ArticleAuthor.objects.filter(author=target).values_list('article_id', flat=True)
    )
    source_links = ArticleAuthor.objects.filter(author=source)
    source_article_ids = set(source_links.values_list('article_id', flat=True))

    source_chat = Chat.objects.filter(author=source).first()
    target_chat = Chat.objects.filter(author=target).first()

    return {
        'articles_moving':    len(source_article_ids - target_article_ids),
        'articles_duplicate': len(source_article_ids & target_article_ids),
        'submissions':        ArticleSubmission.objects.filter(author=source).count(),
        'source_has_chat':    source_chat is not None,
        'target_has_chat':    target_chat is not None,
        'chat_messages':      Message.objects.filter(chat=source_chat).count() if source_chat else 0,
        'profile_views_sum':  (target.profile_views or 0) + (source.profile_views or 0),
    }


@transaction.atomic
def merge_authors(target: Author, source: Author, field_choices: dict) -> dict:
    """
    `source` profilini `target` ga qo'shadi va `source` ni o'chiradi.

    field_choices — {'name': 'target'|'source', …}. Ko'rsatilmagan maydon
    `target` dagicha qoladi.

    Qaytaradi: nima qilinganining qisqacha hisoboti.
    """
    if target.pk == source.pk:
        raise MergeError('Bir xil profilni o\'zi bilan birlashtirib bo\'lmaydi.')

    # Qulflab olamiz — parallel tahrir bilan urishmasin
    target = Author.objects.select_for_update().get(pk=target.pk)
    source = Author.objects.select_for_update().get(pk=source.pk)

    report = {
        'target':             target.name,
        'source':             source.name,
        'articles_moved':     0,
        'articles_skipped':   0,
        'submissions_moved':  0,
        'messages_moved':     0,
        'chat_moved':         False,
        'alias_slugs':        [],
    }

    # ── 1. Tanlangan qiymatlarni oldindan o'qib olamiz ───────────────────────
    chosen = {}
    for field, _label in MERGE_FIELDS:
        if field_choices.get(field) == 'source':
            chosen[field] = getattr(source, field)

    # ── 2. Maqolalar (ArticleAuthor) ─────────────────────────────────────────
    from apps.articles.models import ArticleAuthor, ArticleSubmission

    target_article_ids = set(
        ArticleAuthor.objects.filter(author=target).values_list('article_id', flat=True)
    )
    for link in ArticleAuthor.objects.filter(author=source).select_related('article'):
        if link.article_id in target_article_ids:
            # Ikkala profil ham shu maqolaga bog'langan — dublikatni o'chiramiz
            link.delete()
            report['articles_skipped'] += 1
        else:
            link.author = target
            link.save(update_fields=['author', 'updated_at'])
            target_article_ids.add(link.article_id)
            report['articles_moved'] += 1

    # ── 3. Telegram topshiriqlari ────────────────────────────────────────────
    report['submissions_moved'] = ArticleSubmission.objects.filter(
        author=source
    ).update(author=target)

    # ── 4. Chat va xabarlar ──────────────────────────────────────────────────
    from apps.chat.models import Chat, Message

    source_chat = Chat.objects.filter(author=source).first()
    if source_chat:
        target_chat = Chat.objects.filter(author=target).first()
        if target_chat:
            # Ikkalasida ham chat bor — xabarlarni target chatga ko'chiramiz
            report['messages_moved'] = Message.objects.filter(
                chat=source_chat
            ).update(chat=target_chat)

            target_chat.unread_count = (target_chat.unread_count or 0) + (source_chat.unread_count or 0)
            stamps = [s for s in (target_chat.last_message_at, source_chat.last_message_at) if s]
            if stamps:
                target_chat.last_message_at = max(stamps)
            target_chat.is_blocked = target_chat.is_blocked or source_chat.is_blocked
            target_chat.save(update_fields=[
                'unread_count', 'last_message_at', 'is_blocked', 'updated_at',
            ])
            source_chat.delete()
        else:
            # Faqat source'da chat bor — uni target'ga o'tkazamiz
            source_chat.author = target
            source_chat.save(update_fields=['author', 'updated_at'])
            report['chat_moved'] = True

    # ── 5. Profil ko'rishlari — qo'shiladi ───────────────────────────────────
    Author.objects.filter(pk=target.pk).update(
        profile_views=F('profile_views') + (source.profile_views or 0)
    )

    # ── 6. Eski sluglarni alias sifatida saqlaymiz (havolalar buzilmasin) ────
    old_slugs = {source.slug}
    old_slugs.update(AuthorAlias.objects.filter(author=source).values_list('slug', flat=True))
    if chosen.get('slug'):
        # Target'ning slugi almashadi — eskisi ham alias bo'lsin
        old_slugs.add(target.slug)

    # ── 7. Unique maydonlarni source'dan bo'shatamiz (konflikt bo'lmasligi uchun)
    AuthorAlias.objects.filter(author=source).delete()
    source.slug = f'merged-{source.pk}'
    source.telegram_chat_id = None
    source.save(update_fields=['slug', 'telegram_chat_id', 'updated_at'])

    # ── 8. Tanlangan qiymatlarni target'ga yozamiz ───────────────────────────
    if chosen:
        for field, value in chosen.items():
            setattr(target, field, value)
        target.save(update_fields=list(chosen.keys()) + ['updated_at'])

    # ── 9. Source'ni o'chiramiz ──────────────────────────────────────────────
    source_name = source.name
    source.delete()

    # ── 10. Aliaslarni yozamiz (target saqlangandan keyin — slug aniq bo'lsin)
    target.refresh_from_db()
    for slug in sorted(s for s in old_slugs if s and s != target.slug):
        AuthorAlias.objects.get_or_create(
            slug=slug, defaults={'author': target, 'note': f'«{source_name}» bilan birlashtirildi'},
        )
        report['alias_slugs'].append(slug)

    # ── 11. Kesh ─────────────────────────────────────────────────────────────
    from utils.cache import bump_all
    bump_all()

    logger.info(
        'Profillar birlashtirildi: "%s" ← "%s" (%s maqola, %s topshiriq)',
        target.name, source_name, report['articles_moved'], report['submissions_moved'],
    )
    return report
