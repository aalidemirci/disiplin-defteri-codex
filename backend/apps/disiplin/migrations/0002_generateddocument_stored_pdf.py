from django.db import migrations, models

import shared.crypto


class Migration(migrations.Migration):
    dependencies = [
        ("disiplin", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="generateddocument",
            name="stored_filename",
            field=models.CharField(
                blank=True,
                default="",
                max_length=255,
                verbose_name="saklanan PDF dosya adı",
            ),
        ),
        migrations.AddField(
            model_name="generateddocument",
            name="stored_pdf_b64",
            field=shared.crypto.EncryptedTextField(
                blank=True,
                default="",
                help_text="Base64 PDF içeriği; uygulama parolası etkinse diskte şifreli tutulur.",
                verbose_name="saklanan PDF kopyası",
            ),
        ),
        migrations.AddField(
            model_name="generateddocument",
            name="stored_pdf_size",
            field=models.PositiveIntegerField(
                default=0,
                editable=False,
                help_text="Ham PDF boyutu (bayt); liste ekranı içeriği yüklemeden kopya varlığını gösterir.",
                verbose_name="saklanan PDF boyutu",
            ),
        ),
    ]
