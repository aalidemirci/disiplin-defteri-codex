"""Disiplin kurulu + üye + dosya toplantısı — md. 185-192.

OYS `discipline_committee.py`'den FK-ikameli uyarlama (tasarım §4.2):
`chair`/`member_user` → `okul.Personnel`; `member_parent` KALDIRILDI — veli
üyeler yalnız ad snapshot'ıyla tutulur (`member_name`; tutanak bütünlüğü yeter).
"""

from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db import models

from apps.disiplin.models.cases import DisciplineCase, DisciplineEvent
from shared.models import BaseModel


class CommitteeMemberType(models.TextChoices):
    """Kurul üyesinin tipi (md. 185/1)."""

    TEACHER = "TEACHER", "Öğretmen"
    STUDENT = "STUDENT", "Öğrenci"
    PARENT = "PARENT", "Veli"


class DisciplineCommittee(BaseModel):
    """Okul Öğrenci Ödül ve Disiplin Kurulu — ders yılı başına bir kurul (md. 185).

    `chair`: müdürün görevlendireceği müdür yardımcısı (kurul başkanı, md. 188).
    """

    school_year = models.ForeignKey(
        "okul.SchoolYear",
        on_delete=models.PROTECT,
        related_name="discipline_committees",
        verbose_name="ders yılı",
    )
    chair = models.ForeignKey(
        "okul.Personnel",
        on_delete=models.PROTECT,
        related_name="chaired_discipline_committees",
        verbose_name="kurul başkanı",
        help_text="Müdürün görevlendireceği müdür yardımcısı (md. 188).",
    )
    notes = models.TextField("açıklama", blank=True, default="")

    class Meta:
        verbose_name = "disiplin kurulu"
        verbose_name_plural = "disiplin kurulları"
        ordering = ["-created_at"]
        constraints = [
            # Ders yılı başına tek (silinmemiş) kurul.
            models.UniqueConstraint(
                fields=["school_year"],
                condition=models.Q(deleted_at__isnull=True),
                name="uq_disc_committee_year_alive",
            )
        ]
        indexes = [
            models.Index(fields=["school_year"], name="disc_comm_year_idx"),
        ]

    def __str__(self) -> str:
        return f"Disiplin Kurulu {self.school_year_id} (başkan {self.chair_id})"


class DisciplineCommitteeMember(BaseModel):
    """Kurul üyesi — asıl veya yedek (md. 185-186).

    Kişi referansı üye tipine göre: TEACHER→`member_user` (Personnel),
    STUDENT→`member_student`; PARENT üyede FK YOK — `member_name` snapshot
    zorunludur (tasarım §4.2: "member_parent KALKAR, ad snapshot yeter").
    `is_substitute` asıl/yedek ayrımı; `order` oy/yedek sırası (md. 186).
    """

    committee = models.ForeignKey(
        DisciplineCommittee,
        on_delete=models.CASCADE,
        related_name="members",
        verbose_name="kurul",
    )
    member_type = models.CharField("üye tipi", max_length=10, choices=CommitteeMemberType.choices)
    is_substitute = models.BooleanField("yedek üye", default=False, db_index=True)
    order = models.PositiveSmallIntegerField(
        "sıra", default=0, help_text="Oy/yedek sırası (md. 186 'sıraya göre')."
    )
    title = models.CharField(
        "görev/ünvan",
        max_length=120,
        blank=True,
        default="",
        help_text="Örn. 'Onur kurulu ikinci başkanı', 'Okul-aile birliği üyesi'.",
    )
    member_user = models.ForeignKey(
        "okul.Personnel",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="discipline_committee_memberships",
        verbose_name="öğretmen üye",
    )
    member_student = models.ForeignKey(
        "okul.Student",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="discipline_committee_memberships",
        verbose_name="öğrenci üye",
    )
    member_name = models.CharField(
        "üye adı (snapshot)",
        max_length=200,
        blank=True,
        default="",
        help_text="Ekleme anındaki ad-soyad; tutanak bütünlüğü için (kişi sonradan değişebilir).",
    )

    class Meta:
        verbose_name = "disiplin kurulu üyesi"
        verbose_name_plural = "disiplin kurulu üyeleri"
        ordering = ["is_substitute", "order", "id"]
        indexes = [
            models.Index(fields=["committee", "is_substitute"], name="disc_member_comm_sub_idx"),
        ]

    def __str__(self) -> str:
        kind = "yedek" if self.is_substitute else "asıl"
        return f"{self.member_name or self.pk} ({self.get_member_type_display()}, {kind})"

    def clean(self) -> None:
        """Üye tipi ↔ referans tutarlılığı: TEACHER/STUDENT'ta ilgili FK, PARENT'ta ad."""
        provided = {
            "member_user": self.member_user_id,
            "member_student": self.member_student_id,
        }
        if self.member_type == CommitteeMemberType.PARENT:
            if not (self.member_name or "").strip():
                raise ValidationError(
                    {"member_name": "Veli üye için ad-soyad (snapshot) zorunludur."}
                )
            for field, val in provided.items():
                if val is not None:
                    raise ValidationError({field: "Veli üyede bu alan boş olmalı (ad yeter)."})
            return

        expected: dict[str, str] = {
            CommitteeMemberType.TEACHER: "member_user",
            CommitteeMemberType.STUDENT: "member_student",
        }
        wanted = expected.get(self.member_type)
        if wanted is None:
            raise ValidationError({"member_type": "Geçersiz üye tipi."})
        if provided[wanted] is None:
            raise ValidationError(
                {wanted: f"{self.get_member_type_display()} üye için bu alan zorunlu."}
            )
        for field, val in provided.items():
            if field != wanted and val is not None:
                raise ValidationError(
                    {field: f"Bu üye tipinde bu alan boş olmalı (yalnız {wanted})."}
                )


class DisciplineMeeting(BaseModel):
    """Bir disiplin dosyası için kurul toplantısı — katılanlar kurul üyelerinden seçilir.

    `attendees`: toplantıya katılan kurul üyeleri (md. 191 salt çoğunluk; şikâyetçi
    üye katılamaz → yerine yedek). Tutanak/PDF veriyi buradan çeker.
    """

    case = models.ForeignKey(
        DisciplineCase,
        on_delete=models.CASCADE,
        related_name="meetings",
        verbose_name="dosya",
    )
    event = models.ForeignKey(
        DisciplineEvent,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="meetings",
        verbose_name="ilgili kurul kararı olayı",
    )
    meeting_date = models.DateField("toplantı tarihi")
    attendees = models.ManyToManyField(
        DisciplineCommitteeMember,
        related_name="meetings",
        verbose_name="katılan üyeler",
        blank=True,
    )
    notes = models.TextField("toplantı notu", blank=True, default="")

    class Meta:
        verbose_name = "disiplin kurulu toplantısı"
        verbose_name_plural = "disiplin kurulu toplantıları"
        ordering = ["-meeting_date", "-created_at"]
        indexes = [
            models.Index(fields=["case"], name="disc_meeting_case_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.case_id} kurul toplantısı @ {self.meeting_date:%d.%m.%Y}"
