"""Disiplin kararı + yasal süreler + itiraz — md. 163-175.

OYS `discipline_decisions.py`'den uyarlama (tasarım §4.2): alan listeleri
(EK-1 anlatı + öğrenci-bağlam blokları dahil) AYNEN; yalnız `student` FK'sı
`okul.Student`'a bağlanır. Koşullu unique SQLite'ta çalışır (test_models).
"""

from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db import models

from apps.disiplin.models.cases import DisciplineCase, DisciplineEvent
from apps.disiplin.models.committee import DisciplineMeeting
from shared.models import BaseModel


class PenaltyType(models.TextChoices):
    """Disiplin kurulu karar sonuçları — md. 163/1 cezaları + "ceza verilmesine yer
    olmadığı" (md. 191: kurul olayı "karara bağlamak zorundadır", ceza vermek zorunda
    değil). İlk dördü kanunla sabit ceza türleri; NO_PENALTY ceza-dışı karar sonucudur
    (davranış puanı indirimi 0, üst mercie onay/itiraz gerektirmez)."""

    REPRIMAND = "REPRIMAND", "Kınama"
    SHORT_TERM_SUSPENSION = "SHORT_TERM_SUSPENSION", "Okuldan kısa süreli uzaklaştırma"
    SCHOOL_CHANGE = "SCHOOL_CHANGE", "Okul değiştirme"
    EXPULSION = "EXPULSION", "Örgün eğitim dışına çıkarma"
    NO_PENALTY = "NO_PENALTY", "Ceza verilmesine yer olmadığı"


class ApprovalAuthority(models.TextChoices):
    """Onay/itiraz mercii — md. 163/2 + md. 169/2-3."""

    PRINCIPAL = "PRINCIPAL", "Okul müdürü"
    DISTRICT_BOARD = "DISTRICT_BOARD", "İlçe öğrenci disiplin kurulu"
    PROVINCIAL_BOARD = "PROVINCIAL_BOARD", "İl öğrenci disiplin kurulu"
    UPPER_BOARD = "UPPER_BOARD", "Öğrenci üst disiplin kurulu"


class DecisionApprovalStatus(models.TextChoices):
    """Kararın onay durumu (md. 163/2, 197).

    Müdür kararı ya onaylar ya da uygun bulmazsa gerekçeyle kurula iade eder
    (md. 197) — REDDEDEMEZ. Kurul ısrar ederse müdür ilçe kuruluna gönderir.
    REJECTED yalnız itiraz **bozması** (md. 171, resolve_appeal) ile oluşur.
    """

    PENDING = "PENDING", "Onay bekliyor"
    APPROVED = "APPROVED", "Onaylandı"
    RETURNED_TO_COMMITTEE = "RETURNED", "Kurula iade edildi (md. 197)"
    REFERRED_TO_DISTRICT = "REFERRED", "İlçe kuruluna gönderildi (md. 197)"
    REJECTED = "REJECTED", "Kaldırıldı (itiraz bozdu)"


class AppealFiledByRole(models.TextChoices):
    """İtirazı yapan — md. 169/3 (okul müdürü, 18+ öğrenci, veli)."""

    PRINCIPAL = "PRINCIPAL", "Okul müdürü"
    STUDENT_ADULT = "STUDENT_ADULT", "Öğrenci (18 yaşını tamamlamış)"
    PARENT = "PARENT", "Veli"


class AppealResult(models.TextChoices):
    """İtiraz sonucu — md. 169/4 (sonuç kesindir, yeniden itiraz edilemez)."""

    PENDING = "PENDING", "İnceleniyor"
    UPHELD = "UPHELD", "Onandı (ceza aynen)"
    REDUCED = "REDUCED", "Hafifletildi/değiştirildi"
    OVERTURNED = "OVERTURNED", "Bozuldu (ceza kaldırıldı)"


