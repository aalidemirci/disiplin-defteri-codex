"""Disiplin süreç takibi — dosya, aşama olayları, dosya ekleri.

OYS `ogrenci_isleri/models/discipline_cases.py`'den FK-ikameli uyarlama
(tasarım §4.2). Alan listeleri AYNEN; farklar:

- `petitioner_user` → `okul.Personnel` (login'siz sicil).
- `petitioner_parent` KALDIRILDI: VELI rolünde dilekçe İLGİLİ ÖĞRENCİ FK'sıyla
  bağlanır (`petitioner_student`) + veli adı `petitioner_name` snapshot'ında.
- `DisciplineEvent.performed_by` KALDIRILDI (tek kullanıcı — "kim yaptı" anlamsız).
- `assigned_guidance` FK → `assigned_guidance_name` Char (sinyalsiz rehberlik,
  tasarım §2/5 — rehber sistemin kullanıcısı değil).
- `DisciplineAttachment.uploaded_by` KALDIRILDI.
- `kvkk_personal_data` sınıf bayrakları alınmadı (denetim modülü yok; program
  zaten bütünüyle KVKK kapsamındaki tek dosyalık disiplin arşividir).
"""

from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db import models

from shared.models import BaseModel


class PetitionerRole(models.TextChoices):
    """Dilekçeyi veren kişinin rolü."""

    OGRETMEN = "OGRETMEN", "Öğretmen"
    VELI = "VELI", "Veli"
    OGRENCI = "OGRENCI", "Öğrenci"
    IDARE = "IDARE", "İdare"
    DIGER = "DIGER", "Diğer"


class CaseStage(models.TextChoices):
    """Disiplin sürecinin aşamaları (durum makinesi düğümleri, state_machine.py)."""

    PETITION = "PETITION", "Dilekçe alındı"
    GUIDANCE_REFERRED = "GUIDANCE_REFERRED", "Rehberliğe sevk edildi"
    GUIDANCE_RETURNED = "GUIDANCE_RETURNED", "Rehberlikten döndü"
    DECIDED = "DECIDED", "Müdür değerlendirmesi / sevk kararı"
    COMMITTEE_DONE = "COMMITTEE_DONE", "Kurul kararı tamamlandı"
    CLOSED = "CLOSED", "Kapatıldı"


class PrincipalDecision(models.TextChoices):
    """Müdürün değerlendirme/sevk kararı — DECIDED aşamasında TEK seçilir.

    Müdür ya uyarır (sicile işlenip kapanır) ya bir kurula sevk eder; bir arada olmaz.
    """

    WRITTEN_WARNING = "WRITTEN_WARNING", "Yazılı Uyarı"
    HONOR_COMMITTEE = "HONOR_COMMITTEE", "Onur Kuruluna Sevk"
    DISCIPLINE_COMMITTEE = "DISCIPLINE_COMMITTEE", "Disiplin Kuruluna Sevk"


class AttachmentType(models.TextChoices):
    """Disiplin dosya eki türü."""

    PETITION_SCAN = "PETITION_SCAN", "Dilekçe taraması"
    GUIDANCE_FORM = "GUIDANCE_FORM", "Rehberlik görüşme formu"
    PRINCIPAL_DECISION = "PRINCIPAL_DECISION", "Müdür değerlendirme/sevk belgesi"
    COMMITTEE_DECISION = "COMMITTEE_DECISION", "Kurul kararı belgesi"
    OTHER = "OTHER", "Diğer"


class DisciplineDecisionType(BaseModel):
    """Kurul karar tipi lookup tablosu — ayarlar ekranından yönetilir.

    Boş başlar; kullanıcı gerçek kararları (kınama, kısa süreli uzaklaştırma vb.)
    ekler. Kod değişikliği gerekmez.
    """

    code = models.CharField("kod", max_length=50, unique=True)
    name = models.CharField("ad", max_length=200)
    description = models.TextField("açıklama", blank=True, default="")
    is_active = models.BooleanField("aktif", default=True)
    sort_order = models.PositiveSmallIntegerField("sıra", default=0)

    class Meta:
        verbose_name = "disiplin karar tipi"
        verbose_name_plural = "disiplin karar tipleri"
        ordering = ["sort_order", "name"]

    def __str__(self) -> str:
        return f"{self.name} ({self.code})"


