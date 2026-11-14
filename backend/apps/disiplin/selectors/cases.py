"""Disiplin dosyası salt-okunur sorguları.

OYS `selectors/discipline_cases.py`'den YALINLAŞTIRILDI: rol/görünürlük
fonksiyonları silindi (tek kullanıcı her dosyayı görür) — `cases_for_user`
yerine `all_cases()` (aşama/arama filtreli).
"""

from __future__ import annotations

from django.db.models import QuerySet

from apps.disiplin.models import (
    DecisionApprovalStatus,
    DisciplineAttachment,
    DisciplineCase,
    DisciplineDecision,
    DisciplineDecisionType,
    DisciplineEvent,
)


def latest_principal_decision_event(
    case: DisciplineCase, *, include_deleted: bool = False
) -> DisciplineEvent | None:
    """Dosyanın EN SON KAYDEDİLEN müdür kararı (DECIDED) olayı — "son karar"ın TEK ölçütü.

    Sıra kayıt sırasıdır (`-recorded_at, -id`), olay TARİHİ değil: `revert_stage` olay
    silmez ve geri alınıp yeniden verilen karar daha ERKEN bir tarihle girilebilir
    (`_assert_event_date_in_order` geri alınmış olayın tarihini bağlamaz). Olay tarihine
    göre sıralansaydı geri alınmış, yanlış (daha geç) tarihli sevk "geçerli" sayılırdı.
    Evrak tarafı (`documents.py`) aynı ölçütü kullanır.

    Güncel aşamaya BAKMAZ — "karar aşaması geri alınmış mı" denetimi çağıranındır
    (`committee_referred_on`, `services.participants._current_principal_decisions`).
    `include_deleted`: imha aracı için soft-delete edilmiş olaylar dahil.
    """
    from apps.disiplin.models import CaseStage

    manager = DisciplineEvent.all_objects if include_deleted else DisciplineEvent.objects
    event: DisciplineEvent | None = (
        manager.filter(case_id=case.pk, stage=CaseStage.DECIDED)
        .order_by("-recorded_at", "-id")
        .first()
    )
    return event


def decision_types(*, active_only: bool = True) -> QuerySet[DisciplineDecisionType]:
    """Disiplin karar tipleri (lookup). Varsayılan: yalnızca aktif olanlar."""
    qs = DisciplineDecisionType.objects.all()
    if active_only:
        qs = qs.filter(is_active=True)
    return qs


def get_decision_type(decision_type_id: int) -> DisciplineDecisionType | None:
    """Tek karar tipini id ile getirir — yoksa None."""
    return DisciplineDecisionType.objects.filter(pk=decision_type_id).first()


def get_case(case_id: int) -> DisciplineCase | None:
    """Tek disiplin dosyası (canlı) — ilişkili öğrenci/olay/ek önceden çekilir."""
    return (
        DisciplineCase.objects.filter(pk=case_id)
        .prefetch_related("case_students__student", "events", "attachments")
        .first()
    )


def get_attachment(case: DisciplineCase, attachment_id: int) -> DisciplineAttachment | None:
    """Belirli dosyaya ait tek eki getirir (canlı) — yoksa None."""
    return DisciplineAttachment.objects.filter(case=case, pk=attachment_id).first()


def case_student_ids(case: DisciplineCase) -> set[int]:
    """Dosyadaki öğrenci id'leri."""
    return set(case.case_students.values_list("student_id", flat=True))


def all_cases(*, stage: str = "", search: str = "") -> QuerySet[DisciplineCase]:
    """Tüm (canlı) disiplin dosyaları — aşama ve dosya-no/dilekçe araması filtreli."""
    qs = DisciplineCase.objects.all()
    if stage.strip():
        qs = qs.filter(current_stage=stage.strip())
    if search.strip():
        # SQLite LIKE yalnız ASCII'de harf duyarsızdır ("şükrü" ≠ "Şükrü"); öğrenci/
        # personel aramasıyla aynı Türkçe katlama Python tarafında yapılır (≤1000 kayıt).
        from apps.okul.excel_veli import normalize_header

        needle = normalize_header(search)
        matched = [
            pk
            for pk, case_no, petitioner in qs.values_list("pk", "case_no", "petitioner_name")
            if needle in normalize_header(case_no) or needle in normalize_header(petitioner)
        ]
        qs = qs.filter(pk__in=matched)
    return qs.distinct()


def open_cases_for_close_scan() -> QuerySet[DisciplineCase]:
    """Kapanış taramasına giren açık dosyalar (karar/kurul aşamasını geçmiş).

    "Yaklaşan Süreler" paneli 5. bölümü bunu okur.
    """
    from apps.disiplin.models import CaseStage

    return DisciplineCase.objects.filter(
        closed_at__isnull=True,
        current_stage__in=[CaseStage.DECIDED, CaseStage.COMMITTEE_DONE],
    )


def decisions_in_md197_review() -> QuerySet[DisciplineDecision]:
    """md. 197 askısındaki kararlar: kurula iade edilmiş ya da ilçe kuruluna gönderilmiş.

    Bu kararlar ne "onay bekliyor" ne "tebliğ bekliyor" listesine girer; panelde hiç
    görünmezse açık dosya unutulur (kapatılamaz da). Yalnız BİLGİ satırı — md. 197'deki
    5 iş günlük gönderme süresi kurulun ısrar tarihinden işler, o tarih kayıtlı değildir
    (borç M9).
    """
    return (
        DisciplineDecision.objects.filter(
            approval_status__in=[
                DecisionApprovalStatus.RETURNED_TO_COMMITTEE,
                DecisionApprovalStatus.REFERRED_TO_DISTRICT,
            ],
            case__closed_at__isnull=True,
        )
        .select_related("case", "student")
        .order_by("case__case_no", "pk")
    )


def cases_for_student(student_id: int) -> QuerySet[DisciplineCase]:
    """Belirli öğrencinin disiplin dosyaları (sicil ekranı için)."""
    return DisciplineCase.objects.filter(case_students__student_id=student_id).distinct()
