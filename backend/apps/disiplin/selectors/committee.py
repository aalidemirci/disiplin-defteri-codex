"""Disiplin kurulu + karar defteri + onur kurulu salt-okunur sorguları.

OYS `selectors/discipline_committee.py` + `council_meeting.py` + `honors.py`'den
YALINLAŞTIRILDI: rol/yetki fonksiyonları (`can_manage_council_meeting`,
`guidance_counselors`…) silindi — tek kullanıcı her kaydı görür/yönetir.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from django.db.models import Exists, OuterRef, Q, QuerySet
from django.utils import timezone

from apps.disiplin.discipline_periods import BEHAVIOR_POINT_START
from apps.disiplin.models import (
    AgendaItemOutcome,
    CouncilAgendaItem,
    CouncilMeeting,
    CouncilType,
    DisciplineCase,
    DisciplineCommittee,
    DisciplineCommitteeMember,
    DisciplineDecision,
    DisciplineEvent,
    DisciplineMeeting,
    HonorBoard,
    HonorBoardMember,
    HonorCertificate,
    HonorCertificateStatus,
    HonorGeneralAssemblyMember,
    HonorMeetingKind,
)
from apps.okul import selectors as okul_selectors


def get_active_committee() -> DisciplineCommittee | None:
    """Aktif ders yılının disiplin kurulu (silinmemiş) — yoksa None (üyeler önceden)."""
    year = okul_selectors.active_school_year()
    if year is None:
        return None
    return DisciplineCommittee.objects.filter(school_year=year).prefetch_related("members").first()


def committee_for_case(case: DisciplineCase) -> DisciplineCommittee | None:
    """Dosyayı görüşen kurul: kurula sevk (yoksa dilekçe) tarihinin ders yılının kurulu.

    md. 185/4: kurulun görevi yeni kurul oluşuncaya kadar sürer. Yıl devrinden
    sonra eski yılın dosyasının evrakı YENİ yılın kurulunu basmamalı; o yılın
    kurulu yoksa (henüz kurulmamışsa) aktif kurula, o da yoksa en son kurula düşülür.
    """
    from apps.disiplin.selectors.precautions import committee_referred_on

    anchor = committee_referred_on(case) or case.petition_date
    qs = DisciplineCommittee.objects.prefetch_related("members")
    own: DisciplineCommittee | None = qs.filter(
        school_year__start_date__lte=anchor, school_year__end_date__gte=anchor
    ).first()
    if own is not None:
        return own
    fallback: DisciplineCommittee | None = (
        get_active_committee() or qs.order_by("-school_year__start_date").first()
    )
    return fallback


def get_committee(committee_id: int) -> DisciplineCommittee | None:
    """Tek kurul (id ile, silinmemiş) — üyeleriyle birlikte. Yoksa None."""
    return DisciplineCommittee.objects.filter(pk=committee_id).prefetch_related("members").first()


def committee_members(committee: DisciplineCommittee) -> QuerySet[DisciplineCommitteeMember]:
    """Kurulun üyeleri (asıl önce, sonra yedek; sıraya göre)."""
    return committee.members.all()


def get_committee_member(
    committee: DisciplineCommittee, member_id: int
) -> DisciplineCommitteeMember | None:
    """Belirli kurula ait tek üye (silinmemiş) — yoksa None."""
    return DisciplineCommitteeMember.objects.filter(committee=committee, pk=member_id).first()


def committee_composition_warnings(committee: DisciplineCommittee) -> list[str]:
    """Kurul bileşiminin md. 185/1'e uymayan yanları — UYARI metinleri (engel değil).

    Kullanıcı kararı, 14.11.2026 — S5: bileşim denetlenir ama kayıt/toplantı engellenmez;
    neyin eksik/fazla olduğu somut söylenir. md. 185/1: kurul a) müdürün görevlendireceği
    müdür yardımcısı, b) öğretmenler kurulunca gizli oyla seçilecek İKİ öğretmen, c) onur
    kurulu ikinci başkanı, ç) okul-aile birliğinin kendi üyeleri arasından seçeceği BİR
    öğrenci velisinden oluşur. Yalnız ASIL üyeler sayılır (yedekler md. 186).

    Modelden ayırt edilebilenler denetlenir: asıl üye tipi sayıları (öğretmen/öğrenci/veli)
    ve öğrenci üyenin o ders yılının Onur Kurulunda görevdeki asıl ikinci başkan olması.
    Denetlenemeyenler (şema sınırı): başkanın müdür yardımcısı olması (`Personnel.title`
    serbest metin), öğretmenlerin öğretmenler kurulunca seçilmiş olması ve velinin
    okul-aile birliği üyeliği (veli üye yalnız ad snapshot'ı).
    """
    from apps.disiplin.models import CommitteeMemberType

    # Doğrudan sorgu: `committee.members.all()` prefetch önbelleğinden bayat liste
    # verebilir (§7.5 — üye eklendikten/çıkarıldıktan hemen sonraki yanıt).
    members = list(
        DisciplineCommitteeMember.objects.filter(committee=committee, is_substitute=False)
    )
    teachers = [m for m in members if m.member_type == CommitteeMemberType.TEACHER]
    students = [m for m in members if m.member_type == CommitteeMemberType.STUDENT]
    parents = [m for m in members if m.member_type == CommitteeMemberType.PARENT]
    warnings: list[str] = []

    if not teachers:
        warnings.append(
            "Kurul md. 185/1-b'ye göre eksik: öğretmen üye tanımlı değil (öğretmenler "
            "kurulunca seçilen iki öğretmen asıl üyedir)."
        )
    elif len(teachers) == 1:
        warnings.append(
            "Kurul md. 185/1-b'ye göre eksik: öğretmenler kurulunca seçilen iki öğretmen "
            "üyeden yalnız biri tanımlı."
        )
    elif len(teachers) > 2:
        warnings.append(
            f"Kurul md. 185/1-b'ye göre fazla: {len(teachers)} asıl öğretmen üye tanımlı; "
            "asıl öğretmen üye sayısı ikidir."
        )

    if not students:
        warnings.append(
            "Kurul md. 185/1-c'ye göre eksik: onur kurulu ikinci başkanı tanımlı değil."
        )
    elif len(students) > 1:
        warnings.append(
            f"Kurul md. 185/1-c'ye göre fazla: {len(students)} asıl öğrenci üye tanımlı; "
            "öğrenci üye yalnız onur kurulu ikinci başkanıdır."
        )
    second_chair_ids = set(
        HonorBoardMember.objects.filter(
            board__school_year_id=committee.school_year_id,
            board__deleted_at__isnull=True,
            is_second_chair=True,
            is_substitute=False,
            effective_until__isnull=True,
        ).values_list("member_student_id", flat=True)
    )
    for student in students:
        if student.member_student_id not in second_chair_ids:
            warnings.append(
                f"Kurul md. 185/1-c'ye uymuyor: öğrenci üye {student.member_name}, Onur "
                "Kurulunun ikinci başkanı değil."
            )

    if not parents:
        warnings.append(
            "Kurul md. 185/1-ç'ye göre eksik: okul-aile birliği temsilcisi (öğrenci velisi) "
            "tanımlı değil."
        )
    elif len(parents) > 1:
        warnings.append(
            f"Kurul md. 185/1-ç'ye göre fazla: {len(parents)} asıl veli üye tanımlı; "
            "okul-aile birliğinden bir öğrenci velisi asıl üyedir."
        )
    return warnings


def meetings_for_case(case: DisciplineCase) -> QuerySet[DisciplineMeeting]:
    """Bir dosyanın kurul toplantıları (katılan üyeler önceden çekilir)."""
    return case.meetings.prefetch_related("attendees").all()


def get_event_for_case(case: DisciplineCase, event_id: int) -> DisciplineEvent | None:
    """Dosyaya ait tek aşama olayını id ile getirir — yoksa None."""
    return case.events.filter(pk=event_id).first()


def get_meeting_for_case(case: DisciplineCase, meeting_id: int) -> DisciplineMeeting | None:
    """Dosyaya ait tek kurul toplantısını id ile getirir — yoksa None."""
    return case.meetings.filter(pk=meeting_id).first()


# ---------------------------------------------------------------------------
# Karar defteri (CouncilMeeting)
# ---------------------------------------------------------------------------
def list_council_meetings(
    *, council_type: str | None = None, school_year_id: int | None = None
) -> QuerySet[CouncilMeeting]:
    """Kurul toplantı tutanakları (karar defteri) — katılımcılar önceden çekilir."""
    qs = (
        CouncilMeeting.objects.select_related("discipline_case", "school_term")
        .prefetch_related("attendees", "agenda_items__honor_certificate__student")
        .all()
    )
    if council_type in CouncilType.values:
        qs = qs.filter(council_type=council_type)
    if school_year_id is not None:
        qs = qs.filter(school_year_id=school_year_id)
    return qs


def get_council_meeting(meeting_id: int) -> CouncilMeeting | None:
    """Tek kurul toplantı tutanağı (id ile, silinmemiş) — katılımcılarıyla. Yoksa None."""
    return (
        CouncilMeeting.objects.filter(pk=meeting_id)
        .select_related("discipline_case", "school_term")
        .prefetch_related("attendees", "agenda_items__honor_certificate__student")
        .first()
    )


def committee_cases_for_minutes() -> QuerySet[DisciplineCase]:
    """Dosya görüşme tutanağına bağlanabilecek dosyalar.

    Kurula sevkli ve en az bir canlı resmî kararı olan dosyalar — CLOSED dahil
    (tutanak karar sonrası da yazılabilir). SQLite JSON contains kısıtı gereği
    sevk kontrolü Python'da yapılır (selectors.precautions deseni).
    """
    from apps.disiplin.models import CaseStage
    from apps.disiplin.selectors.precautions import committee_referred_on

    alive_decision = DisciplineDecision.objects.filter(case=OuterRef("pk"))
    candidates = (
        DisciplineCase.objects.filter(events__stage=CaseStage.DECIDED)
        .filter(Exists(alive_decision))
        .distinct()
        .prefetch_related("case_students__student", "decisions")
        .order_by("-case_no")
    )
    referred_ids = [c.pk for c in candidates if committee_referred_on(c) is not None]
    return (
        DisciplineCase.objects.filter(pk__in=referred_ids)
        .prefetch_related("case_students__student", "decisions")
        .order_by("-case_no")
    )


# ---------------------------------------------------------------------------
# Onur kurulu + onur belgesi (honors-lite)
# ---------------------------------------------------------------------------
def get_active_honor_board() -> HonorBoard | None:
    """Aktif ders yılının onur kurulu (silinmemiş) — yoksa None (üyeler önceden)."""
    year = okul_selectors.active_school_year()
    if year is None:
        return None
    return HonorBoard.objects.filter(school_year=year).prefetch_related("members").first()


def get_honor_board(board_id: int) -> HonorBoard | None:
    """Tek onur kurulu (id ile, silinmemiş) — üyeleriyle birlikte. Yoksa None."""
    return HonorBoard.objects.filter(pk=board_id).prefetch_related("members").first()


def get_honor_board_member(board: HonorBoard, member_id: int) -> HonorBoardMember | None:
    """Belirli onur kuruluna ait tek üye (silinmemiş) — yoksa None."""
    return HonorBoardMember.objects.filter(board=board, pk=member_id).first()


def assembly_members_in_office(
    qs: QuerySet[HonorGeneralAssemblyMember], on: date | None = None
) -> QuerySet[HonorGeneralAssemblyMember]:
    """Verilen gün (varsayılan bugün) GÖREVDE olan temsilciler (md. 178/1).

    Görevde = görev başlamış ve bitmemiş. "Bitiş tarihi boş" ölçütü yetmez: ileri
    tarihli temsilci değişikliğinde eski temsilcinin bitişi önceden yazılır ama dönem
    başına dek görevdedir; yeni temsilcinin bitişi boştur ama henüz göreve başlamamıştır.
    """
    day = on or timezone.localdate()
    return qs.filter(effective_from__lte=day).filter(
        Q(effective_until__isnull=True) | Q(effective_until__gte=day)
    )


def is_assembly_member_in_office(
    member: HonorGeneralAssemblyMember, on: date | None = None
) -> bool:
    """Temsilci verilen gün (varsayılan bugün) görevde mi — `assembly_members_in_office` eşi."""
    day = on or timezone.localdate()
    return member.effective_from <= day and (
        member.effective_until is None or member.effective_until >= day
    )


def honor_general_assembly_members(
    *, school_year_id: int, active_only: bool = False
) -> QuerySet[HonorGeneralAssemblyMember]:
    qs = HonorGeneralAssemblyMember.objects.select_related(
        "member_student", "school_year", "replaced_member"
    ).filter(school_year_id=school_year_id)
    if active_only:
        qs = assembly_members_in_office(qs)
    return qs


def get_honor_general_assembly_member(
    member_id: int,
) -> HonorGeneralAssemblyMember | None:
    return HonorGeneralAssemblyMember.objects.filter(pk=member_id).first()


def honor_compliance_status(school_year_id: int) -> dict[str, object]:
    """Dönemlik genel kurul ve aylık Onur Kurulu toplantı uygunluğu."""

    from apps.okul.models import SchoolTerm

    terms = list(SchoolTerm.objects.filter(school_year_id=school_year_id))
    month_names = (
        "",
        "Ocak",
        "Şubat",
        "Mart",
        "Nisan",
        "Mayıs",
        "Haziran",
        "Temmuz",
        "Ağustos",
        "Eylül",
        "Ekim",
        "Kasım",
        "Aralık",
    )
    meetings = CouncilMeeting.objects.filter(
        school_year_id=school_year_id,
        council_type=CouncilType.HONOR,
    )
    rows: list[dict[str, object]] = []
    for term in terms:
        assembly_count = meetings.filter(
            school_term=term,
            honor_meeting_kind=HonorMeetingKind.GENERAL_ASSEMBLY,
        ).count()
        cursor = date(term.start_date.year, term.start_date.month, 1)
        last = date(term.end_date.year, term.end_date.month, 1)
        months: list[dict[str, object]] = []
        while cursor <= last:
            count = meetings.filter(
                school_term=term,
                honor_meeting_kind=HonorMeetingKind.BOARD,
                meeting_date__year=cursor.year,
                meeting_date__month=cursor.month,
            ).count()
            months.append(
                {
                    "year": cursor.year,
                    "month": cursor.month,
                    "label": f"{month_names[cursor.month]} {cursor.year}",
                    "meeting_count": count,
                    "complete": count > 0,
                }
            )
            cursor = (
                date(cursor.year + 1, 1, 1)
                if cursor.month == 12
                else date(cursor.year, cursor.month + 1, 1)
            )
        rows.append(
            {
                "term_id": term.pk,
                "sequence": term.sequence,
                "name": term.name,
                "assembly_meeting_count": assembly_count,
                "assembly_complete": assembly_count > 0,
                "months": months,
            }
        )
    return {"configured": len(terms) == 2, "terms": rows}


def honor_certificates(
    *,
    status: str = "",
    school_year_id: int | None = None,
    school_term_id: int | None = None,
    student_id: int | None = None,
) -> QuerySet[HonorCertificate]:
    """Onur belgeleri (öğrenci + yıl önceden çekilir) — durum/yıl/öğrenci filtreli."""
    qs = HonorCertificate.objects.select_related("student", "school_year", "school_term").all()
    if status.strip():
        qs = qs.filter(status=status.strip())
    if school_year_id is not None:
        qs = qs.filter(school_year_id=school_year_id)
    if school_term_id is not None:
        qs = qs.filter(school_term_id=school_term_id)
    if student_id is not None:
        qs = qs.filter(student_id=student_id)
    return qs


def get_honor_certificate(certificate_id: int) -> HonorCertificate | None:
    """Tek onur belgesi (id ile, silinmemiş) — yoksa None."""
    return (
        HonorCertificate.objects.select_related("student", "school_year", "school_term")
        .filter(pk=certificate_id)
        .first()
    )


def is_eligible_for_honor(student_id: int, school_year_id: int | None = None) -> bool:
    """Öğrenci onur belgesine uygun mu (md. 161): davranış puanı İNDİRİLMEMİŞ olmalı."""
    from apps.disiplin.selectors.decisions import behavior_point_for_student

    return behavior_point_for_student(student_id, school_year_id) >= BEHAVIOR_POINT_START


def honor_list_for_year(school_year_id: int) -> list[int]:
    """Yılın onur listesi (md. 161/2): 2+ AWARDED belgeli öğrenci id'leri — türetilir.

    Saklanmaz; belge sayısına göre hesaplanır (OYS `honor_list_for_year` paritesi).
    """
    counts: dict[int, int] = {}
    qs = HonorCertificate.objects.filter(
        school_year_id=school_year_id, status=HonorCertificateStatus.AWARDED
    ).values_list("student_id", flat=True)
    for sid in qs:
        counts[sid] = counts.get(sid, 0) + 1
    return sorted(sid for sid, n in counts.items() if n >= 2)


# ---------------------------------------------------------------------------
# Kurul gündemi + müdür onayı (04.10.2026, kurul işleyişi Aşama 1)
# ---------------------------------------------------------------------------
def get_agenda_item(meeting_id: int, item_id: int) -> CouncilAgendaItem | None:
    """Toplantının tek gündem maddesi (silinmemiş) — yoksa None."""
    return (
        CouncilAgendaItem.objects.select_related(
            "meeting", "meeting__discipline_committee", "honor_certificate__student"
        )
        .filter(pk=item_id, meeting_id=meeting_id, meeting__deleted_at__isnull=True)
        .first()
    )


def honor_agenda_candidates(
    *, council_type: str, school_year_id: int
) -> QuerySet[HonorCertificate]:
    """Kurul gündemine alınmayı bekleyen onur belgesi teklifleri.

    Onur Kurulu: teklif aşamasındakiler (md. 161/1 → 183/b). Ödül ve Disiplin Kurulu:
    Onur Kurulunca uygun görülenler (md. 161/1). Bir toplantıda karar bekleyenler hariç.
    """
    statuses: dict[str, str] = {
        CouncilType.HONOR: HonorCertificateStatus.PROPOSED,
        CouncilType.DISCIPLINE: HonorCertificateStatus.HONOR_BOARD_RECOMMENDED,
    }
    status = statuses.get(council_type)
    if status is None:
        return HonorCertificate.objects.none()
    pending = CouncilAgendaItem.objects.filter(
        honor_certificate=OuterRef("pk"), outcome=AgendaItemOutcome.PENDING
    )
    return (
        HonorCertificate.objects.select_related("student", "school_term")
        .filter(school_year_id=school_year_id, status=status)
        .exclude(Exists(pending))
        .order_by("school_term__sequence", "created_at")
    )


def principal_pending(school_year_id: int | None = None) -> dict[str, list[Any]]:
    """Okul müdürünün onayını bekleyen kurul kararları (Panel kartı).

    - Onur belgesi: Ödül ve Disiplin Kurulunca kabul edilmiş (AWARDED) teklifler.
    - Disiplin: onay mercii okul müdürü olan, onay bekleyen kurul kararları (md. 163/2).
      Üst merci (ilçe/il) onayındaki kararlar müdür onayı değildir, listelenmez.
    """
    from apps.disiplin.models import ApprovalAuthority, DecisionApprovalStatus

    certificates = HonorCertificate.objects.select_related("student").filter(
        status=HonorCertificateStatus.AWARDED
    )
    if school_year_id is not None:
        certificates = certificates.filter(school_year_id=school_year_id)
    decisions = (
        DisciplineDecision.objects.select_related("student", "case")
        .filter(
            approval_status=DecisionApprovalStatus.PENDING,
            approval_authority=ApprovalAuthority.PRINCIPAL,
            case__deleted_at__isnull=True,
        )
        .order_by("decision_date", "id")
    )
    return {
        "honor_certificates": list(certificates.order_by("awarded_at", "id")),
        "decisions": list(decisions),
    }
