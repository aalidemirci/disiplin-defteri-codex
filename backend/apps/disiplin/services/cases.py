"""Disiplin süreci — dosya açma, aşama olayları (durum makinesi), kapanış, ekler.

OYS `services/discipline_cases.py`'den temizlenerek taşındı (tasarım §4.4):
- Sinyal emit'leri (`_emit_referred`/`_emit_case_updated`) + `_audit_write` +
  `_log_override` SİLİNDİ (bildirim/denetim modülü yok).
- Rol kontrolleri SİLİNDİ (tek kullanıcı tam yetkili): override/geri alma/erken
  kapatma GEREKÇE ile herkese açık (gerekçe zorunluluğu korunur — olay kaydı
  `is_override` + `override_reason` izini taşımaya devam eder).
- `petitioner_parent` yolu kalktı: VELI rolü ilgili öğrenci FK'sına bağlanır.
- `assigned_guidance` FK → `assigned_guidance_name` metni (sinyalsiz rehberlik).
- `generate_case_no` AYNEN (aktif ders yılı prefix'i + select_for_update —
  SQLite'ta kilit no-op'tur; tek yazar olduğundan kabul, tasarım §4.2).
"""

from __future__ import annotations

import re
from datetime import date

from django.db import transaction
from django.utils import timezone

from apps.disiplin.models import (
    CaseStage,
    DisciplineAttachment,
    DisciplineCase,
    DisciplineCaseStudent,
    DisciplineDecision,
    DisciplineDecisionType,
    DisciplineEvent,
    PetitionerRole,
    PrincipalDecision,
)
from apps.disiplin.services.participants import ensure_accused_participant
from apps.disiplin.state_machine import InvalidTransitionError, validate_transition
from apps.okul import selectors as okul_selectors


def generate_case_no() -> str:
    """Sıradaki dosya no: '{ders yılı adı}-{4 haneli sıra}' (örn. 2025-2026-0001).

    Numara AKTİF ders yılına bağlıdır; eski biçimli numaralar regex filtresiyle
    izole edilir. Soft-delete edilmiş kayıtlar da sırayı tükettiğinden (case_no
    UNIQUE) `all_objects` üzerinden bakılır. Transaction içinde (create_case)
    çağrılmalıdır.
    """
    year = okul_selectors.active_school_year()
    if year is None:
        raise ValueError(
            "Aktif ders yılı bulunamadı; disiplin dosyası açmak için önce "
            "Ayarlar'dan bir ders yılını etkinleştirin."
        )
    prefix = f"{year.name}-"
    last = (
        DisciplineCase.all_objects.select_for_update()
        .filter(case_no__regex=rf"^{re.escape(prefix)}\d{{4}}$")
        .order_by("-case_no")
        .first()
    )
    seq = (int(last.case_no.rsplit("-", 1)[1]) + 1) if last else 1
    return f"{prefix}{seq:04d}"


@transaction.atomic
def create_case(
    *,
    petition_date: date,
    petitioner_name: str,
    petitioner_role: str,
    summary: str,
    student_ids: list[int],
    petitioner_user_id: int | None = None,
    petitioner_student_id: int | None = None,
) -> DisciplineCase:
    """Yeni disiplin dosyası açar (None → PETITION genesis aşaması).

    En az bir geçerli öğrenci zorunludur. İlk aşama (PETITION) bir DisciplineEvent
    olarak kaydedilir; her suçlanan öğrenci için ACCUSED katılımcı senkron kurulur.
    """
    students = []
    for sid in dict.fromkeys(student_ids):  # sırayı koru + yinelenenleri ele
        student = okul_selectors.get_student(sid)
        if student is not None:
            students.append(student)
    if not students:
        raise ValueError("En az bir geçerli öğrenci belirtilmelidir.")

    p_user = None
    p_student = None
    if petitioner_user_id is not None:
        p_user = okul_selectors.get_personnel(petitioner_user_id)
        if p_user is None:
            raise ValueError("Belirtilen personel bulunamadı (petitioner_user_id).")
        if not petitioner_name.strip():
            petitioner_name = p_user.full_name
    if petitioner_student_id is not None:
        p_student = okul_selectors.get_student(petitioner_student_id)
        if p_student is None:
            raise ValueError("Belirtilen öğrenci bulunamadı (petitioner_student_id).")
        if not petitioner_name.strip():
            petitioner_name = p_student.full_name or "(isimsiz öğrenci)"

    case = DisciplineCase(
        case_no=generate_case_no(),
        petition_date=petition_date,
        petitioner_name=petitioner_name,
        petitioner_role=petitioner_role,
        petitioner_user=p_user,
        petitioner_student=p_student,
        summary=summary,
        current_stage=CaseStage.PETITION,
    )
    # clean() — petitioner_role ↔ FK tutarlılığı doğrulaması.
    case.full_clean(exclude=["case_no", "current_stage", "closed_at"])
    case.save()
    for student in students:
        DisciplineCaseStudent.objects.create(case=case, student=student)
        # Suçlanan roster'ı — ifade/evrak katılımcıdan üretilir.
        ensure_accused_participant(case, student)

    event = DisciplineEvent(
        case=case,
        stage=CaseStage.PETITION,
        event_date=petition_date,
        notes="Dilekçe alındı.",
    )
    event.full_clean()
    event.save()
    return case


