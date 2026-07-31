from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("okul", "0003_classresponsibility"),
    ]

    operations = [
        migrations.CreateModel(
            name="SchoolTerm",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "created_at",
                    models.DateTimeField(
                        auto_now_add=True, db_index=True, verbose_name="oluşturulma"
                    ),
                ),
                (
                    "updated_at",
                    models.DateTimeField(auto_now=True, verbose_name="güncellenme"),
                ),
                (
                    "deleted_at",
                    models.DateTimeField(
                        blank=True, db_index=True, null=True, verbose_name="silinme"
                    ),
                ),
                (
                    "sequence",
                    models.PositiveSmallIntegerField(
                        choices=[(1, "1. dönem"), (2, "2. dönem")],
                        verbose_name="dönem",
                    ),
                ),
                ("start_date", models.DateField(verbose_name="başlangıç")),
                ("end_date", models.DateField(verbose_name="bitiş")),
                (
                    "school_year",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="terms",
                        to="okul.schoolyear",
                        verbose_name="ders yılı",
                    ),
                ),
            ],
            options={
                "verbose_name": "ders dönemi",
                "verbose_name_plural": "ders dönemleri",
                "ordering": ["school_year", "sequence"],
                "indexes": [
                    models.Index(
                        fields=["school_year", "start_date"],
                        name="schoolterm_year_start_idx",
                    )
                ],
                "constraints": [
                    models.UniqueConstraint(
                        condition=models.Q(deleted_at__isnull=True),
                        fields=("school_year", "sequence"),
                        name="uq_schoolterm_year_sequence_alive",
                    ),
                    models.CheckConstraint(
                        condition=models.Q(sequence__in=(1, 2)),
                        name="ck_schoolterm_sequence",
                    ),
                    models.CheckConstraint(
                        condition=models.Q(end_date__gte=models.F("start_date")),
                        name="ck_schoolterm_date_order",
                    ),
                ],
            },
        ),
    ]
