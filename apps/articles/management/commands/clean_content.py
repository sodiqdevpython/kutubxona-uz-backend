"""
Mavjud kontentni tozalash. Yangi ma'lumot to'qilmaydi — faqat:

  • sarlavha, annotatsiya va ismlardagi yozuv xatolari (aralash kirill/lotin,
    ligatura, apostrof, CAPS LOCK ismlar, PDF'da tushib qolgan apostroflar);
  • PDF parser allaqachon ajratgan bet oralig'i va jurnal rubrikasi
    `ParsedArticle` dan `Article` ga ko'chiriladi;
  • bitta profilga yozilgan bir necha muallif ajratiladi, ismi aynan bir xil
    profillar birlashtiriladi (slug `AuthorAlias` da saqlanadi);
  • muallifning parser ajratgan ish joyi `bio` dan `org` ga o'tadi;
  • maqola yili chiqqan son yiliga tenglashtiriladi.

Sukut bo'yicha faqat hisobot (o'zgarish saqlanmaydi):
    python manage.py clean_content
Saqlash uchun:
    python manage.py clean_content --apply
"""
from collections import defaultdict
from difflib import SequenceMatcher

from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Count, Max

from apps.articles.models import Article, ArticleAuthor, Category
from apps.authors.merge import MERGE_FIELDS, merge_authors
from apps.authors.models import Author, AuthorAlias
from apps.journals.models import Issue, Journal
from utils.cache import bump_all
from utils.text import detect_language, normalize_person_name, normalize_text, repair_title, sentence_case


def _key(name: str) -> str:
    return ' '.join(name.split()).casefold()


