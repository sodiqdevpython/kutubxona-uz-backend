from django.core.management.base import BaseCommand

from apps.central_asia.services import run_scrape


class Command(BaseCommand):
    help = "einfolib.uz/category/central-asia sahifasini parse qilib DB'ga saqlaydi."

    def add_arguments(self, parser):
        parser.add_argument(
            '--pages', type=int, default=None,
            help='Faqat birinchi N sahifani olish (test uchun).',
        )
        parser.add_argument(
            '--no-detail', action='store_true',
            help="Detail sahifalarni olmaslik — faqat kartochkalar (test/tez tekshirish).",
        )

    def handle(self, *args, **opts):
        pages   = opts.get('pages')
        detail  = not opts.get('no_detail')

        self.stdout.write(self.style.NOTICE('Central Asia parse boshlandi…'))
        summary = run_scrape(max_pages=pages, fetch_detail=detail)

        self.stdout.write(self.style.SUCCESS(
            f'Sahifalar: {summary.pages_visited}, '
            f'topilgan: {summary.cards_found}, '
            f'yangi: {summary.created}, '
            f'yangilangan: {summary.updated}'
        ))
        for err in summary.errors:
            self.stdout.write(self.style.WARNING(f'  ! {err}'))
