from django.db import migrations, models

from utils.text import detect_language


def fill_language(apps, schema_editor):
    Article = apps.get_model('articles', 'Article')
    for article in Article.objects.only('pk', 'title').iterator():
        Article.objects.filter(pk=article.pk).update(language=detect_language(article.title))


class Migration(migrations.Migration):

    dependencies = [
        ('articles', '0011_articlesubmission_preview_html'),
    ]

    operations = [
        migrations.AddField(
            model_name='article',
            name='language',
            field=models.CharField(
                choices=[('uz', "O'zbek (lotin)"), ('uz-cyrl', 'Ўзбек (кирилл)'), ('ru', 'Русский'), ('en', 'English')],
                db_index=True, default='uz', editable=False, max_length=10, verbose_name='Til',
            ),
        ),
        migrations.RunPython(fill_language, migrations.RunPython.noop),
    ]
