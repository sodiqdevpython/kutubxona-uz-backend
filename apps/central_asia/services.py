"""
Central Asia — parse natijasini DB'ga saqlash.
"""
from __future__ import annotations

from django.utils import timezone

from .models import CentralAsiaPost
from .scraper import PostData, ScrapeSummary, scrape_category


def upsert_post(data: PostData) -> tuple[str, CentralAsiaPost]:
    """
    Bitta PostData'ni DB'ga saqlaydi (yoki yangilaydi).
    Idempotent — `source_url` unique kaliti bo'yicha ishlaydi.
    Qaytadi: ('created' | 'updated', post).
    """
    post = CentralAsiaPost.objects.filter(source_url=data.source_url).first()

    is_new = post is None
    if post is None:
        post = CentralAsiaPost(source='scraped', source_url=data.source_url)

    # Sarlavha va matn — har safar manbadagi so'nggi versiyaga tenglashtiramiz
    post.title           = data.title[:500]
    post.author_line     = (data.author_line or '')[:500]
    post.source_slug     = (data.source_slug or '')[:500]
    post.source_category = (data.category or 'Central Asia')[:200]
    post.excerpt         = data.excerpt or post.excerpt
    if data.content_html:
        post.content = data.content_html
    if data.doi:
        post.doi = data.doi[:200]

    # Manba view — HAR SAFAR yangilanadi (bizning `views_local` alohida)
    post.views_scraped   = max(int(data.views or 0), 0)
    post.quote_number    = max(int(data.quote_number or 0), 0)
    post.sort_order      = int(data.sort_order or 0)
    post.last_scraped_at = timezone.now()

    post.save()
    return ('created' if is_new else 'updated', post)


def run_scrape(*, max_pages: int | None = None, fetch_detail: bool = True) -> ScrapeSummary:
    """Barcha central-asia bo'limini yangilash. Xatoliklar `summary.errors`'ga yig'iladi."""
    def _on_post(data: PostData):
        outcome, post = upsert_post(data)
        return outcome, str(post.pk)

    return scrape_category(
        max_pages    = max_pages,
        fetch_detail = fetch_detail,
        on_post      = _on_post,
    )
