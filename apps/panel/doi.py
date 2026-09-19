"""
DOI va jurnal soniga biriktirish yordamchilari (admin panel).

DOI formati:  10.62499/kutubxona.<yil>.<son>.<tartib>
  tartib — maqolaning shu sondagi tartib raqami (02 ko'rinishida).
"""
from django.utils import timezone

from apps.articles.models import Article

DOI_PREFIX = '10.62499'


def make_doi(article: Article, issue) -> str:
    seq = Article.objects.filter(issue=issue).exclude(pk=article.pk).count() + 1
    return f'{DOI_PREFIX}/kutubxona.{issue.year}.{issue.number}.{seq:02d}'


def attach_to_issue(article: Article, issue) -> list[str]:
    """
    Maqolani songa biriktiradi (nashr sanasi, yil, DOI). Saqlamaydi —
    o'zgargan maydonlar ro'yxatini qaytaradi.
    """
    article.issue        = issue
    article.published_at = article.published_at or timezone.now().date()
    article.year         = issue.year
    changed = ['issue', 'published_at', 'year']
    if not article.doi:
        article.doi = make_doi(article, issue)
        changed.append('doi')
    return changed


def parse_int(value) -> int | None:
    try:
        n = int(str(value).strip())
        return n if n > 0 else None
    except (TypeError, ValueError):
        return None