@transaction.atomic
def add_event(
    case: DisciplineCase,
    stage: str,
    event_date: date,
    *,
    override: bool = False,
    override_reason: str = "",
    assigned_guidance_name: str = "",
    notes: str = "",
    guidance_outcome: str | None = None,
    principal_decisions: list[str] | None = None,
    committee_decision_type: DisciplineDecisionType | None = None,
    committee_decision_text: str | None = None,
) -> DisciplineEvent:
    """Sürece yeni bir aşama olayı ekler ve durum makinesini ilerletir.

    Geçiş geçersizse: `override=True` + zorunlu gerekçe ile delinir (olay
    `is_override` iziyle kaydedilir); değilse InvalidTransitionError.
    """
    current = case.current_stage
    is_override = False
    try:
        validate_transition(current, stage)
    except InvalidTransitionError as exc:
        if not override:
            raise
        if not (override_reason or "").strip():
            raise ValueError("Override işleminde gerekçe (override_reason) zorunludur.") from exc
        is_override = True

    event = DisciplineEvent(
        case=case,
        stage=stage,
        event_date=event_date,
        notes=notes,
        assigned_guidance_name=(assigned_guidance_name or "").strip(),
        guidance_outcome=guidance_outcome or "",
        principal_decisions=principal_decisions,
        committee_decision_type=committee_decision_type,
        committee_decision_text=committee_decision_text or "",
        is_override=is_override,
        override_reason=override_reason if is_override else "",
    )
    event.full_clean()
    event.save()

    # Otomatik kapanma kuralı: DECIDED yalnızca yazılı uyarı (kurula sevk yok) →
    # süreç biter → CLOSED. COMMITTEE_DONE otomatik KAPANMAZ — dosya orada dinlenir
    # (tebliğ + itiraz penceresi); gerçek kapanış close_case iledir.
    final_stage = stage
    if stage == CaseStage.DECIDED:
        committee_needed = any(
            d in (PrincipalDecision.HONOR_COMMITTEE, PrincipalDecision.DISCIPLINE_COMMITTEE)
            for d in (principal_decisions or [])
        )
        if not committee_needed:
            final_stage = CaseStage.CLOSED

    case.current_stage = final_stage
    update_fields = ["current_stage", "updated_at"]
    if final_stage == CaseStage.CLOSED:
        case.closed_at = timezone.now()
        update_fields.append("closed_at")
    case.save(update_fields=update_fields)
    return event


@transaction.atomic
def update_guidance_assignee(case: DisciplineCase, *, name: str) -> bool:
    """Dosyanın EN GÜNCEL rehberlik sevk olayındaki rehber adını günceller.

    Yeni bir aşama olayı ÜRETİLMEZ (durum makinesi GUIDANCE_REFERRED'de kalır;
    tarihçe yalın). İlgili olay yoksa False döner (idempotent).
    """
    event = (
        case.events.filter(stage=CaseStage.GUIDANCE_REFERRED)
        .order_by("-recorded_at", "-id")
        .first()
    )
    if event is None:
        return False
    cleaned = (name or "").strip()
    if event.assigned_guidance_name == cleaned:
        return False  # değişiklik yok
    event.assigned_guidance_name = cleaned
    event.save(update_fields=["assigned_guidance_name", "updated_at"])
    return True


# Aşama sırası ("daha erken" karşılaştırması; geri alma).
_STAGE_ORDER: list[str] = [
    CaseStage.PETITION,
    CaseStage.GUIDANCE_REFERRED,
    CaseStage.GUIDANCE_RETURNED,
    CaseStage.DECIDED,
    CaseStage.COMMITTEE_DONE,
    CaseStage.CLOSED,
]


@transaction.atomic
def revert_stage(case: DisciplineCase, *, target_stage: str, reason: str) -> DisciplineCase:
    """Dosyayı seçilen daha ERKEN bir aşamaya geri alır (zorunlu gerekçe).

    ORPHAN KORUMASI: karar aşaması (DECIDED) öncesine geri almak, dosyada
    (silinmemiş) resmî karar varsa engellenir — önce kararı silin (geri alınabilir).
    closed_at temizlenir. DisciplineEvent OLUŞTURULMAZ (aşamaya-özel doğrulamaya
    takılmamak + timeline ileri-yön geçmişini bozmamak için).
    """
    reason = (reason or "").strip()
    if not reason:
        raise ValueError("Aşama geri alma için gerekçe zorunludur.")
    if target_stage not in set(CaseStage.values):
        raise ValueError("Geçersiz hedef aşama.")
    current = case.current_stage
    if _STAGE_ORDER.index(target_stage) >= _STAGE_ORDER.index(current):
        raise ValueError("Hedef aşama mevcut aşamadan önceki bir aşama olmalıdır.")
    if (
        _STAGE_ORDER.index(target_stage) < _STAGE_ORDER.index(CaseStage.DECIDED)
        and DisciplineDecision.objects.filter(case=case).exists()
    ):
        raise ValueError(
            "Bu dosyada resmî karar var; karar aşaması öncesine geri almak için önce kararı "
            "silin (geri alınabilir)."
        )

    case.current_stage = target_stage
    update_fields = ["current_stage", "updated_at"]
    if case.closed_at is not None:
        case.closed_at = None
        update_fields.append("closed_at")
    case.save(update_fields=update_fields)
    return case


