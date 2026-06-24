from django.db import migrations


def set_source(apps, schema_editor):
    """Mavjud mualliflar: Telegram chat_id bo'lsa 'telegram', aks holda 'manual'."""
    Author = apps.get_model('authors', 'Author')
    Author.objects.filter(telegram_chat_id__isnull=False).update(source='telegram')
    Author.objects.filter(telegram_chat_id__isnull=True).update(source='manual')


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('authors', '0005_author_source'),
    ]

    operations = [
        migrations.RunPython(set_source, noop),
    ]
