from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('journals', '0005_issue_editor_name_issue_editorial_note_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='journal',
            name='title',
            field=models.CharField(default='Kutubxona', max_length=200, verbose_name='Jurnal nomi'),
        ),
    ]