class DisciplineDecision(BaseModel):
    """Bir disiplin dosyasının bir öğrenci için resmî ceza kararı (md. 163).

    Ceza türü (`penalty_type`) kanunla sabit. `behavior_point_deduction` (md. 170) ve
    `approval_authority` (md. 163/2) cezadan OTOMATİK türetilir (services →
    discipline_periods). Tebliğ (md. 169/5) sonrası `appeal_deadline` = tebliğ + 5 iş
    günü snapshot olarak yazılır. Dosya başına öğrenciye tek (silinmemiş) karar.
    """

    case = models.ForeignKey(
        DisciplineCase,
        on_delete=models.CASCADE,
        related_name="decisions",
        verbose_name="dosya",
    )
    student = models.ForeignKey(
        "okul.Student",
        on_delete=models.PROTECT,
        related_name="discipline_decisions",
        verbose_name="öğrenci",
    )
    event = models.ForeignKey(
        DisciplineEvent,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="decisions",
        verbose_name="ilgili kurul kararı olayı",
    )
    meeting = models.ForeignKey(
        DisciplineMeeting,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="decisions",
        verbose_name="kurul toplantısı",
    )
    penalty_type = models.CharField("ceza türü", max_length=24, choices=PenaltyType.choices)
    statute_ref = models.CharField(
        "mevzuat madde atfı",
        max_length=64,
        blank=True,
        default="",
        help_text="Kanonik çapa (örn. '#madde-164'); tutanak/PDF dayanağı.",
    )
    penalty_detail = models.TextField(
        "gerekçe / fiil",
        blank=True,
        default="",
        help_text="Cezaya esas fiil ve gerekçe (md. 168 takdir hususları).",
    )
    decision_no = models.CharField("karar no", max_length=40, blank=True, default="")
    decision_date = models.DateField("karar tarihi")
    suspension_days = models.PositiveSmallIntegerField(
        "uzaklaştırma süresi (gün)",
        null=True,
        blank=True,
        help_text="Yalnız kısa süreli uzaklaştırmada 1-5 gün (md. 164/2).",
    )
    enforcement_start_date = models.DateField(
        "uzaklaştırma uygulama başlangıcı",
        null=True,
        blank=True,
        help_text="Kısa süreli uzaklaştırmanın fiilen başladığı gün; bitiş ve okula "
        "başlama iş günü (tatil hariç) hesaplanır (md. 164/2, 172).",
    )
    behavior_point_deduction = models.PositiveSmallIntegerField(
        "davranış puanı indirimi",
        default=0,
        help_text="md. 170: kınama 10, uzaklaştırma 20, okul değiştirme 40, örgün dışı 80.",
    )
    approval_authority = models.CharField(
        "onay mercii", max_length=20, choices=ApprovalAuthority.choices
    )
    approval_status = models.CharField(
        "onay durumu",
        max_length=12,
        choices=DecisionApprovalStatus.choices,
        default=DecisionApprovalStatus.PENDING,
        db_index=True,
    )
    approved_at = models.DateField("onay tarihi", null=True, blank=True)
    # md. 197 — müdürün kurula iade / ilçeye sevk gerekçesi ve tarihi (RETURNED/REFERRED).
    return_reason = models.TextField(
        "kurula iade / sevk gerekçesi",
        blank=True,
        default="",
        help_text="md. 197: müdür kararı uygun bulmazsa kurula iade veya (ısrarda) ilçeye sevk gerekçesi.",
    )
    returned_at = models.DateField(
        "iade / sevk tarihi",
        null=True,
        blank=True,
        help_text="md. 197: kurula iade veya ilçe kuruluna gönderme tarihi.",
    )
    notified_at = models.DateField("tebliğ tarihi", null=True, blank=True)
    notification_method = models.CharField(
        "tebliğ yöntemi",
        max_length=120,
        blank=True,
        default="",
        help_text="Tebligat Kanunu yöntemi (md. 169/5); tebellüğ belgesi dosyada saklanır.",
    )
    appeal_deadline = models.DateField(
        "itiraz son günü",
        null=True,
        blank=True,
        help_text="Tebliğ + 5 iş günü (md. 169/3) — tebliğde otomatik hesaplanır.",
    )
    e_school_processed_on = models.DateField(
        "e-Okul'a işlenme tarihi",
        null=True,
        blank=True,
        help_text=(
            "Kesinleşen cezanın e-Okul'a işlendiğinin kullanıcı tarafından onaylandığı tarih."
        ),
    )
    is_enforced = models.BooleanField(
        "uygulandı",
        default=False,
        help_text="md. 172/2-ç: okul değiştirmede süresi içinde itiraz varsa karar verilene "
        "kadar uygulanmaz.",
    )
    # --- EK-1 anlatı alanları — karar anında girilir, sicile işlenir (md. 168, 193).
    accused_statement_summary = models.TextField(
        "öğrencinin ifadesinin özeti",
        blank=True,
        default="",
        help_text="EK-1 (a): cezalandırılan öğrencinin ifadesinin özeti (md. 193).",
    )
    witness_statement_summary = models.TextField(
        "tanıkların ifadesinin özeti",
        blank=True,
        default="",
        help_text="EK-1 (b): tanıkların ifadesinin özeti (md. 193).",
    )
    other_evidence = models.TextField(
        "diğer deliller",
        blank=True,
        default="",
        help_text="EK-1 (c): davranışın tespitine yarayan diğer deliller.",
    )
    mitigating_aggravating = models.TextField(
        "hafifleten/şiddetlendiren nedenler",
        blank=True,
        default="",
        help_text="EK-1: cezayı hafifleten veya şiddetlendiren nedenler (md. 168).",
    )
    committee_opinion = models.TextField(
        "kurulun kanaati",
        blank=True,
        default="",
        help_text="EK-1: okul öğrenci ödül ve disiplin kurulunun kanaati.",
    )
    psychosocial_summary = models.TextField(
        "psikososyal değerlendirme özeti",
        blank=True,
        default="",
        help_text="Rehberlik Form-2 raporundan psikososyal durum özeti (md. 192).",
    )
    # --- EK-1 öğrenci-bağlam alanları — resmî EK-1 formunun "ÖĞRENCİNİN" bloğu.
    boarding_status = models.CharField(
        "yatılılık durumu",
        max_length=120,
        blank=True,
        default="",
        help_text="EK-1: paralı/parasız yatılı ya da gündüzlü olduğu.",
    )
    academic_standing = models.CharField(
        "başarı durumu", max_length=200, blank=True, default="", help_text="EK-1: başarı durumu."
    )
    health_status = models.TextField(
        "sağlık durumu", blank=True, default="", help_text="EK-1: sağlık durumu."
    )
    family_economic_status = models.CharField(
        "ailesinin ekonomik durumu",
        max_length=200,
        blank=True,
        default="",
        help_text="EK-1: ailesinin ekonomik durumu.",
    )
    lives_with_family = models.CharField(
        "ailesiyle oturma durumu",
        max_length=120,
        blank=True,
        default="",
        help_text="EK-1: ailesi ile birlikte oturup oturmadığı.",
    )
    parents_alive = models.CharField(
        "anne-baba sağ mı",
        max_length=120,
        blank=True,
        default="",
        help_text="EK-1: anne-babasının sağ olup olmadığı.",
    )
    parents_biological = models.CharField(
        "anne-baba öz mü",
        max_length=120,
        blank=True,
        default="",
        help_text="EK-1: anne-babasının öz olup olmadığı.",
    )
    studies_near_family = models.CharField(
        "aile yanında okuma durumu",
        max_length=120,
        blank=True,
        default="",
        help_text="EK-1: ailesinin yanında okuyup okumadığı.",
    )
    upbringing_environment = models.TextField(
        "büyüyüp yetiştiği çevre",
        blank=True,
        default="",
        help_text="EK-1: büyüyüp yetiştiği çevre.",
    )
    family_residence_area = models.TextField(
        "ailesinin oturduğu yer ve çevresi",
        blank=True,
        default="",
        help_text="EK-1: ailesinin oturduğu yer ve çevresi.",
    )
    incident_place = models.CharField(
        "davranışın yapıldığı yer",
        max_length=200,
        blank=True,
        default="",
        help_text="EK-1: cezayı gerektiren davranışının yapıldığı yer.",
    )
    incident_date = models.DateField(
        "davranışın yapıldığı tarih",
        null=True,
        blank=True,
        help_text="EK-1: cezayı gerektiren davranışının yapıldığı tarih.",
    )
    prior_penalties_summary = models.TextField(
        "şimdiye kadar aldığı cezalar ve genel durumu",
        blank=True,
        default="",
        help_text="EK-1: önceki cezalar (karar anında otomatik derlenir) + genel durum.",
    )
    notes = models.TextField("açıklama", blank=True, default="")

    class Meta:
        verbose_name = "disiplin kararı"
        verbose_name_plural = "disiplin kararları"
        ordering = ["-decision_date", "-created_at"]
        constraints = [
            # Dosya başına öğrenciye tek (silinmemiş) resmî karar.
            models.UniqueConstraint(
                fields=["case", "student"],
                condition=models.Q(deleted_at__isnull=True),
                name="uq_disc_decision_case_student_alive",
            )
        ]
        indexes = [
            models.Index(fields=["case"], name="disc_decision_case_idx"),
            models.Index(fields=["student"], name="disc_decision_student_idx"),
            models.Index(fields=["approval_status"], name="disc_decision_status_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.case_id}/{self.student_id} — {self.get_penalty_type_display()}"

    def clean(self) -> None:
        """Ceza türüne özgü tutarlılık (md. 164/2 uzaklaştırma süresi)."""
        errors: dict[str, str] = {}
        if self.penalty_type == PenaltyType.SHORT_TERM_SUSPENSION:
            days = self.suspension_days
            if days is None or not (1 <= days <= 5):
                errors["suspension_days"] = (
                    "Kısa süreli uzaklaştırma 1-5 gün olmalıdır (md. 164/2)."
                )
        elif self.suspension_days is not None:
            errors["suspension_days"] = (
                "Uzaklaştırma süresi yalnız kısa süreli uzaklaştırmada girilir."
            )
        if errors:
            raise ValidationError(errors)


class DisciplineAppeal(BaseModel):
    """Bir disiplin kararına itiraz — md. 169/3-4.

    `appeal_authority` (üst kurul) cezadan OTOMATİK türetilir. `within_deadline` ve
    `forward_deadline` itiraz açılışında snapshot yazılır (iş günü mantığı). İtiraz
    sonucu (`result`) kesindir (md. 169/4 — yeniden itiraz edilemez).
    """

    decision = models.ForeignKey(
        DisciplineDecision,
        on_delete=models.CASCADE,
        related_name="appeals",
        verbose_name="karar",
    )
    filed_on = models.DateField("itiraz başvuru tarihi")
    filed_by_role = models.CharField(
        "itirazı yapan", max_length=16, choices=AppealFiledByRole.choices
    )
    filed_by_name = models.CharField("itirazı yapan (ad)", max_length=200, blank=True, default="")
    within_deadline = models.BooleanField(
        "süresinde mi",
        default=True,
        help_text="Başvuru, tebliğ + 5 iş günü itiraz süresi içinde mi (md. 169/3).",
    )
    appeal_authority = models.CharField(
        "itiraz mercii", max_length=20, choices=ApprovalAuthority.choices
    )
    forward_deadline = models.DateField(
        "sevk son günü",
        null=True,
        blank=True,
        help_text="Başvuru + 5 iş günü; müdürlüğün üst kurula sevk süresi (md. 169/3).",
    )
    forwarded_on = models.DateField("üst kurula sevk tarihi", null=True, blank=True)
    result = models.CharField(
        "sonuç",
        max_length=12,
        choices=AppealResult.choices,
        default=AppealResult.PENDING,
        db_index=True,
    )
    resulted_on = models.DateField("sonuç tarihi", null=True, blank=True)
    result_notes = models.TextField("sonuç açıklaması", blank=True, default="")

    class Meta:
        verbose_name = "disiplin itirazı"
        verbose_name_plural = "disiplin itirazları"
        ordering = ["-filed_on", "-created_at"]
        indexes = [
            models.Index(fields=["decision"], name="disc_appeal_decision_idx"),
            models.Index(fields=["result"], name="disc_appeal_result_idx"),
        ]

    def __str__(self) -> str:
        return f"İtiraz #{self.pk} (karar {self.decision_id}) — {self.get_result_display()}"
