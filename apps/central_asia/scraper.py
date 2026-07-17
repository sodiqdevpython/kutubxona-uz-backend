"""
einfolib.uz / Central Asia — scraper.

Sayt tuzilishi (2026-yil):
  Ro'yxat: https://einfolib.uz/category/central-asia?page=N&per-page=15
  Detail:  https://einfolib.uz/post/<slug>

Har bir card ichida sarlavha, ko'rish soni, quote soni bor.
Detail'da esa `.post-content` — asosiy HTML matn, `.doi` va meta ma'lumot.

Bu modul hech qanday Django ORM'ga bog'lanmaydi — faqat toza dict'lar qaytaradi.
Saqlash mantiqi `services.py` da.
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from urllib.parse import urljoin, urlparse, parse_qs

import requests
from bs4 import BeautifulSoup


BASE_URL          = 'https://einfolib.uz'
CATEGORY_URL      = f'{BASE_URL}/category/central-asia'
USER_AGENT        = (
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
    'AppleWebKit/537.36 (KHTML, like Gecko) '
    'Chrome/124.0 Safari/537.36 kutubxona.uz-bot/1.0'
)
REQUEST_TIMEOUT   = 20
BETWEEN_REQUESTS  = 0.4   # sekund — juda tez urmaslik uchun


# ── Data types ────────────────────────────────────────────────────────────────

@dataclass
class CardData:
    source_url:   str
    source_slug:  str
    title:        str
    author_line:  str = ''
    excerpt:      str = ''
    views:        int = 0
    quote_number: int = 0
    category:     str = 'Central Asia'
    sort_order:   int = 0   # ro'yxatdagi global pozitsiya (0 — 1-sahifadagi birinchi)


@dataclass
class PostData(CardData):
    content_html: str = ''
    doi:          str = ''


@dataclass
class ScrapeSummary:
    pages_visited: int = 0
    cards_found:   int = 0
    created:       int = 0
    updated:       int = 0
    errors:        list[str] = field(default_factory=list)


# ── HTTP ──────────────────────────────────────────────────────────────────────

def _session() -> requests.Session:
    s = requests.Session()
    s.headers.update({'User-Agent': USER_AGENT, 'Accept-Language': 'uz,ru;q=0.8,en;q=0.7'})
    return s


def _fetch(session: requests.Session, url: str) -> BeautifulSoup:
    res = session.get(url, timeout=REQUEST_TIMEOUT)
    res.raise_for_status()
    # Encoding — einfolib UTF-8, lekin ba'zan Content-Type'da ko'rsatilmaydi
    res.encoding = res.apparent_encoding or 'utf-8'
    return BeautifulSoup(res.text, 'html.parser')


# ── Helpers ───────────────────────────────────────────────────────────────────

_INT_RE = re.compile(r'\d+')

def _to_int(txt: str | None) -> int:
    if not txt:
        return 0
    m = _INT_RE.search(txt.replace(',', '').replace('\xa0', ' '))
    return int(m.group(0)) if m else 0


def _abs_url(href: str) -> str:
    return urljoin(BASE_URL + '/', href.lstrip('/'))


def _slug_from_post_url(url: str) -> str:
    path = urlparse(url).path
    # /post/<slug>
    parts = [p for p in path.split('/') if p]
    if len(parts) >= 2 and parts[0] == 'post':
        return parts[1]
    return ''


# ── List page ────────────────────────────────────────────────────────────────

def _parse_cards(soup: BeautifulSoup) -> list[CardData]:
    """Bitta sahifa HTML'idan barcha kartochkalarni ajratib olamiz."""
    cards: list[CardData] = []
    for row in soup.select('div.item_category'):
        # 1) Title + URL — h4.page-title > a
        a = row.select_one('h4.page-title a[href^="/post/"]')
        if not a:
            continue
        href = a.get('href') or ''
        title = a.get_text(strip=True)
        if not href or not title:
            continue

        source_url  = _abs_url(href)
        source_slug = _slug_from_post_url(source_url)

        # 2) Author line (birinchi <p> — kartochka ichida)
        author_line = ''
        content_box = row.select_one('.right_category_content') or row
        first_p = content_box.find('p')
        if first_p:
            author_line = first_p.get_text(' ', strip=True)

        # 3) Meta — views, quote, category
        meta = content_box.select_one('.entry-meta')
        views = quote_num = 0
        category = 'Central Asia'
        if meta:
            # views: <i class="fa fa-eye"></i> 587
            eye = meta.select_one('i.fa-eye')
            if eye and eye.parent:
                views = _to_int(eye.parent.get_text(' ', strip=True))
            # quote: #copy-counter
            cc = meta.select_one('#copy-counter')
            if cc:
                quote_num = _to_int(cc.get_text(strip=True))
            # category link
            cat_a = meta.select_one('a[href^="/category/"]')
            if cat_a:
                category = cat_a.get_text(strip=True) or category

        cards.append(CardData(
            source_url  = source_url,
            source_slug = source_slug,
            title       = title,
            author_line = author_line,
            excerpt     = author_line,   # kartochkadagi qisqa matn
            views       = views,
            quote_number= quote_num,
            category    = category,
        ))
    return cards


def _max_page_number(soup: BeautifulSoup) -> int:
    """
    Pagination'dagi eng katta `page=` raqamini qaytaradi.
    einfolib.uz — bir sahifada 4 tagacha raqam ko'rsatadi, shu sabab
    bu faqat quyi chegara — asosiy loop hech bo'lmasa shuncha sahifani ko'radi,
    keyingi sahifalarni esa `next`/kart topilmagan holat orqali aniqlaydi.
    """
    pages = {1}
    for a in soup.select('ul.pagination a[href*="page="]'):
        href = a.get('href') or ''
        if '/category/central-asia' not in href:
            continue
        q = parse_qs(urlparse(href).query)
        try:
            pages.add(int(q.get('page', ['1'])[0]))
        except ValueError:
            continue
    return max(pages)


