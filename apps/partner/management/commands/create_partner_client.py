"""
Tashqi xizmat uchun API mijozi yaratadi va kirish ma'lumotlarini chiqaradi.

    python manage.py create_partner_client --name "Indekslash xizmati" --contact info@example.com

Mavjud mijozga yangi secret berish:

    python manage.py create_partner_client --name "Indekslash xizmati" --rotate
"""
from django.core.management.base import BaseCommand, CommandError

from apps.partner.models import PartnerClient, generate_client_secret


class Command(BaseCommand):
    help = "Hamkor (tashqi xizmat) uchun API mijozi yaratadi"

    def add_arguments(self, parser):
        parser.add_argument('--name',    required=True, help='Hamkor nomi')
        parser.add_argument('--contact', default='',    help='Aloqa (email/telefon)')
        parser.add_argument('--note',    default='',    help='Izoh')
        parser.add_argument(
            '--rotate', action='store_true',
            help="Shu nomdagi mijoz bor bo'lsa — unga yangi secret beradi",
        )

    def handle(self, *args, **opts):
        name = opts['name'].strip()
        if not name:
            raise CommandError('--name bo\'sh bo\'lmasligi kerak')

        existing = PartnerClient.objects.filter(name=name).first()

        if existing and not opts['rotate']:
            raise CommandError(
                f'"{name}" nomli mijoz allaqachon bor (client_id: {existing.client_id}). '
                'Yangi secret uchun --rotate qo\'shing.'
            )

        if existing:
            client = existing
            secret = client.rotate_secret()
            action = 'yangilandi'
        else:
            client = PartnerClient(
                name=name, contact=opts['contact'], note=opts['note'],
            )
            secret = generate_client_secret()
            client.set_secret(secret)
            client.save()
            action = 'yaratildi'

        self.stdout.write(self.style.SUCCESS(f'\nHamkor mijozi {action}: {client.name}\n'))
        self.stdout.write(f'  client_id:     {client.client_id}')
        self.stdout.write(f'  client_secret: {secret}')
        self.stdout.write(self.style.WARNING(
            '\n  client_secret bazada xesh holida saqlanadi — bu qiymat boshqa ko\'rsatilmaydi.\n'
        ))
