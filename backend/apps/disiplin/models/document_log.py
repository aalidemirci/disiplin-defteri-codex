"""Disiplin evrak kütüğü — üretilen/yazdırılan belge ve yeniden basım kopyası.

OYS `document_log.py`'den uyarlama (tasarım §4.2): `generated_by` KALDIRILDI
(tek kullanıcı). Uygulamanın ürettiği PDF, yeniden indirme/yazdırma ve SQLite
yedeğine dahil olma amacıyla base64 olarak saklanır; uygulama parolası etkinse
`EncryptedTextField` tarafından şifrelenir. Rehberlik görüşme formu (Form-2)
"no-trace"tir → kütüğe ve PDF arşivine yazılmaz.
"""

from __future__ import annotations

from django.db import models

from apps.disiplin.models.cases import DisciplineCase
from shared.crypto import EncryptedTextField
from shared.models import BaseModel


class DocumentType(models.TextChoices):
    """Üretilebilen disiplin evrak türleri (form ↔ kod eşlemesi) — OYS AYNEN."""

    STATEMENT_CALL = "STATEMENT_CALL", "İfadeye çağrı pusulası (Form-3, md. 193)"
    STATEMENT_RECORD = "STATEMENT_RECORD", "İfade tutanağı (Form-4/5/6, md. 193)"
    INFO_GATHERING = "INFO_GATHERING", "Bilgi toplama formu (Form-7/8, md. 193)"
    DEFENSE_CALL = "DEFENSE_CALL", "Savunmaya çağrı (Form-9)"
    DEFENSE_RECORD = "DEFENSE_RECORD", "Savunma tutanağı (Form-11)"
    MEETING_CALL = "MEETING_CALL", "Kurul toplantı çağrısı (Form-10, md. 190-191)"
    DEADLINE_EXTENSION = "DEADLINE_EXTENSION", "Süre uzatma (Form-12/13, md. 192/3)"
    COMMITTEE_DECISION = "COMMITTEE_DECISION", "Kurul kararı (EK-1, md. 163-170)"
    INDEX_SHEET = "INDEX_SHEET", "Dizi pusulası"
    PENALTY_NOTICE = "PENALTY_NOTICE", "Ceza/Karar tebliği (Form-14/15, md. 169/5)"
    PENALTY_DAYS_NOTICE = "PENALTY_DAYS_NOTICE", "Ceza günleri tebliği (Form-16/17, md. 172)"
    APPEAL_LETTER = "APPEAL_LETTER", "İl/İlçe itiraz yazısı (Form-18, md. 169/3)"
    WARNING_LETTER = "WARNING_LETTER", "Müdür uyarısı yazısı (Form-01/02, md. 157/7)"
    PRECAUTION_NOTICE = "PRECAUTION_NOTICE", "Tedbir bildirimi (md. 175)"
    COUNCIL_MEETING_MINUTES = "COUNCIL_MEETING_MINUTES", "Kurul toplantı tutanağı (md. 184/206)"
    BOARD_DECISION_NOTICE = "BOARD_DECISION_NOTICE", "Üst kurul kararı tebliği (md. 169/2-4)"
    OTHER = "OTHER", "Diğer"


class GeneratedDocument(BaseModel):
    """Üretilen/yazdırılan bir disiplin belgesinin kütük kaydı.

    Uygulamanın ürettiği PDF `stored_pdf_b64` alanında saklanır. Dışarıdan yalnız
    metadata olarak eklenen eski/harici evraklarda bu alan boş olabilir.
    `sort_order` dizi pusulası sırası (canonical_order ×10); `parent_document`
    doluysa alt/destekleyici evraktır (dizi pusulasında girintili).
    """

    case = models.ForeignKey(
        DisciplineCase,
        on_delete=models.CASCADE,
        related_name="generated_documents",
        verbose_name="dosya",
    )
    student = models.ForeignKey(
        "okul.Student",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="discipline_documents",
        verbose_name="öğrenci",
        help_text="Öğrenci-özgü belge (EK-1, tebliğ) için; dosya-geneli belgede boş.",
    )
    document_type = models.CharField("belge türü", max_length=32, choices=DocumentType.choices)
    title = models.CharField(
        "başlık",
        max_length=200,
        help_text="Belge başlığı snapshot (örn. 'EK-1 Kurul Kararı — 2025-2026-0001').",
    )
    document_no = models.CharField("belge/karar no", max_length=40, blank=True, default="")
    source_label = models.CharField(
        "kimden (sıfat/kaynak)",
        max_length=80,
        blank=True,
        default="",
        help_text="Katılımcı belgelerinde belgenin kimden olduğu — ifade/savunmada katılımcı "
        "rolü, bilgi almada kaynak. Üretim anında doldurulan snapshot; dizi pusulasında görünür.",
    )
    source_name = models.CharField(
        "kimden (ad)",
        max_length=150,
        blank=True,
        default="",
        help_text="Katılımcı belgesinde kişinin adı snapshot'ı (tutanak bütünlüğü).",
    )
    generated_on = models.DateField("üretim tarihi")
    notes = models.TextField("açıklama", blank=True, default="")
    sort_order = models.PositiveIntegerField(
        "dizi sırası",
        default=0,
        db_index=True,
        help_text="Dizi pusulasındaki sıra; varsayılan kanonik süreç sırası (Form-1→18), "
        "arayüzden yeniden düzenlenebilir (küçük = önce).",
    )
    page_count = models.PositiveSmallIntegerField(
        "sayfa sayısı",
        default=1,
        help_text="Belgenin sayfa sayısı; üretilen belgelerde otomatik (WeasyPrint), "
        "eklenen/alt evraklarda elle. Dizi pusulasında görünür.",
    )
    stored_pdf_b64 = EncryptedTextField(
        "saklanan PDF kopyası",
        blank=True,
        default="",
        help_text="Base64 PDF içeriği; uygulama parolası etkinse diskte şifreli tutulur.",
    )
    stored_pdf_size = models.PositiveIntegerField(
        "saklanan PDF boyutu",
        default=0,
        editable=False,
        help_text="Ham PDF boyutu (bayt); liste ekranı içeriği yüklemeden kopya varlığını gösterir.",
    )
    stored_filename = models.CharField(
        "saklanan PDF dosya adı",
        max_length=255,
        blank=True,
        default="",
    )
    parent_document = models.ForeignKey(
        "self",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="sub_documents",
        verbose_name="bağlı olduğu ana evrak",
        help_text="Doluysa bu kayıt bir ALT/destekleyici evraktır (örn. dilekçe→delil); "
        "boşsa ana evraktır. Dizi pusulasında ana evrak altında girintili listelenir.",
    )

    class Meta:
        verbose_name = "üretilen disiplin belgesi"
        verbose_name_plural = "üretilen disiplin belgeleri"
        ordering = ["sort_order", "generated_on", "created_at"]
        indexes = [
            models.Index(fields=["case"], name="disc_doc_case_idx"),
            models.Index(fields=["document_type"], name="disc_doc_type_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.case_id} — {self.get_document_type_display()} @ {self.generated_on:%d.%m.%Y}"
