"""Onur kurulu + onur belgesi — honors-LITE (tasarım §4.2).

OYS `honors.py`'den SADELEŞTİRİLMİŞ uyarlama: yalnız 3 onur PDF'inin
(teklif formu + uygun görüş/karar + belge) şablon gereksinimleri kadar alan.

Alınmayanlar (OYS iş-akışı parçaları): `ProposalWindow` + `ProposalWindowTerm`
(teklif dönemi penceresi), `FormDeliveryStatus`/`form_delivery_*` (fiziksel form
teslim takibi), `recommended_by`/`awarded_by_committee` FK izleri (PDF render
yıl kurullarından çözer), `superseded_*` kardeş-eleme izleri + SUPERSEDED durumu,
`teacher_proposal_limit`. `criteria` ArrayField (Postgres) → JSONField (SQLite).
`chair` → `okul.Personnel`.
"""

from __future__ import annotations

from django.db import models

from shared.models import BaseModel


class HonorCertificateStatus(models.TextChoices):
    """Onur belgesi durum makinesi (md. 161 + 183/b) — tek yönlü süreç."""

    PROPOSED = "PROPOSED", "Teklif edildi"
    HONOR_BOARD_RECOMMENDED = "HONOR_BOARD_RECOMMENDED", "Onur kurulu uygun gördü"
    AWARDED = "AWARDED", "Ödül ve disiplin kurulu kabul etti"
    PRINCIPAL_APPROVED = "PRINCIPAL_APPROVED", "Okul müdürü onayladı"
    PRINCIPAL_REJECTED = "PRINCIPAL_REJECTED", "Okul müdürü onaylamadı"
    REJECTED = "REJECTED", "Uygun görülmedi"


class HonorProposerRole(models.TextChoices):
    """Onur belgesini teklif eden tarafın rolü (md. 161/1)."""

    STUDENT = "STUDENT", "Öğrenci"
    TEACHER = "TEACHER", "Öğretmen"
    ADMINISTRATION = "ADMINISTRATION", "Okul yönetimi"


class HonorCriterion(models.TextChoices):
    """Onur belgesi örnek davranış kriterleri (md. 161/1 a-ğ + 161/2 ek) — OYS AYNEN."""

    LANGUAGE = "LANGUAGE", "(a) Türkçeyi doğru, güzel ve etkili kullanarak örnek olmak"
    ACHIEVEMENT = "ACHIEVEMENT", "(b) Bilimsel/sosyal etkinliklerde liderlik ve üstün başarı"
    RESOURCES = "RESOURCES", "(c) Okul araç-gereci ve çevreyi koruma/gözetmede örneklik"
    MANNERS = "MANNERS", "(ç) Görgü kuralları ve insan ilişkilerinde örneklik"
    TRAFFIC = "TRAFFIC", "(d) Trafik kurallarına uymada örnek davranış"
    IT = "IT", "(e) Bilişim araçlarını kullanmada iyi örneklik"
    ATTENDANCE = "ATTENDANCE", "(f) Okula ve derslere düzenli devam, arkadaşlarına örneklik"
    SOCIAL_RESPONSIBILITY = (
        "SOCIAL_RESPONSIBILITY",
        "(g) Sosyal sorumluluk programı çalışmalarında görev almak",
    )
    SAFETY = "SAFETY", "(ğ) Sağlık ve güvenlik tedbirlerine uymada örneklik"
    OTHER = "OTHER", "Öğretmenler kurulunca belirlenen diğer davranış (md. 161/2)"


class HonorGeneralAssemblyMember(BaseModel):
    """Her şubenin Onur Genel Kurulu temsilcisi ve görev tarihçesi (md. 178-181)."""

    school_year = models.ForeignKey(
        "okul.SchoolYear",
        on_delete=models.PROTECT,
        related_name="honor_general_assembly_members",
        verbose_name="ders yılı",
    )
    member_student = models.ForeignKey(
        "okul.Student",
        on_delete=models.PROTECT,
        related_name="honor_general_assembly_memberships",
        verbose_name="öğrenci temsilci",
    )
    class_level = models.PositiveSmallIntegerField("sınıf")
    class_section = models.CharField("şube", max_length=8)
    member_name = models.CharField("üye adı (snapshot)", max_length=200)
    effective_from = models.DateField("görev başlangıcı")
    effective_until = models.DateField("görev bitişi", null=True, blank=True)
    end_reason = models.CharField("görev bitiş nedeni", max_length=255, blank=True, default="")
    replaced_member = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="replacements",
        verbose_name="yerine seçildiği üye",
    )

    class Meta:
        verbose_name = "onur genel kurulu temsilcisi"
        verbose_name_plural = "onur genel kurulu temsilcileri"
        ordering = ["class_level", "class_section", "effective_from"]
        constraints = [
            models.UniqueConstraint(
                fields=["school_year", "class_level", "class_section"],
                condition=models.Q(effective_until__isnull=True, deleted_at__isnull=True),
                name="uq_honor_assembly_active_branch",
            ),
        ]
        indexes = [
            models.Index(
                fields=["school_year", "class_level", "class_section"],
                name="honor_assembly_branch_idx",
            ),
        ]

    @property
    def is_active(self) -> bool:
        return self.effective_until is None


