"""
Qidiruv botlari uchun server HTML, robots.txt va sitemap.xml.

Sayt SPA: serverdan bo'sh <div id="root"> keladi, Google Scholar va havola
ko'rinishlari esa JavaScript'ni bajarmaydi. Frontend nginx bot User-Agent'larini
shu yerga yo'naltiradi — sahifadagi ma'lumotlarning o'zi, citation_* teglari bilan.
"""
from django.conf import settings
from django.http import Http404, HttpResponse, HttpResponsePermanentRedirect
from django.shortcuts import get_object_or_404, render
from django.utils.html import strip_tags
from django.views.decorators.cache import cache_page
from django.views.decorators.http import require_GET
from xml.sax.saxutils import escape

from apps.authors.models import Author, AuthorAlias
from apps.central_asia.models import CentralAsiaPost
from apps.journals.models import Issue

from .models import Article

STATIC_PATHS = ['/', '/articles', '/archive', '/authors', '/central-asia',
                '/about', '/about/board', '/about/policy', '/about/guide']
SITE_NAME = 'Kutubxona.uz'
SITE_ISSN = '2181-1732'
BODY_LIMIT = 60000


def _site() -> str:
    return settings.SITE_URL.rstrip('/')


def _absolute(request, file_field) -> str:
    return request.build_absolute_uri(file_field.url) if file_field else ''


def _paragraphs(html: str) -> list[str]:
    """Parser HTML'idan xavfsiz matn: teglar olib tashlanadi, shablon yana ekranlaydi."""
    text = strip_tags((html or '')[:BODY_LIMIT].replace('</p>', '\n'))
    return [line.strip() for line in text.splitlines() if line.strip()]


@require_GET
def robots_txt(request):
    lines = [
        'User-agent: *',
        'Disallow: /admin',
        'Disallow: /login',
        'Disallow: /api/',
        '',
        f'Sitemap: {_site()}/sitemap.xml',
        '',
    ]
    return HttpResponse('\n'.join(lines), content_type='text/plain; charset=utf-8')


@require_GET
@cache_page(60 * 60)
def sitemap_xml(request):
    site = _site()
    entries = [(f'{site}{path}', None) for path in STATIC_PATHS]
    for issue in Issue.objects.filter(is_upcoming=False):
        entries.append((f'{site}/archive/{issue.id}', issue.updated_at))
    for article in Article.objects.filter(issue__isnull=False).only('slug', 'updated_at'):
        entries.append((f'{site}/articles/{article.slug}', article.updated_at))
    for author in Author.objects.filter(articles__issue__isnull=False).distinct().only('slug', 'updated_at'):
        entries.append((f'{site}/authors/{author.slug}', author.updated_at))
    for post in CentralAsiaPost.objects.filter(is_published=True).only('slug', 'updated_at'):
        entries.append((f'{site}/central-asia/{post.slug}', post.updated_at))

    body = ['<?xml version="1.0" encoding="UTF-8"?>',
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for url, modified in entries:
        lastmod = f'<lastmod>{modified.date().isoformat()}</lastmod>' if modified else ''
        body.append(f'<url><loc>{escape(url)}</loc>{lastmod}</url>')
    body.append('</urlset>')
    return HttpResponse('\n'.join(body), content_type='application/xml; charset=utf-8')


@require_GET
def home_page(request):
    issues = Issue.objects.filter(is_upcoming=False).select_related('journal').order_by('-year', '-number')
    return render(request, 'seo/home.html', {
        'site_name': SITE_NAME, 'canonical': f'{_site()}/', 'issues': issues,
        'issn': SITE_ISSN, 'lang': 'uz-Latn',
    })


@require_GET
def article_page(request, slug):
    article = get_object_or_404(
        Article.objects.select_related('issue', 'issue__journal', 'category').prefetch_related('authors', 'keywords'),
        slug=slug, issue__isnull=False,
    )
    issue = article.issue
    authors = [a.name for a in article.authors.all().order_by('articleauthor__order')] or article.author_names_list
    canonical = f'{_site()}/articles/{article.slug}'
    return render(request, 'seo/article.html', {
        'site_name': SITE_NAME,
        'canonical': canonical,
        'lang': {'uz': 'uz-Latn', 'uz-cyrl': 'uz-Cyrl'}.get(article.language, article.language),
        'citation_lang': article.language.split('-')[0],
        'article': article,
        'issue': issue,
        'authors': authors,
        'journal': issue.journal.title,
        'issn': issue.journal.issn or SITE_ISSN,
        'keywords': [k.name for k in article.keywords.all()],
        'description': article.excerpt or f'{", ".join(authors)}. {issue.journal.title}, {issue.year}, № {issue.number}.',
        'pdf_url': _absolute(request, article.source_file) if article.source_file.name.lower().endswith('.pdf') else '',
        'image_url': _absolute(request, article.image) or _absolute(request, issue.cover_image),
        'paragraphs': _paragraphs(article.content),
    })


@require_GET
def issue_page(request, pk):
    issue = get_object_or_404(Issue.objects.select_related('journal'), pk=pk, is_upcoming=False)
    return render(request, 'seo/issue.html', {
        'site_name': SITE_NAME,
        'canonical': f'{_site()}/archive/{issue.id}',
        'lang': 'uz-Latn',
        'issue': issue,
        'articles': issue.articles.order_by('page_start', 'created_at').prefetch_related('authors'),
        'image_url': _absolute(request, issue.cover_image),
    })


@require_GET
def author_page(request, slug):
    author = Author.objects.filter(slug=slug, articles__issue__isnull=False).distinct().first()
    if author is None:
        alias = AuthorAlias.objects.select_related('author').filter(slug=slug).first()
        if alias is None:
            raise Http404
        return HttpResponsePermanentRedirect(f'{_site()}/authors/{alias.author.slug}')
    return render(request, 'seo/author.html', {
        'site_name': SITE_NAME,
        'canonical': f'{_site()}/authors/{author.slug}',
        'lang': 'uz-Latn',
        'author': author,
        'articles': author.articles.filter(issue__isnull=False).select_related('issue').order_by('-issue__year', '-issue__number'),
        'image_url': _absolute(request, author.avatar),
    })
