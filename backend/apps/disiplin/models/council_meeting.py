"""Kurul toplantı tutanağı / karar defteri — md. 183-191, 206.

OYS `council_meeting.py`'den FK-ikameli uyarlama (tasarım §4.2):
`member_user` → `okul.Personnel`; `member_parent` KALDIRILDI (katılımcı zaten
zorunlu ad snapshot'ıyla tutulur — veli katılımcı yalnız adla kaydedilir).
"""

from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db import models

from apps.disiplin.models.cases import DisciplineCase
from apps.disiplin.models.committee import DisciplineCommittee
from apps.disiplin.models.honors import HonorBoard
from shared.models import BaseModel


class CouncilType(models.TextChoices):
    """Tutanağı tutulan kurul türü."""

    DISCIPLINE = "DISCIPLINE", "Ödül ve Disiplin Kurulu (md. 185)"
    HONOR = "HONOR", "Onur Kurulu (md. 180)"


class HonorMeetingKind(models.TextChoices):
    BOARD = "BOARD", "Onur Kurulu"
    GENERAL_ASSEMBLY = "GENERAL_ASSEMBLY", "Onur Genel Kurulu"


class CouncilDecisionBasis(models.TextChoices):
    """Kararın alınış esası (md. 191 oy çoğunluğu; md. 206 oy birliği/çoğunluğu)."""

    UNANIMITY = "UNANIMITY", "Oy birliği"
    MAJORITY = "MAJORITY", "Oy çoğunluğu"


class CouncilAttendeeRole(models.TextChoices):
    """Katılımcının oy hakkı (md. 191 üyeler oy kullanır; md. 185/6 davetliler kullanamaz)."""

    VOTING_MEMBER = "VOTING_MEMBER", "Oy hakkı olan üye"
    NON_VOTING_INVITEE = "NON_VOTING_INVITEE", "Oy hakkı olmayan davetli (md. 185/6)"


class CouncilMinutesType(models.TextChoices):
    """Tutanak türü — disiplin kurulunda dosya görüşmesi ayrı şablonla derlenir.

    CASE_REVIEW yalnız DISCIPLINE kurulunda; tutanak bir disiplin dosyasına
    bağlanır ve öğrenci-bazlı resmî kararlar PDF'e render anında otomatik
    derlenir (çift veri girişi yok). Onur kurulu tutanakları her zaman GENERAL.
    """

    CASE_REVIEW = "CASE_REVIEW", "Disiplin dosyası görüşme"
    GENERAL = "GENERAL", "Diğer"