class HonorBoard(BaseModel):
    """Onur Kurulu — ders yılı başına bir kurul (md. 180-184).

    Ödül-disiplin kurulundan (`DisciplineCommittee`, md. 185) AYRIDIR. `chair`:
    öğretmenler kurulunca ödül-disiplin kurulu dışından seçilen öğretmen (md. 182).
    """

    school_year = models.ForeignKey(
        "okul.SchoolYear",
        on_delete=models.PROTECT,
        related_name="honor_boards",
        verbose_name="ders yılı",
    )
    chair = models.ForeignKey(
        "okul.Personnel",
        on_delete=models.PROTECT,
        related_name="chaired_honor_boards",
        verbose_name="onur kurulu başkanı",
        help_text="Öğretmenler kurulunca ödül-disiplin kurulu dışından seçilen öğretmen (md. 182).",
    )
    substitute_chair = models.ForeignKey(
        "okul.Personnel",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="substitute_chaired_honor_boards",
        verbose_name="onur kurulu başkan yedeği",
    )
    notes = models.TextField("açıklama", blank=True, default="")

    class Meta:
        verbose_name = "onur kurulu"
        verbose_name_plural = "onur kurulları"
        ordering = ["-created_at"]
        constraints = [
            # Ders yılı başına tek (silinmemiş) onur kurulu.
            models.UniqueConstraint(
                fields=["school_year"],
                condition=models.Q(deleted_at__isnull=True),
                name="uq_honor_board_year_alive",
            )
        ]
        indexes = [
            models.Index(fields=["school_year"], name="honor_board_year_idx"),
        ]

    def __str__(self) -> str:
        return f"Onur Kurulu {self.school_year_id} (başkan {self.chair_id})"


class HonorBoardMember(BaseModel):
    """Onur kurulu üyesi — yalnız öğrenci (md. 180).

    Her sınıf seviyesinden birer öğrenci; son/11. sınıf öğrencisi ikinci başkan
    (`is_second_chair`). PDF'ler (uygun görüş/karar) asıl üyeleri listeler —
    honors-lite'ta bu model o yüzden korunur (`honor_documents` tüketimi).
    """

    board = models.ForeignKey(
        HonorBoard,
        on_delete=models.CASCADE,
        related_name="members",
        verbose_name="onur kurulu",
    )
    assembly_member = models.ForeignKey(
        HonorGeneralAssemblyMember,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="board_memberships",
        verbose_name="genel kurul seçim kaynağı",
    )
    member_student = models.ForeignKey(
        "okul.Student",
        on_delete=models.PROTECT,
        related_name="honor_board_memberships",
        verbose_name="öğrenci üye",
    )
    grade_level = models.PositiveSmallIntegerField(
        "temsil edilen sınıf seviyesi",
        null=True,
        blank=True,
        help_text="Üyenin temsil ettiği sınıf seviyesi (9-12; md. 180).",
    )
    is_second_chair = models.BooleanField(
        "ikinci başkan",
        default=False,
        help_text="Son/11. sınıf öğrencisi ikinci başkandır (md. 180).",
    )
    is_substitute = models.BooleanField("yedek üye", default=False, db_index=True)
    order = models.PositiveSmallIntegerField("sıra", default=0)
    title = models.CharField(
        "görev/ünvan",
        max_length=120,
        blank=True,
        default="",
        help_text="Örn. 'İkinci başkan', 'Yedek ikinci başkan'.",
    )
    member_name = models.CharField(
        "üye adı (snapshot)",
        max_length=200,
        blank=True,
        default="",
        help_text="Ekleme anındaki ad-soyad; karar defteri bütünlüğü için (md. 184).",
    )
    effective_from = models.DateField("görev başlangıcı", null=True, blank=True)
    effective_until = models.DateField("görev bitişi", null=True, blank=True)
    end_reason = models.CharField("görev bitiş nedeni", max_length=255, blank=True, default="")

    class Meta:
        verbose_name = "onur kurulu üyesi"
        verbose_name_plural = "onur kurulu üyeleri"
        ordering = ["is_substitute", "grade_level", "order", "id"]
        indexes = [
            models.Index(fields=["board", "is_substitute"], name="honor_member_board_sub_idx"),
        ]

    def __str__(self) -> str:
        kind = "yedek" if self.is_substitute else "asıl"
        chair = " · ikinci başkan" if self.is_second_chair else ""
        return f"{self.member_name or self.pk} ({kind}{chair})"

    @property
    def is_active(self) -> bool:
        return self.effective_until is None