@transaction.atomic
def close_case(
    case: DisciplineCase,
    *,
    override: bool = False,
    override_reason: str = "",
) -> DisciplineCase:
    """Disiplin dosyasını ELLE kapatır.

    Kurula sevk edilen (Dal B) dosyalar COMMITTEE_DONE'da DİNLENİR (otomatik
    kapanmaz); gerçek kapanış kararın kesinleşmesine bağlıdır (md. 169). Uygunluk
    `selectors.close_eligible` ile hesaplanır: tebliğ + 5 iş günü itiraz süresi +
    5 iş günü tampon (itirazsız) ya da itiraz sonucunun kesinleşmesi. Erken
    kapatma yalnız GEREKÇE (override) ile mümkündür.
    """
    from apps.disiplin import selectors

    if case.current_stage == CaseStage.CLOSED:
        raise ValueError("Dosya zaten kapalı.")

    if override:
        if not (override_reason or "").strip():
            raise ValueError("Erken kapatma için gerekçe (override_reason) zorunludur.")
    else:
        eligible, eligible_on, reason = selectors.close_eligibility_details(case)
        if not eligible:
            if eligible_on is not None:
                raise ValueError(
                    "Dosya henüz kapatılamaz; itiraz süresi + tampon dolmadı "
                    f"(en erken {eligible_on:%d.%m.%Y}). Erken kapatma gerekçe gerektirir."
                )
            raise ValueError(f"Dosya henüz kapatılamaz; {reason} Erken kapatma gerekçe gerektirir.")

    current = case.current_stage
    # Durum makinesi: COMMITTEE_DONE/DECIDED → CLOSED geçerli geçiştir.
    validate_transition(current, CaseStage.CLOSED)
    case.current_stage = CaseStage.CLOSED
    case.closed_at = timezone.now()
    case.save(update_fields=["current_stage", "closed_at", "updated_at"])
    return case


@transaction.atomic
def add_attachment(
    *,
    case: DisciplineCase,
    file_bytes: bytes,
    original_filename: str,
    file_type: str,
    event: DisciplineEvent | None = None,
) -> tuple[DisciplineAttachment, bool]:
    """Dosya ekini doğrular, diske yazar ve DisciplineAttachment kaydı üretir.

    Döner: (attachment, is_duplicate). `is_duplicate`, aynı dosyanın (SHA256) bu
    case'e daha önce yüklendiğini gösterir — kayıt yine de oluşturulur (uyarı UI'da).
    Geçersiz MIME/boyut `file_storage.FileValidationError` yükseltir (diske yazılmaz).
    """
    from apps.disiplin import file_storage

    stored = file_storage.save_attachment(case_id=case.pk, file_bytes=file_bytes)
    is_duplicate = DisciplineAttachment.objects.filter(case=case, sha256=stored.sha256).exists()

    attachment = DisciplineAttachment.objects.create(
        case=case,
        event=event,
        file_path=stored.file_path,
        original_filename=original_filename,
        file_type=file_type,
        file_size_bytes=stored.file_size_bytes,
        mime_type=stored.mime_type,
        sha256=stored.sha256,
    )
    return attachment, is_duplicate


@transaction.atomic
def update_case(
    case: DisciplineCase,
    *,
    summary: str | None = None,
    petitioner_name: str | None = None,
    petitioner_role: str | None = None,
    petition_date: date | None = None,
) -> DisciplineCase:
    """Dosyanın düzeltilebilir künye alanlarını günceller (kapalı dosyada yasak)."""
    if case.closed_at is not None:
        raise ValueError("Dosya kapatılmış; künye alanları güncellenemez.")
    if petitioner_role is not None and petitioner_role not in set(PetitionerRole.values):
        raise ValueError("Geçersiz dilekçe veren rolü.")
    fields: list[str] = []
    if petitioner_role is not None:
        case.petitioner_role = petitioner_role
        fields.append("petitioner_role")
    if summary is not None:
        case.summary = summary
        fields.append("summary")
    if petitioner_name is not None:
        case.petitioner_name = petitioner_name
        fields.append("petitioner_name")
    if petition_date is not None:
        case.petition_date = petition_date
        fields.append("petition_date")
    if fields:
        case.save(update_fields=[*fields, "updated_at"])
    return case


@transaction.atomic
def delete_attachment(attachment: DisciplineAttachment) -> None:
    """Dosya ekini soft-delete eder (fiziksel dosya imha aracına kadar diskte kalır)."""
    attachment.delete()
