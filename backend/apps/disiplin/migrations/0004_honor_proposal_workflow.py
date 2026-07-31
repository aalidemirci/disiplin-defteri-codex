import django.db.models.deletion
from django.db import migrations, models


def populate_proposal_terms(apps, schema_editor):
    HonorCertificate = apps.get_model("disiplin", "HonorCertificate")
    HonorCertificateEvent = apps.get_model("disiplin", "HonorCertificateEvent")
    for proposal in HonorCertificate.objects.all().iterator():
        event = (
            HonorCertificateEvent.objects.filter(
                certificate_id=proposal.pk,
                event_type="PROPOSED",
                school_term_id__isnull=False,
            )
            .order_by("event_date", "pk")
            .first()
        )
        if event is not None:
            proposal.school_term_id = event.school_term_id
            proposal.save(update_fields=["school_term"])


class Migration(migrations.Migration):
    dependencies = [
        ("okul", "0004_schoolterm"),
        ("disiplin", "0003_honor_periods"),
    ]

    operations = [
        migrations.AddField(
            model_name="honorcertificate",
            name="school_term",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="honor_certificate_proposals",
                to="okul.schoolterm",
                verbose_name="teklif dönemi",
            ),
        ),
        migrations.AddField(
            model_name="honorcertificate",
            name="principal_decided_at",
            field=models.DateField(
                blank=True, null=True, verbose_name="okul müdürü karar tarihi"
            ),
        ),
        migrations.AddField(
            model_name="honorcertificate",
            name="principal_decision_reason",
            field=models.TextField(
                blank=True, default="", verbose_name="okul müdürü karar açıklaması"
            ),
        ),
        migrations.AlterField(
            model_name="honorcertificate",
            name="awarded_at",
            field=models.DateField(
                blank=True,
                null=True,
                verbose_name="ödül ve disiplin kurulu karar tarihi",
            ),
        ),
        migrations.AlterField(
            model_name="honorcertificate",
            name="status",
            field=models.CharField(
                choices=[
                    ("PROPOSED", "Teklif edildi"),
                    ("HONOR_BOARD_RECOMMENDED", "Onur kurulu uygun gördü"),
                    ("AWARDED", "Ödül ve disiplin kurulu kabul etti"),
                    ("PRINCIPAL_APPROVED", "Okul müdürü onayladı"),
                    ("PRINCIPAL_REJECTED", "Okul müdürü onaylamadı"),
                    ("REJECTED", "Uygun görülmedi"),
                ],
                db_index=True,
                default="PROPOSED",
                max_length=24,
                verbose_name="durum",
            ),
        ),
        migrations.AlterField(
            model_name="honorcertificateevent",
            name="event_type",
            field=models.CharField(
                choices=[
                    ("PROPOSED", "Teklif edildi"),
                    ("RECOMMENDED", "Onur kurulu uygun gördü"),
                    ("AWARDED", "Ödül ve disiplin kurulu kabul etti"),
                    ("PRINCIPAL_APPROVED", "Okul müdürü onayladı"),
                    ("PRINCIPAL_REJECTED", "Okul müdürü onaylamadı"),
                    ("REJECTED", "Uygun görülmedi"),
                ],
                max_length=20,
                verbose_name="işlem",
            ),
        ),
        migrations.RunPython(populate_proposal_terms, migrations.RunPython.noop),
        migrations.AddIndex(
            model_name="honorcertificate",
            index=models.Index(
                fields=["school_term", "status"],
                name="honor_cert_term_status_idx",
            ),
        ),
    ]