class HonorCertificate(BaseModel):
    """Onur belgesi — davranış/sosyal temelli ödül (md. 161). LITE model.

    Durum makinesi: teklif → onur kurulu uygun görüşü (md. 183/b) → ödül-disiplin
    kurulu kararı (md. 161). Puan şartı YOK ama 'davranış puanı indirilmemiş'
    olmalı (serviste doğrulanır). `criteria`: md. 161 a-ğ kriter kodları listesi
    (JSONField — SQLite'ta ArrayField ikamesi).
    """

    student = models.ForeignKey(
        "okul.Student",
        on_delete=models.PROTECT,
        related_name="honor_certificates",
        verbose_name="öğrenci",
    )
    school_year = models.ForeignKey(
        "okul.SchoolYear",
        on_delete=models.PROTECT,
        related_name="honor_certificates",
        verbose_name="ders yılı",
    )
    school_term = models.ForeignKey(
        "okul.SchoolTerm",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="honor_certificate_proposals",
        verbose_name="teklif dönemi",
    )
    status = models.CharField(
        "durum",
        max_length=24,
        choices=HonorCertificateStatus.choices,
        default=HonorCertificateStatus.PROPOSED,
        db_index=True,
    )
    proposer_role = models.CharField(
        "teklif eden",
        max_length=16,
        choices=HonorProposerRole.choices,
        help_text="Teklifi yapan taraf (md. 161): öğrenci, öğretmen veya yönetim.",
    )
    proposer_name = models.CharField(
        "teklif eden adı",
        max_length=200,
        blank=True,
        default="",
        help_text="Teklif eden kişinin adı (snapshot) — PDF imza satırında kullanılır.",
    )
    criteria = models.JSONField(
        "kriterler",
        default=list,
        blank=True,
        help_text="md. 161 a-ğ örnek davranış kodlarından bir veya birkaçı (HonorCriterion).",
    )
    justification = models.TextField(
        "gerekçe",
        blank=True,
        default="",
        help_text="Teklifin somut dayanağı (örnek davranışın açıklaması).",
    )
    recommended_at = models.DateField("uygun görüş tarihi", null=True, blank=True)
    awarded_at = models.DateField("ödül ve disiplin kurulu karar tarihi", null=True, blank=True)
    principal_decided_at = models.DateField("okul müdürü karar tarihi", null=True, blank=True)
    principal_decision_reason = models.TextField(
        "okul müdürü karar açıklaması", blank=True, default=""
    )
    rejection_reason = models.TextField("ret gerekçesi", blank=True, default="")
    rejected_at = models.DateField("ret tarihi", null=True, blank=True)

    class Meta:
        verbose_name = "onur belgesi"
        verbose_name_plural = "onur belgeleri"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["student", "school_year"], name="honor_cert_stu_year_idx"),
            models.Index(fields=["school_year", "status"], name="honor_cert_year_status_idx"),
            models.Index(fields=["school_term", "status"], name="honor_cert_term_status_idx"),
        ]

    def __str__(self) -> str:
        return f"Onur Belgesi #{self.pk} — öğrenci {self.student_id} ({self.get_status_display()})"


class HonorCertificateEventType(models.TextChoices):
    PROPOSED = "PROPOSED", "Teklif edildi"
    RECOMMENDED = "RECOMMENDED", "Onur kurulu uygun gördü"
    AWARDED = "AWARDED", "Ödül ve disiplin kurulu kabul etti"
    PRINCIPAL_APPROVED = "PRINCIPAL_APPROVED", "Okul müdürü onayladı"
    PRINCIPAL_REJECTED = "PRINCIPAL_REJECTED", "Okul müdürü onaylamadı"
    REJECTED = "REJECTED", "Uygun görülmedi"


class HonorCertificateEvent(BaseModel):
    """Onur belgesi durum değişikliğinin dönem ve toplantı izidir."""

    certificate = models.ForeignKey(
        HonorCertificate,
        on_delete=models.CASCADE,
        related_name="events",
        verbose_name="onur belgesi",
    )
    event_type = models.CharField(
        "işlem",
        max_length=20,
        choices=HonorCertificateEventType.choices,
    )
    event_date = models.DateField("işlem tarihi")
    school_term = models.ForeignKey(
        "okul.SchoolTerm",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="honor_certificate_events",
        verbose_name="dönem",
    )
    meeting = models.ForeignKey(
        "disiplin.CouncilMeeting",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="honor_certificate_events",
        verbose_name="dayanak toplantı",
    )
    explanation = models.TextField("açıklama", blank=True, default="")

    class Meta:
        verbose_name = "onur belgesi işlem olayı"
        verbose_name_plural = "onur belgesi işlem olayları"
        ordering = ["event_date", "created_at"]
        indexes = [
            models.Index(
                fields=["certificate", "event_type"],
                name="honor_event_cert_type_idx",
            )
        ]