class Command(BaseCommand):
    help = "Mavjud kontentdagi yozuv xatolarini tozalaydi va parser ma'lumotlarini ko'chiradi"

    def add_arguments(self, parser):
        parser.add_argument('--apply', action='store_true', help="O'zgarishlarni saqlash (sukut bo'yicha faqat hisobot)")

    def handle(self, *args, **options):
        self.stats = defaultdict(int)
        self.notes = []
        with transaction.atomic():
            self._journals()
            self._categories()
            self._articles()
            self._split_combined_authors()
            self._normalize_author_names()
            self._author_orgs()
            self._issue_pages()
            self._report_similar_authors()
            if not options['apply']:
                transaction.set_rollback(True)

        for name, count in sorted(self.stats.items()):
            self.stdout.write(f'{name}: {count}')
        for note in self.notes:
            self.stdout.write(note)
        if options['apply']:
            bump_all()
            self.stdout.write(self.style.SUCCESS('Saqlandi, kesh yangilandi.'))
        else:
            self.stdout.write(self.style.WARNING('Faqat hisobot. Saqlash uchun: --apply'))

    def _journals(self):
        self.stats["jurnal nomi to'g'rilandi"] += Journal.objects.filter(title='Kutubxona Arxivi').update(title='Kutubxona')

    def _articles(self):
        for article in Article.objects.select_related('issue', 'parsed_source').iterator():
            changes = {}

            title = repair_title(article.title)
            if title != article.title:
                changes['title'] = title
                self.notes.append(f'sarlavha: {article.title!r} → {title!r}')
            excerpt = normalize_text(article.excerpt)
            if excerpt != article.excerpt:
                changes['excerpt'] = excerpt
            names = ', '.join(normalize_person_name(n) for n in article.author_names.split(',') if n.strip())
            if names != article.author_names:
                changes['author_names'] = names
            language = detect_language(title)
            if language != article.language:
                changes['language'] = language
            if article.issue_id and article.year != article.issue.year:
                changes['year'] = article.issue.year
                self.stats['yil songa moslandi'] += 1

            parsed = getattr(article, 'parsed_source', None)
            if parsed:
                if article.page_start is None and parsed.start_page:
                    changes['page_start'] = parsed.start_page
                if article.page_end is None and parsed.end_page:
                    changes['page_end'] = parsed.end_page
                if not article.pages and parsed.start_page and parsed.end_page:
                    changes['pages'] = parsed.end_page - parsed.start_page + 1
                if 'page_start' in changes:
                    self.stats["bet oralig'i ko'chirildi"] += 1
                section = sentence_case(parsed.section or '')
                if section and not article.category_id:
                    category, created = Category.objects.get_or_create(name=section)
                    changes['category'] = category
                    self.stats['rubrika biriktirildi'] += 1
                    self.stats['yangi rubrika'] += int(created)

            if changes:
                # .update(): slug va updated_at o'zgarmaydi
                Article.objects.filter(pk=article.pk).update(**changes)
                self.stats["maqola yangilandi"] += 1

    def _find_or_create_author(self, name: str) -> tuple[Author, bool]:
        for author in Author.objects.filter(name__iexact=name):
            return author, False
        for author in Author.objects.all():
            if _key(normalize_person_name(author.name)) == _key(name):
                return author, False
        return Author.objects.create(name=name, source='parser'), True

    def _split_combined_authors(self):
        for combined in Author.objects.filter(name__contains=',', source='parser'):
            names = [normalize_person_name(n) for n in combined.name.split(',') if n.strip()]
            if len(names) < 2:
                continue
            people = [self._find_or_create_author(n) for n in names]
            for link in ArticleAuthor.objects.filter(author=combined):
                article_id, base = link.article_id, link.order
                link.delete()
                for offset, (person, _created) in enumerate(people):
                    ArticleAuthor.objects.get_or_create(
                        article_id=article_id, author=person, defaults={'order': base + offset},
                    )
            first, first_created = people[0]
            if combined.avatar and first_created:
                first.avatar = combined.avatar.name
                first.save(update_fields=['avatar', 'updated_at'])
            AuthorAlias.objects.get_or_create(slug=combined.slug, defaults={'author': first})
            self.notes.append(f'ajratildi: {combined.name!r} → {names}')
            if combined.bio:
                self.notes.append(f"  qo'lda tekshiring, ish joyi ajratilmadi: {combined.bio!r}")
            combined.delete()
            self.stats['profil ajratildi'] += 1

    def _normalize_author_names(self):
        groups = defaultdict(list)
        for author in Author.objects.annotate(n=Count('articles')).order_by('-n', 'created_at'):
            name = normalize_person_name(author.name)
            if name != author.name:
                Author.objects.filter(pk=author.pk).update(name=name)
                author.name = name
                self.stats['ism yozuvi tuzatildi'] += 1
            groups[_key(name)].append(author)

        for same in groups.values():
            target = same[0]
            for source in same[1:]:
                if target.telegram_chat_id and source.telegram_chat_id:
                    self.notes.append(f"birlashtirilmadi (ikkalasida Telegram bor): {source.name!r}")
                    continue
                choices = {
                    field: 'source'
                    for field, _label in MERGE_FIELDS
                    if field != 'slug' and not getattr(target, field) and getattr(source, field)
                }
                merge_authors(target, source, choices)
                target.refresh_from_db()
                self.notes.append(f'birlashtirildi: {source.name!r} → {target.name!r}')
                self.stats['profil birlashtirildi'] += 1

    def _author_orgs(self):
        for author in Author.objects.filter(org='', source='parser').exclude(bio=''):
            text = normalize_text(author.bio)
            if len(text) > 300:
                continue
            Author.objects.filter(pk=author.pk).update(org=text, bio='')
            self.stats["ish joyi bio'dan ko'chirildi"] += 1
        for author in Author.objects.exclude(org=''):
            text = normalize_text(author.org)
            if text != author.org:
                Author.objects.filter(pk=author.pk).update(org=text)
                self.stats['ish joyi yozuvi tuzatildi'] += 1

    def _categories(self):
        for category in Category.objects.all():
            name = normalize_text(category.name)
            if name != category.name:
                Category.objects.filter(pk=category.pk).update(name=name)
                self.stats['rubrika nomi tuzatildi'] += 1

    def _issue_pages(self):
        for issue in Issue.objects.filter(total_pages=0):
            last = issue.parsed_articles.aggregate(m=Max('end_page'))['m']
            if last:
                Issue.objects.filter(pk=issue.pk).update(total_pages=last)
                self.stats['son hajmi hisoblandi'] += 1

    def _report_similar_authors(self):
        names = list(Author.objects.values_list('name', flat=True))
        for i, first in enumerate(names):
            for second in names[i + 1:]:
                if first[:1].casefold() != second[:1].casefold():
                    continue
                if SequenceMatcher(None, first.casefold(), second.casefold()).ratio() >= 0.9:
                    self.notes.append(f"o'xshash ismlar (birlashtirilmadi, qo'lda tekshiring): {first!r} / {second!r}")
