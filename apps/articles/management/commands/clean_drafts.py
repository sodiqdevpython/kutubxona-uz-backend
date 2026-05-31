"""
24 soatdan eski tugatilmagan qoralamalarni (draft) o'chiradi.

Ishlatish:
    python manage.py clean_drafts

Cron / Task Scheduler orqali kuniga bir marta ishga tushiriladi.
"""
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.articles.models import ArticleSubmission

DRAFT_TTL = timedelta(hours=24)


class Command(BaseCommand):
    help = "24 soatdan eski tugatilmagan qoralamalarni o'chiradi"

    def add_arguments(self, parser):
        parser.add_argument(
            '--hours', type=int, default=24,
            help='Necha soatdan eski draftlar o\'chiriladi (default: 24)',
        )

    def handle(self, *args, **options):
        cutoff = timezone.now() - timedelta(hours=options['hours'])
        qs = ArticleSubmission.objects.filter(status='draft', created_at__lt=cutoff)
        count = qs.count()
        qs.delete()
        self.stdout.write(self.style.SUCCESS(
            f"{count} ta eski qoralama o'chirildi (>{options['hours']} soat)."
        ))
