"""Kurul süresi uzatma + tedbir — md. 175, 192/3.

OYS `discipline_precautions.py`'den uyarlama (tasarım §4.2): alanlar AYNEN,
yalnız `student` → `okul.Student`. Snapshot süre alanları (end_date,
process_start_deadline) iş günü mantığıyla serviste hesaplanıp yazılır.
"""

from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db import models

from apps.disiplin.models.cases import DisciplineCase, DisciplineEvent
from shared.models import BaseModel


class DisciplineDeadlineExtension(BaseModel):
    """Kurul karar süresi uzatması — Form-12 (ara karar) + Form-13 (dilekçe), md. 192/3.

    md. 192/3: 10 iş günlük kurul karar süresi yetmezse, alınacak ara karar ve okul
    müdürünün onayıyla ANCAK BİR KEZ uzatılabilir → dosya başına tek (silinmemiş)
    uzatma (alive-unique). `original_deadline`/`new_deadline` uzatma anında snapshot.
    """

    case = models.ForeignKey(
        DisciplineCase,
        on_delete=models.CASCADE,
        related_name="deadline_extensions",
        verbose_name="dosya",
    )
    requested_days = models.PositiveSmallIntegerField(
        "uzatma süresi (iş günü)",
        help_text="Ara kararda talep edilen ek süre (Form-12/13).",
    )
    reason = models.TextField(
        "uzatma gerekçesi",
        help_text="md. 192/3 ara karar gerekçesi (ifade/delil gecikmesi vb.).",
    )
    decided_on = models.DateField(
        "ara karar tarihi", help_text="Kurulun süre uzatma ara kararı tarihi (Form-12)."
    )
    approved_by_principal = models.BooleanField(
        "müdür onayı",
        default=False,
        help_text="md. 192/3: uzatma okul müdürünün onayıyla yürürlüğe girer (Form-13).",
    )
    approved_on = models.DateField("müdür onay tarihi", null=True, blank=True)
    original_deadline = models.DateField(
        "uzatma öncesi son gün",
        help_text="Uzatmadan önceki kurul karar son günü (kurula geliş + 10 iş günü).",
    )
    new_deadline = models.DateField(
        "uzatma sonrası son gün",
        help_text="Uzatma sonrası kurul karar son günü (snapshot).",
    )
    notes = models.TextField("açıklama", blank=True, default="")

    class Meta:
        verbose_name = "disiplin kurulu süre uzatması"
        verbose_name_plural = "disiplin kurulu süre uzatmaları"
        ordering = ["-decided_on", "-created_at"]
        constraints = [
            # md. 192/3: süre ancak BİR KEZ uzatılabilir → dosya başına tek canlı uzatma.
            models.UniqueConstraint(
                fields=["case"],
                condition=models.Q(deleted_at__isnull=True),
                name="uq_disc_deadline_ext_case_alive",
            )
        ]
        indexes = [
            models.Index(fields=["case"], name="disc_ext_case_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.case_id} süre uzatma (+{self.requested_days} iş günü)"


class PrecautionStatus(models.TextChoices):
    """Tedbir (geçici uzaklaştırma) durumu — md. 175."""

    ACTIVE = "ACTIVE", "Yürürlükte"
    LIFTED = "LIFTED", "Kaldırıldı"
    EXPIRED = "EXPIRED", "Kendiliğinden kalktı"


class DisciplinePrecaution(BaseModel):
    """Tedbir kararı — acele geçici uzaklaştırma (md. 175).

    Müdür, kurula sevkten önce/sonra acele tedbir olarak öğrenciyi ≤10 iş günü
    geçici uzaklaştırabilir (md. 175/1, milli eğitim müdürü bilgilendirilir). Tedbiri
    izleyen 3 iş günü içinde disiplin işlemine başlanır (md. 175/2). Uzaklaştırılan
    süre devamsızlıktan SAYILMAZ (md. 175/1). `end_date` ve `process_start_deadline`
    tedbir kaydında snapshot yazılır (iş günü mantığı).
    """

    case = models.ForeignKey(
        DisciplineCase,
        on_delete=models.CASCADE,
        related_name="precautions",
        verbose_name="dosya",
    )
    student = models.ForeignKey(
        "okul.Student",
        on_delete=models.PROTECT,
        related_name="discipline_precautions",
        verbose_name="öğrenci",
    )
    event = models.ForeignKey(
        DisciplineEvent,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="precautions",
        verbose_name="ilgili olay",
    )
    start_date = models.DateField("tedbir başlangıç tarihi")
    requested_days = models.PositiveSmallIntegerField(
        "tedbir süresi (iş günü)",
        help_text="md. 175/1: en fazla 10 iş günü.",
    )
    end_date = models.DateField(
        "tedbir bitiş günü",
        help_text="Son uzaklaştırma günü (başlangıç + süre, iş günü; snapshot).",
    )
    process_start_deadline = models.DateField(
        "işleme başlama son günü",
        help_text="md. 175/2: tedbiri izleyen en geç 3 iş günü.",
    )
    mne_notified = models.BooleanField(
        "milli eğitim müdürlüğü bilgilendirildi",
        default=False,
        help_text="md. 175/1: tedbir milli eğitim müdürü bilgilendirilerek alınır.",
    )
    extension_count = models.PositiveSmallIntegerField(
        "uzatma sayısı",
        default=0,
        help_text="md. 175/2: milli eğitim müdürü onayıyla en fazla iki kez uzatılabilir.",
    )
    status = models.CharField(
        "durum",
        max_length=10,
        choices=PrecautionStatus.choices,
        default=PrecautionStatus.ACTIVE,
        db_index=True,
    )
    lifted_on = models.DateField(
        "kaldırma/sonlanma tarihi",
        null=True,
        blank=True,
        help_text="Karara bağlandığında veya süre dolduğunda tedbirin sonlandığı tarih.",
    )
    reason = models.TextField("tedbir gerekçesi", blank=True, default="")
    notes = models.TextField("açıklama", blank=True, default="")

    class Meta:
        verbose_name = "disiplin tedbiri"
        verbose_name_plural = "disiplin tedbirleri"
        ordering = ["-start_date", "-created_at"]
        constraints = [
            # Bir dosyada öğrenciye aynı anda tek YÜRÜRLÜKTEKİ tedbir (md. 175).
            models.UniqueConstraint(
                fields=["case", "student"],
                condition=models.Q(deleted_at__isnull=True, status="ACTIVE"),
                name="uq_disc_precaution_active_per_student",
            )
        ]
        indexes = [
            models.Index(fields=["case"], name="disc_prec_case_idx"),
            models.Index(fields=["student"], name="disc_prec_student_idx"),
            models.Index(fields=["status"], name="disc_prec_status_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.case_id}/{self.student_id} tedbir ({self.get_status_display()})"

    def clean(self) -> None:
        """Tedbir süresi 1-10 iş günü olmalıdır (md. 175/1)."""
        from apps.disiplin import discipline_periods

        if not (1 <= self.requested_days <= discipline_periods.PRECAUTION_MAX_WORKING_DAYS):
            raise ValidationError(
                {
                    "requested_days": (
                        "Tedbir süresi 1-"
                        f"{discipline_periods.PRECAUTION_MAX_WORKING_DAYS} iş günü olmalıdır "
                        "(md. 175/1)."
                    )
                }
            )