class CouncilMeeting(BaseModel):
    """Bir kurulun genel toplantı kararı — karar defteri satırı (md. 184/206).

    `meeting_no` (ders yılı + tür) başına artan sıra (defter no). İzlenebilirlik
    için kaynağa (DISCIPLINE→`discipline_committee`, HONOR→`honor_board`)
    opsiyonel bağlanır; `clean()` çapraz-kurul tutarlılığını doğrular.
    """

    school_year = models.ForeignKey(
        "okul.SchoolYear",
        on_delete=models.PROTECT,
        related_name="council_meetings",
        verbose_name="ders yılı",
    )
    school_term = models.ForeignKey(
        "okul.SchoolTerm",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="council_meetings",
        verbose_name="dönem",
    )
    council_type = models.CharField(
        "kurul türü", max_length=12, choices=CouncilType.choices, db_index=True
    )
    honor_meeting_kind = models.CharField(
        "onur toplantısı türü",
        max_length=20,
        choices=HonorMeetingKind.choices,
        default=HonorMeetingKind.BOARD,
    )
    meeting_no = models.PositiveSmallIntegerField(
        "toplantı no",
        help_text="Ders yılı + kurul türü başına artan karar defteri sırası (md. 184).",
    )
    meeting_date = models.DateField("toplantı tarihi")
    agenda = models.TextField("gündem", blank=True, default="")
    decision_text = models.TextField(
        "karar (gerekçeli)",
        blank=True,
        default="",
        help_text="Gerekçeli karar metni (md. 206).",
    )
    decision_basis = models.CharField(
        "karar esası",
        max_length=10,
        choices=CouncilDecisionBasis.choices,
        default=CouncilDecisionBasis.UNANIMITY,
        help_text="Oy birliği / oy çoğunluğu (md. 191/206).",
    )
    notes = models.TextField("açıklama", blank=True, default="")
    minutes_type = models.CharField(
        "tutanak türü",
        max_length=12,
        choices=CouncilMinutesType.choices,
        default=CouncilMinutesType.GENERAL,
        help_text="Dosya görüşme tutanağı yalnız disiplin kurulunda.",
    )
    discipline_case = models.ForeignKey(
        DisciplineCase,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="council_meetings",
        verbose_name="görüşülen disiplin dosyası",
        help_text="Yalnız 'Disiplin dosyası görüşme' tutanağında; kararlar dosyadan derlenir.",
    )
    discipline_committee = models.ForeignKey(
        DisciplineCommittee,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="council_meetings",
        verbose_name="disiplin kurulu (kaynak)",
    )
    honor_board = models.ForeignKey(
        HonorBoard,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="council_meetings",
        verbose_name="onur kurulu (kaynak)",
    )

    class Meta:
        verbose_name = "kurul toplantı tutanağı"
        verbose_name_plural = "kurul toplantı tutanakları"
        ordering = ["-meeting_date", "-meeting_no", "-created_at"]
        constraints = [
            # Ders yılı + tür başına toplantı no benzersiz (silinmemişler arasında).
            models.UniqueConstraint(
                fields=["school_year", "council_type", "meeting_no"],
                condition=models.Q(deleted_at__isnull=True),
                name="uq_council_meeting_year_type_no_alive",
            ),
        ]
        indexes = [
            models.Index(
                fields=["school_year", "council_type"], name="council_meeting_year_type_idx"
            ),
        ]

    @property
    def meeting_no_display(self) -> str:
        """Resmî defter numarası görüntüsü: T001, T002 … (sayaç meeting_no)."""
        return f"T{self.meeting_no:03d}"

    def __str__(self) -> str:
        return (
            f"{self.get_council_type_display()} — Toplantı {self.meeting_no_display} "
            f"@ {self.meeting_date:%d.%m.%Y}"
        )

    def clean(self) -> None:
        """Kaynak kurul FK'sı ↔ kurul türü ve tutanak türü ↔ dosya tutarlılığını doğrular."""
        if self.council_type == CouncilType.DISCIPLINE and self.honor_board_id is not None:
            raise ValidationError(
                {"honor_board": "Disiplin kurulu toplantısı onur kuruluna bağlanamaz."}
            )
        if (
            self.council_type == CouncilType.DISCIPLINE
            and self.honor_meeting_kind != HonorMeetingKind.BOARD
        ):
            raise ValidationError(
                {"honor_meeting_kind": "Onur toplantısı türü disiplin kurulunda kullanılamaz."}
            )
        if self.council_type == CouncilType.HONOR and self.discipline_committee_id is not None:
            raise ValidationError(
                {"discipline_committee": "Onur kurulu toplantısı disiplin kuruluna bağlanamaz."}
            )
        if (
            self.minutes_type == CouncilMinutesType.CASE_REVIEW
            and self.council_type != CouncilType.DISCIPLINE
        ):
            raise ValidationError(
                {"minutes_type": "Dosya görüşme tutanağı yalnız disiplin kurulunda tutulabilir."}
            )
        if self.minutes_type == CouncilMinutesType.CASE_REVIEW and self.discipline_case_id is None:
            raise ValidationError(
                {"discipline_case": "Dosya görüşme tutanağı bir disiplin dosyasına bağlanmalıdır."}
            )
        if self.minutes_type == CouncilMinutesType.GENERAL and self.discipline_case_id is not None:
            raise ValidationError(
                {
                    "discipline_case": "Disiplin dosyası yalnız dosya görüşme tutanağına bağlanabilir."
                }
            )


class CouncilMeetingAttendee(BaseModel):
    """Kurul toplantısı katılımcısı — snapshot (md. 191 üye / md. 185/6 davetli).

    `person_name`/`title` snapshot tutanak bütünlüğü için (md. 206); `dissent_note`
    karşı görüş gerekçesi. İzlenebilirlik için kişi opsiyonel FK ile bağlanabilir
    (veli katılımcı yalnız adla — Parent tablosu yok).
    """

    meeting = models.ForeignKey(
        CouncilMeeting,
        on_delete=models.CASCADE,
        related_name="attendees",
        verbose_name="toplantı",
    )
    attendee_role = models.CharField(
        "katılımcı rolü",
        max_length=20,
        choices=CouncilAttendeeRole.choices,
        default=CouncilAttendeeRole.VOTING_MEMBER,
    )
    person_name = models.CharField("ad-soyad (snapshot)", max_length=200)
    title = models.CharField(
        "görev/ünvan",
        max_length=120,
        blank=True,
        default="",
        help_text="Örn. 'Müdür Yardımcısı', 'Rehberlik Öğretmeni', 'Onur Kurulu Başkanı'.",
    )
    is_chair = models.BooleanField("başkan", default=False)
    dissent_note = models.TextField(
        "karşı görüş gerekçesi",
        blank=True,
        default="",
        help_text="Karara karşı oy kullanan üye nedenini yazar (md. 206).",
    )
    order = models.PositiveSmallIntegerField("sıra", default=0)
    member_user = models.ForeignKey(
        "okul.Personnel",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="council_meeting_attendances",
        verbose_name="personel (opsiyonel)",
    )
    member_student = models.ForeignKey(
        "okul.Student",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="council_meeting_attendances",
        verbose_name="öğrenci (opsiyonel)",
    )

    class Meta:
        verbose_name = "kurul toplantısı katılımcısı"
        verbose_name_plural = "kurul toplantısı katılımcıları"
        ordering = ["attendee_role", "order", "id"]
        indexes = [
            models.Index(fields=["meeting", "attendee_role"], name="council_attendee_role_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.person_name} ({self.get_attendee_role_display()})"