class DisciplineCase(BaseModel):
    """Bir disiplin dosyası — bir veya birden çok öğrenci, aşamalı süreç.

    `current_stage` durum makinesiyle ilerler (state_machine.py). Her aşama bir
    `DisciplineEvent` satırı olarak zaman damgalı kaydedilir (geçmiş korunur).
    Silme yok (soft delete); `closed_at` null ise dosya aktiftir.
    """

    case_no = models.CharField(
        "dosya no",
        max_length=30,
        unique=True,
        help_text="Ders yılı-sıra biçiminde; örn. 2025-2026-0001 (services.generate_case_no).",
    )
    petition_date = models.DateField("dilekçe tarihi")
    # Dilekçeyi verenin ham adı (snapshot — geçmiş bütünlüğü için her zaman tutulur).
    petitioner_name = models.CharField("dilekçeyi veren", max_length=200)
    petitioner_role = models.CharField(
        "dilekçe veren rolü", max_length=20, choices=PetitionerRole.choices
    )
    # Role göre opsiyonel FK — yanlış yazımdan ilişkisiz kayıt önleme. clean()
    # petitioner_role ↔ doldurulmuş FK tutarlılığını doğrular. VELI rolünde veli
    # tablosu OLMADIĞINDAN ilgili öğrenci bağlanır (veli adı snapshot'ta).
    # IDARE/DIGER rollerinde hiçbir FK doldurulmaz (serbest metin).
    petitioner_user = models.ForeignKey(
        "okul.Personnel",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="petitioned_discipline_cases",
        verbose_name="dilekçe veren personel",
        help_text="petitioner_role=OGRETMEN ise dolu olmalı.",
    )
    petitioner_student = models.ForeignKey(
        "okul.Student",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="petitioned_discipline_cases",
        verbose_name="dilekçe veren/ilgili öğrenci",
        help_text="petitioner_role=OGRENCI ise dilekçeyi veren öğrenci; VELI ise velinin öğrencisi.",
    )
    summary = models.TextField("olay özeti")
    current_stage = models.CharField(
        "güncel aşama",
        max_length=20,
        choices=CaseStage.choices,
        default=CaseStage.PETITION,
        db_index=True,
    )
    closed_at = models.DateTimeField("kapatılma", null=True, blank=True, db_index=True)

    students: models.ManyToManyField[models.Model, DisciplineCaseStudent] = models.ManyToManyField(
        "okul.Student",
        through="DisciplineCaseStudent",
        related_name="discipline_cases",
        verbose_name="ilgili öğrenciler",
    )

    class Meta:
        verbose_name = "disiplin dosyası"
        verbose_name_plural = "disiplin dosyaları"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["current_stage"], name="disc_case_stage_idx"),
            models.Index(fields=["closed_at"], name="disc_case_closed_idx"),
            models.Index(fields=["petition_date"], name="disc_case_petition_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.case_no} — {self.get_current_stage_display()}"

    def clean(self) -> None:
        """petitioner_role ↔ doldurulmuş FK tutarlılığını doğrular.

        Kurallar (OYS'den fark: VELI rolü öğrenci FK'sına bağlanır):
          - OGRETMEN: petitioner_user dolu, student boş olmalı.
          - VELI / OGRENCI: petitioner_student dolu, user boş olmalı.
          - IDARE/DIGER: hiçbir FK doldurulmaz (serbest metin yeterli).
        Hiç FK yoksa doğrulama atlanır (yalnız create'te view zorlar).
        """
        any_fk = self.petitioner_user_id is not None or self.petitioner_student_id is not None
        if not any_fk:
            return

        expected: dict[str, str] = {
            PetitionerRole.OGRETMEN: "petitioner_user",
            PetitionerRole.VELI: "petitioner_student",
            PetitionerRole.OGRENCI: "petitioner_student",
        }
        wanted = expected.get(self.petitioner_role)
        if wanted is None:
            raise ValidationError(
                {
                    "petitioner_role": (
                        "Bu rolde dilekçe veren için FK doldurulmamalı (serbest metin)."
                    )
                }
            )

        provided = {
            "petitioner_user": self.petitioner_user_id,
            "petitioner_student": self.petitioner_student_id,
        }
        for field, val in provided.items():
            if field != wanted and val is not None:
                raise ValidationError(
                    {field: f"Bu rolde bu alan boş olmalı (yalnız {wanted} doldurulur)."}
                )


class DisciplineCaseStudent(models.Model):
    """Disiplin dosyası ↔ öğrenci through tablosu (bir dosyada çoklu öğrenci)."""

    case = models.ForeignKey(
        DisciplineCase,
        on_delete=models.CASCADE,
        related_name="case_students",
        verbose_name="dosya",
    )
    student = models.ForeignKey(
        "okul.Student",
        on_delete=models.PROTECT,
        related_name="discipline_case_links",
        verbose_name="öğrenci",
    )

    class Meta:
        verbose_name = "disiplin dosyası öğrencisi"
        verbose_name_plural = "disiplin dosyası öğrencileri"
        constraints = [
            models.UniqueConstraint(fields=["case", "student"], name="uq_disc_case_student")
        ]
        indexes = [
            models.Index(fields=["student"], name="disc_cs_student_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.case_id} ↔ {self.student_id}"


class DisciplineEvent(BaseModel):
    """Sürecin bir aşaması — zaman damgalı (geçmiş korunur).

    `is_override`: durum makinesi gerekçeyle delinip geçildiyse işaretlenir;
    `override_reason` zorunludur. `assigned_guidance_name`: GUIDANCE_REFERRED
    aşamasında sevk edilen rehber öğretmenin adı (elle girilir — rehber sistemin
    kullanıcısı değildir; tasarım §2/5).
    """

    case = models.ForeignKey(
        DisciplineCase,
        on_delete=models.CASCADE,
        related_name="events",
        verbose_name="dosya",
    )
    stage = models.CharField("aşama", max_length=20, choices=CaseStage.choices)
    event_date = models.DateField("aşama tarihi")
    recorded_at = models.DateTimeField("sisteme giriş anı", auto_now_add=True)
    notes = models.TextField("açıklama", blank=True, default="")

    # GUIDANCE_REFERRED — sevk edilen rehber öğretmenin adı (snapshot).
    assigned_guidance_name = models.CharField(
        "sevk edilen rehber", max_length=200, blank=True, default=""
    )
    # GUIDANCE_RETURNED — rehberliğin kısa raporu (elle girilir).
    guidance_outcome = models.TextField("rehberlik dönüş raporu", blank=True, default="")
    # DECIDED — müdür değerlendirme/sevk kararı (TEK seçim); tek-elemanlı liste.
    principal_decisions = models.JSONField("müdür kararları", null=True, blank=True)
    # COMMITTEE_DONE — kurul kararı.
    committee_decision_type = models.ForeignKey(
        DisciplineDecisionType,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="events",
        verbose_name="kurul karar tipi",
    )
    committee_decision_text = models.TextField("kurul karar metni", blank=True, default="")

    is_override = models.BooleanField("override", default=False)
    override_reason = models.CharField("override gerekçesi", max_length=255, blank=True, default="")

    class Meta:
        verbose_name = "disiplin olayı"
        verbose_name_plural = "disiplin olayları"
        ordering = ["recorded_at"]
        indexes = [
            models.Index(fields=["case", "stage"], name="disc_event_case_stage_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.case_id} — {self.get_stage_display()} @ {self.event_date:%d.%m.%Y}"

    def clean(self) -> None:
        """Aşamaya özgü zorunlu alanları doğrular (OYS kuralları AYNEN)."""
        errors: dict[str, str] = {}

        if self.stage == CaseStage.GUIDANCE_RETURNED and not (self.guidance_outcome or "").strip():
            errors["guidance_outcome"] = "Rehberlik dönüşünde kısa rapor zorunludur."

        if self.stage == CaseStage.DECIDED:
            # Tek seçim: müdür ya uyarır ya bir kurula sevk eder — bir arada olmaz.
            decisions = self.principal_decisions or []
            valid = set(PrincipalDecision.values)
            if not isinstance(decisions, list) or len(decisions) != 1:
                errors["principal_decisions"] = (
                    "Müdür değerlendirmesi tek seçimdir: yazılı uyarı, onur kuruluna sevk "
                    "veya disiplin kuruluna sevk (bir arada seçilemez)."
                )
            elif decisions[0] not in valid:
                errors["principal_decisions"] = "Geçersiz müdür kararı değeri."

        if self.stage == CaseStage.COMMITTEE_DONE:
            if self.committee_decision_type_id is None:
                errors["committee_decision_type"] = "Kurul karar tipi zorunludur."
            if not (self.committee_decision_text or "").strip():
                errors["committee_decision_text"] = "Kurul karar metni zorunludur."

        if self.is_override and not (self.override_reason or "").strip():
            errors["override_reason"] = "Override işleminde gerekçe zorunludur."

        if errors:
            raise ValidationError(errors)


class DisciplineAttachment(BaseModel):
    """Disiplin dosya eki — dilekçe taraması, form, karar belgesi.

    Dosya, veri dizini altındaki media klasöründe `discipline/case_<id>/<uuid>.<ext>`
    yolunda saklanır; orijinal ad DB'de tutulur, dosya sistemindeki ad tahmin
    edilemez (UUID).
    """

    case = models.ForeignKey(
        DisciplineCase,
        on_delete=models.CASCADE,
        related_name="attachments",
        verbose_name="dosya",
    )
    event = models.ForeignKey(
        DisciplineEvent,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="attachments",
        verbose_name="ilgili aşama",
    )
    file_path = models.CharField(
        "dosya yolu",
        max_length=500,
        help_text="Media kökü altında göreli yol (örn. discipline/case_42/<uuid>.pdf).",
    )
    original_filename = models.CharField("orijinal ad", max_length=255)
    file_type = models.CharField(
        "ek türü",
        max_length=20,
        choices=AttachmentType.choices,
        default=AttachmentType.OTHER,
    )
    file_size_bytes = models.PositiveIntegerField("boyut (bayt)")
    mime_type = models.CharField("MIME türü", max_length=100)
    sha256 = models.CharField(
        "SHA256",
        max_length=64,
        help_text="Bütünlük doğrulaması; aynı dosya yeniden yüklenirse uyarı.",
    )
    uploaded_at = models.DateTimeField("yükleme anı", auto_now_add=True)

    class Meta:
        verbose_name = "disiplin dosya eki"
        verbose_name_plural = "disiplin dosya ekleri"
        ordering = ["-uploaded_at"]
        indexes = [
            models.Index(fields=["case"], name="disc_att_case_idx"),
            models.Index(fields=["sha256"], name="disc_att_sha256_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.original_filename} ({self.get_file_type_display()})"
