from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("disiplin", "0004_honor_proposal_workflow"),
    ]

    operations = [
        migrations.AddField(
            model_name="disciplinedecision",
            name="e_school_processed_on",
            field=models.DateField(
                blank=True,
                help_text=(
                    "Kesinleşen cezanın e-Okul'a işlendiğinin kullanıcı tarafından "
                    "onaylandığı tarih."
                ),
                null=True,
                verbose_name="e-Okul'a işlenme tarihi",
            ),
        ),
    ]