def _page_url(page: int) -> str:
    return f'{CATEGORY_URL}?page={page}&per-page=15'


# ── Detail page ──────────────────────────────────────────────────────────────

def _parse_detail(soup: BeautifulSoup) -> tuple[str, str, str, int, int]:
    """
    Detail sahifadan (content_html, doi, author_line, views, quote_number) qaytaradi.
    """
    # Content
    body = soup.select_one('div.post-content')
    content_html = ''
    if body:
        # Boshqa saytdagi tashqi iframe/script'lardan tozalash
        for tag in body.select('script, iframe, ins, .adsbygoogle'):
            tag.decompose()
        content_html = body.decode_contents().strip()

    # DOI
    doi = ''
    doi_box = soup.select_one('div.doi')
    if doi_box:
        # ikkinchi element — DOI kodi
        text = doi_box.get_text(' ', strip=True)
        m = re.search(r'10\.\S+', text)
        if m:
            doi = m.group(0)

    # Author line
    author_line = ''
    ab = soup.select_one('.row .col-md-12 div.author')
    if ab:
        author_line = ab.get_text(' ', strip=True)

    # Meta (post-title bloki)
    views = quote_num = 0
    meta = soup.select_one('.row.post-title .entry-meta')
    if meta:
        eye = meta.select_one('i.fa-eye')
        if eye and eye.parent:
            views = _to_int(eye.parent.get_text(' ', strip=True))
        cc = meta.select_one('#copy-counter')
        if cc:
            quote_num = _to_int(cc.get_text(strip=True))

    return content_html, doi, author_line, views, quote_num


# ── Public API ───────────────────────────────────────────────────────────────

MAX_PAGES_SAFETY = 500  # heuristik yuqori chegara


def scrape_category(
    *,
    max_pages: int | None = None,
    fetch_detail: bool = True,
    on_post = None,   # callable(PostData) -> ('created' | 'updated' | 'skipped', str)
    session: requests.Session | None = None,
) -> ScrapeSummary:
    """
    Central Asia bo'limining barcha sahifalarini aylanib chiqadi.
    Har bir post uchun `on_post(PostData)` chaqiradi (agar berilgan bo'lsa).

    Strategiya: `?page=1, page=2, …` — sahifa bo'sh bo'lsa yoki hech qanday YANGI
    URL topilmasa, to'xtaymiz. Bu einfolib.uz'da paginationda faqat 4 ta yaqin sahifa
    ko'rinishi bilan bog'liq muammoni hal qiladi (barcha sahifalar avtomatik topiladi).
    """
    summary = ScrapeSummary()
    session = session or _session()

    seen_urls: set[str] = set()
    global_order = 0
    stop_at_page: int | None = max_pages
    page_num = 0

    while True:
        page_num += 1
        if stop_at_page and page_num > stop_at_page:
            break
        if page_num > MAX_PAGES_SAFETY:
            summary.errors.append(f'Xavfsizlik chegarasi: {MAX_PAGES_SAFETY} sahifa oshib ketdi.')
            break

        url = _page_url(page_num)
        try:
            soup = _fetch(session, url)
        except requests.RequestException as e:
            summary.errors.append(f'Sahifa {url}: {e}')
            break

        summary.pages_visited += 1
        cards = _parse_cards(soup)

        # 1-sahifadan pagination'dagi max page raqamini ham eslab qolamiz —
        # cheklovsiz oldingi implementatsiyaga fallback sifatida.
        if page_num == 1 and stop_at_page is None:
            detected_max = _max_page_number(soup)
            # Faqat past chegara — real to'xtash `no new urls` bo'yicha bo'ladi.
            # (Ba'zi pager'lar so'nggi sahifani ko'rsatmaydi.)
            if detected_max > 1:
                stop_at_page = None  # cheklovsiz

        if not cards:
            # bo'sh sahifa — tugagan
            break

        new_this_page = 0
        for card in cards:
            if card.source_url in seen_urls:
                continue
            seen_urls.add(card.source_url)
            new_this_page += 1
            summary.cards_found += 1

            card.sort_order = global_order
            global_order += 1

            post = PostData(**card.__dict__)
            if fetch_detail and card.source_url:
                try:
                    time.sleep(BETWEEN_REQUESTS)
                    d_soup = _fetch(session, card.source_url)
                    content_html, doi, author_line, views, quote_num = _parse_detail(d_soup)
                    post.content_html = content_html
                    post.doi          = doi
                    if author_line:
                        post.author_line = author_line
                    if views:
                        post.views = views
                    if quote_num:
                        post.quote_number = quote_num
                except requests.RequestException as e:
                    summary.errors.append(f'Detail {card.source_url}: {e}')

            if on_post is not None:
                try:
                    outcome, _ = on_post(post)
                except Exception as e:  # pragma: no cover
                    summary.errors.append(f'Saqlashda xato {card.source_url}: {e}')
                    continue
                if outcome == 'created':
                    summary.created += 1
                elif outcome == 'updated':
                    summary.updated += 1

        # Sahifada bitta ham yangi URL bo'lmasa — pager keyingi sahifada takrorlayapti, to'xtaymiz
        if new_this_page == 0:
            break

        time.sleep(BETWEEN_REQUESTS)

    return summary
