"""Disiplin rollü katılımcı + müdür uyarısı — md. 157/7, 166, 193.

OYS `discipline_participants.py`'den FK-ikameli uyarlama (tasarım §4.2):
`user` → `okul.Personnel`; `DisciplineWarning.issued_by` KALDIRILDI (tek
kullanıcı — uyaran daima müdürdür, antet/imza `SchoolConfig.principal_name`'den).
"""

from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db import models

from apps.disiplin.models.cases import DisciplineCase
from shared.models import BaseModel


class ParticipantRole(models.TextChoices):
    """Disiplin sürecinde kişinin rolü (md. 193 ifade/savunma formları)."""

    # "Suçlanan" kavramı yerine "Hakkında İşlem Yapılan" (OYS Talep 1i). Enum
    # DEĞERİ ("ACCUSED") DB/şablon uyumluluğu için korunur.
    ACCUSED = "ACCUSED", "Hakkında İşlem Yapılan"
    VICTIM = "VICTIM", "Mağdur"
    WITNESS = "WITNESS", "Tanık"


class ParticipantPersonType(models.TextChoices):
    """Katılımcının kim olduğu — referans alanını belirler."""

    STUDENT = "STUDENT", "Öğrenci"
    STAFF = "STAFF", "Personel"
    EXTERNAL = "EXTERNAL", "Dış kişi"


class DisciplineParticipant(BaseModel):
    """Bir disiplin dosyasının rollü katılımcısı (hakkında işlem yapılan/mağdur/tanık).

    `person_type`'a göre tam bir referans alanı dolar: STUDENT→`student`,
    STAFF→`user` (Personnel), EXTERNAL→`external_name` (+`external_title`).
    `name_snapshot` ekleme anındaki ad-soyad. ACCUSED-öğrenci katılımcılar
    `DisciplineCaseStudent` ile senkron tutulur (services.add_participant) —
    resmî karar o through tablosuna bağlıdır.
    """

    case = models.ForeignKey(
        DisciplineCase,
        on_delete=models.CASCADE,
        related_name="participants",
        verbose_name="dosya",
    )
    role = models.CharField("rol", max_length=10, choices=ParticipantRole.choices, db_index=True)
    person_type = models.CharField(
        "kişi tipi", max_length=10, choices=ParticipantPersonType.choices
    )
    student = models.ForeignKey(
        "okul.Student",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="discipline_participations",
        verbose_name="öğrenci",
    )
    user = models.ForeignKey(
        "okul.Personnel",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="discipline_participations",
        verbose_name="personel",
    )
    external_name = models.CharField("dış kişi adı", max_length=200, blank=True, default="")
    external_title = models.CharField(
        "dış kişi sıfatı",
        max_length=120,
        blank=True,
        default="",
        help_text="Örn. 'komşu', 'esnaf', 'okul dışı tanık'.",
    )
    name_snapshot = models.CharField(
        "ad (snapshot)",
        max_length=200,
        blank=True,
        default="",
        help_text="Ekleme anındaki ad-soyad; ifade/tutanak bütünlüğü için.",
    )
    notes = models.CharField("açıklama", max_length=255, blank=True, default="")

    class Meta:
        verbose_name = "disiplin katılımcısı"
        verbose_name_plural = "disiplin katılımcıları"
        ordering = ["role", "id"]
        constraints = [
            # Aynı öğrenci aynı rolde iki kez eklenemez (silinmemiş).
            models.UniqueConstraint(
                fields=["case", "role", "student"],
                condition=models.Q(deleted_at__isnull=True, student__isnull=False),
                name="uq_disc_participant_case_role_student",
            ),
            # Aynı personel aynı rolde iki kez eklenemez (silinmemiş).
            models.UniqueConstraint(
                fields=["case", "role", "user"],
                condition=models.Q(deleted_at__isnull=True, user__isnull=False),
                name="uq_disc_participant_case_role_user",
            ),
        ]
        indexes = [
            models.Index(fields=["case", "role"], name="disc_part_case_role_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.name_snapshot or self.pk} ({self.get_role_display()})"

    def clean(self) -> None:
        """person_type ↔ doldurulmuş referans tutarlılığını doğrular (tam biri dolu)."""
        errors: dict[str, str] = {}
        pt = self.person_type
        if pt == ParticipantPersonType.STUDENT:
            if self.student_id is None:
                errors["student"] = "Öğrenci katılımcı için öğrenci seçilmelidir."
            if self.user_id is not None:
                errors["user"] = "Öğrenci katılımcıda personel alanı boş olmalı."
            if (self.external_name or "").strip():
                errors["external_name"] = "Öğrenci katılımcıda dış kişi adı boş olmalı."
        elif pt == ParticipantPersonType.STAFF:
            if self.user_id is None:
                errors["user"] = "Personel katılımcı için personel seçilmelidir."
            if self.student_id is not None:
                errors["student"] = "Personel katılımcıda öğrenci alanı boş olmalı."
            if (self.external_name or "").strip():
                errors["external_name"] = "Personel katılımcıda dış kişi adı boş olmalı."
        elif pt == ParticipantPersonType.EXTERNAL:
            if not (self.external_name or "").strip():
                errors["external_name"] = "Dış kişi için ad zorunludur."
            if self.student_id is not None or self.user_id is not None:
                errors["person_type"] = "Dış kişide öğrenci/personel alanı boş olmalı."
        else:
            errors["person_type"] = "Geçersiz kişi tipi."

        if errors:
            raise ValidationError(errors)


class DisciplineWarning(BaseModel):
    """Müdür uyarısı — md. 157/7 (kusurlu olduğuna dikkat çekme). CEZA DEĞİLDİR.

    İlk kez kınamalık davranış + daha önce ceza almamış öğrenciye verilir; davranış
    puanı düşmez (md. 170 dışı). Tekrarı triajda kurula yönlendirir (md. 166).
    Dal A evrakı (Form-01/02) bu kayıttan üretilir. md. 157/7 imha aracının
    (tasarım §4.6) hedef kayıt türüdür.
    """

    case = models.ForeignKey(
        DisciplineCase,
        on_delete=models.CASCADE,
        related_name="warnings",
        verbose_name="dosya",
    )
    student = models.ForeignKey(
        "okul.Student",
        on_delete=models.PROTECT,
        related_name="discipline_warnings",
        verbose_name="öğrenci",
    )
    warning_date = models.DateField("uyarı tarihi")
    summary = models.TextField("uyarı gerekçesi / özet")

    class Meta:
        verbose_name = "müdür uyarısı"
        verbose_name_plural = "müdür uyarıları"
        ordering = ["-warning_date", "-created_at"]
        indexes = [
            models.Index(fields=["case"], name="disc_warning_case_idx"),
            models.Index(fields=["student"], name="disc_warning_student_idx"),
        ]

    def __str__(self) -> str:
        return f"Müdür uyarısı — öğrenci {self.student_id} @ {self.warning_date:%d.%m.%Y}"
