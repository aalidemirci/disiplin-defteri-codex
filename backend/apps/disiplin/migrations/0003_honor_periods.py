from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("okul", "0004_schoolterm"),
        ("disiplin", "0002_generateddocument_stored_pdf"),
    ]

    operations = [
        migrations.CreateModel(
            name="HonorGeneralAssemblyMember",
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
                ("member_name", models.CharField(max_length=200, verbose_name="üye adı (snapshot)")),
                ("effective_from", models.DateField(verbose_name="görev başlangıcı")),
                ("effective_until", models.DateField(blank=True, null=True, verbose_name="görev bitişi")),
                (
                    "end_reason",
                    models.CharField(blank=True, default="", max_length=255, verbose_name="görev bitiş nedeni"),
                ),
                (
                    "member_student",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="honor_general_assembly_memberships",
                        to="okul.student",
                        verbose_name="öğrenci temsilci",
                    ),
                ),
                (
                    "replaced_member",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="replacements",
                        to="disiplin.honorgeneralassemblymember",
                        verbose_name="yerine seçildiği üye",
                    ),
                ),
                (
                    "school_year",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="honor_general_assembly_members",
                        to="okul.schoolyear",
                        verbose_name="ders yılı",
                    ),
                ),
            ],
            options={
                "verbose_name": "onur genel kurulu temsilcisi",
                "verbose_name_plural": "onur genel kurulu temsilcileri",
                "ordering": ["class_level", "class_section", "effective_from"],
                "indexes": [
                    models.Index(
                        fields=["school_year", "class_level", "class_section"],
                        name="honor_assembly_branch_idx",
                    )
                ],
                "constraints": [
                    models.UniqueConstraint(
                        condition=models.Q(effective_until__isnull=True, deleted_at__isnull=True),
                        fields=("school_year", "class_level", "class_section"),
                        name="uq_honor_assembly_active_branch",
                    )
                ],
            },
        ),
        migrations.AddField(
            model_name="honorboard",
            name="substitute_chair",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="substitute_chaired_honor_boards",
                to="okul.personnel",
                verbose_name="onur kurulu başkan yedeği",
            ),
        ),
        migrations.AddField(
            model_name="honorboardmember",
            name="assembly_member",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="board_memberships",
                to="disiplin.honorgeneralassemblymember",
                verbose_name="genel kurul seçim kaynağı",
            ),
        ),
        migrations.AddField(
            model_name="honorboardmember",
            name="effective_from",
            field=models.DateField(blank=True, null=True, verbose_name="görev başlangıcı"),
        ),
        migrations.AddField(
            model_name="honorboardmember",
            name="effective_until",
            field=models.DateField(blank=True, null=True, verbose_name="görev bitişi"),
        ),
        migrations.AddField(
            model_name="honorboardmember",
            name="end_reason",
            field=models.CharField(
                blank=True,
                default="",
                max_length=255,
                verbose_name="görev bitiş nedeni",
            ),
        ),
        migrations.AddField(
            model_name="councilmeeting",
            name="school_term",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="council_meetings",
                to="okul.schoolterm",
                verbose_name="dönem",
            ),
        ),
        migrations.AddField(
            model_name="councilmeeting",
            name="honor_meeting_kind",
            field=models.CharField(
                choices=[("BOARD", "Onur Kurulu"), ("GENERAL_ASSEMBLY", "Onur Genel Kurulu")],
                default="BOARD",
                max_length=20,
                verbose_name="onur toplantısı türü",
            ),
        ),
        migrations.CreateModel(
            name="HonorCertificateEvent",
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
                    "event_type",
                    models.CharField(
                        choices=[
                            ("PROPOSED", "Teklif edildi"),
                            ("RECOMMENDED", "Onur kurulu uygun gördü"),
                            ("AWARDED", "Belge verildi"),
                            ("REJECTED", "Uygun görülmedi"),
                        ],
                        max_length=16,
                        verbose_name="işlem",
                    ),
                ),
                ("event_date", models.DateField(verbose_name="işlem tarihi")),
                ("explanation", models.TextField(blank=True, default="", verbose_name="açıklama")),
                (
                    "certificate",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="events",
                        to="disiplin.honorcertificate",
                        verbose_name="onur belgesi",
                    ),
                ),
                (
                    "meeting",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="honor_certificate_events",
                        to="disiplin.councilmeeting",
                        verbose_name="dayanak toplantı",
                    ),
                ),
                (
                    "school_term",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="honor_certificate_events",
                        to="okul.schoolterm",
                        verbose_name="dönem",
                    ),
                ),
            ],
            options={
                "verbose_name": "onur belgesi işlem olayı",
                "verbose_name_plural": "onur belgesi işlem olayları",
                "ordering": ["event_date", "created_at"],
                "indexes": [
                    models.Index(
                        fields=["certificate", "event_type"],
                        name="honor_event_cert_type_idx",
                    )
                ],
            },
        ),
    ]
