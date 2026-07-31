from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("okul", "0002_encrypt_sensitive_fields"),
    ]

    operations = [
        migrations.CreateModel(
            name="ClassResponsibility",
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
                ("class_level", models.PositiveSmallIntegerField(verbose_name="sınıf")),
                ("class_section", models.CharField(max_length=8, verbose_name="şube")),
                (
                    "assistant_principal",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="assistant_principal_responsibilities",
                        to="okul.personnel",
                        verbose_name="ilgili müdür yardımcısı",
                    ),
                ),
                (
                    "class_teacher",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="class_teacher_responsibilities",
                        to="okul.personnel",
                        verbose_name="sınıf öğretmeni",
                    ),
                ),
                (
                    "guidance_teacher",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="guidance_teacher_responsibilities",
                        to="okul.personnel",
                        verbose_name="ilgili rehber öğretmen",
                    ),
                ),
                (
                    "school_year",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="class_responsibilities",
                        to="okul.schoolyear",
                        verbose_name="ders yılı",
                    ),
                ),
            ],
            options={
                "verbose_name": "sınıf sorumluluğu",
                "verbose_name_plural": "sınıf sorumlulukları",
                "ordering": ["school_year", "class_level", "class_section"],
            },
        ),
        migrations.AddConstraint(
            model_name="classresponsibility",
            constraint=models.UniqueConstraint(
                condition=models.Q(("deleted_at__isnull", True)),
                fields=("school_year", "class_level", "class_section"),
                name="uq_class_responsibility_alive",
            ),
        ),
        migrations.AddIndex(
            model_name="classresponsibility",
            index=models.Index(
                fields=["school_year", "class_level", "class_section"],
                name="okul_class_resp_lookup_idx",
            ),
        ),
    ]
