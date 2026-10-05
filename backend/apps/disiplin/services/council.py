"""Kurul toplantı tutanağı / karar defteri yönetimi — md. 184/206.

OYS `services/council_meeting.py`'den temizlenerek taşındı: audit + kullanıcı
parametreleri + `member_parent_id` silindi (veli katılımcı yalnız ad snapshot).
Defter numarası + katılımcı doğrulama kuralları AYNEN.

Gündem maddeleri (04.10.2026, kurul işleyişi Aşama 1): kurul toplanır → teklif
gündeme alınır → madde toplantıda karara bağlanır → karar defteri maddelerden
derlenir. Onur belgesi teklifine ilişkin kurul kararı başka yoldan verilemez.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from django.db import transaction

from apps.disiplin.models import (
    AgendaItemOutcome,
    AgendaItemType,
    CouncilAgendaItem,
    CouncilAttendeeRole,
    CouncilDecisionBasis,
    CouncilMeeting,
    CouncilMeetingAttendee,
    CouncilMinutesType,
    CouncilType,
    DisciplineCase,
    DisciplineCommittee,
    HonorCertificate,
    HonorCertificateStatus,
    HonorMeetingKind,
)
from apps.okul import selectors as okul_selectors


def _resolve_case_for_minutes(discipline_case_id: int) -> DisciplineCase:
    """CASE_REVIEW tutanağı için dosyayı doğrular: var + kurula sevkli + kararlı.

    Kararlar tutanağa render anında DisciplineDecision'dan derlenir; bu yüzden
    dosyada en az bir canlı resmî karar bulunmalıdır.
    """
    from apps.disiplin import selectors

    case = selectors.get_case(discipline_case_id)
    if case is None:
        raise ValueError("Disiplin dosyası bulunamadı.")
    if selectors.committee_referred_on(case) is None:
        raise ValueError("Dosya disiplin kuruluna sevk edilmemiş.")
    if not case.decisions.exists():
        raise ValueError("Dosyada kayıtlı resmî karar yok; önce kurul kararlarını girin.")
    return case


def _validate_attendees(attendees: list[dict[str, Any]]) -> None:
    """Katılımcı listesini doğrular: ≥1 oy hakkı olan üye + tam 1 başkan (md. 188/191)."""
    if not attendees:
        raise ValueError("En az bir katılımcı eklenmelidir.")
    voting = [a for a in attendees if a.get("attendee_role") == CouncilAttendeeRole.VOTING_MEMBER]
    if not voting:
        raise ValueError("En az bir oy hakkı olan üye eklenmelidir (md. 191).")
    chairs = [a for a in attendees if a.get("is_chair")]
    if len(chairs) != 1:
        raise ValueError("Tam olarak bir başkan işaretlenmelidir (md. 188).")
    if chairs[0].get("attendee_role") != CouncilAttendeeRole.VOTING_MEMBER:
        raise ValueError("Başkan oy hakkı olan üye olmalıdır.")
    for a in attendees:
        if not str(a.get("person_name", "")).strip():
            raise ValueError("Her katılımcının ad-soyadı zorunludur (tutanak bütünlüğü).")


def _create_attendees(meeting: CouncilMeeting, attendees: list[dict[str, Any]]) -> None:
    """Katılımcı snapshot satırlarını oluşturur (meeting'e bağlı)."""
    for idx, a in enumerate(attendees):
        CouncilMeetingAttendee.objects.create(
            meeting=meeting,
            attendee_role=a.get("attendee_role", CouncilAttendeeRole.VOTING_MEMBER),
            person_name=str(a["person_name"]).strip(),
            title=a.get("title", ""),
            is_chair=bool(a.get("is_chair", False)),
            dissent_note=a.get("dissent_note", ""),
            order=a.get("order", idx),
            member_user_id=a.get("member_user_id"),
            member_student_id=a.get("member_student_id"),
        )


def _resolve_source(council_type: str, honor_meeting_kind: str) -> tuple[Any, Any]:
    """Aktif kurula otomatik izlenebilirlik bağı (DISCIPLINE→kurul, HONOR→onur kurulu)."""
    from apps.disiplin.selectors import get_active_committee, get_active_honor_board

    if council_type == CouncilType.DISCIPLINE:
        return get_active_committee(), None
    if honor_meeting_kind == HonorMeetingKind.GENERAL_ASSEMBLY:
        return None, None
    return None, get_active_honor_board()


@transaction.atomic
def create_council_meeting(
    *,
    school_year_id: int,
    council_type: str,
    meeting_date: date,
    attendees: list[dict[str, Any]],
    agenda: str = "",
    decision_text: str = "",
    decision_basis: str = CouncilDecisionBasis.UNANIMITY,
    notes: str = "",
    minutes_type: str = CouncilMinutesType.GENERAL,
    discipline_case_id: int | None = None,
    honor_meeting_kind: str = HonorMeetingKind.BOARD,
    honor_certificate_ids: list[int] | None = None,
) -> CouncilMeeting:
    """Bir kurulun genel toplantı kararını karar defterine yazar (md. 184/206).

    `meeting_no` ders yılı + kurul türü başına artar (silinmiş kayıtlar dahil —
    defter numarası tekrarlanmaz). CASE_REVIEW: kurula sevkli + kararlı bir
    disiplin dosyası bağlanır; kararlar render anında dosyadan derlenir.
    `honor_certificate_ids` verilirse teklifler gündem maddesi olarak eklenir.
    """
    if council_type not in CouncilType.values:
        raise ValueError("Geçersiz kurul türü.")
    if decision_basis not in CouncilDecisionBasis.values:
        raise ValueError("Geçersiz karar esası.")
    if minutes_type not in CouncilMinutesType.values:
        raise ValueError("Geçersiz tutanak türü.")
    if honor_meeting_kind not in HonorMeetingKind.values:
        raise ValueError("Geçersiz Onur toplantısı türü.")
    if council_type == CouncilType.DISCIPLINE and honor_meeting_kind != HonorMeetingKind.BOARD:
        raise ValueError("Onur toplantısı türü disiplin kurulu tutanağında kullanılamaz.")
    discipline_case: DisciplineCase | None = None
    if minutes_type == CouncilMinutesType.CASE_REVIEW:
        if council_type != CouncilType.DISCIPLINE:
            raise ValueError("Dosya görüşme tutanağı yalnız disiplin kurulunda tutulabilir.")
        if discipline_case_id is None:
            raise ValueError("Dosya görüşme tutanağı için bir disiplin dosyası seçilmelidir.")
        discipline_case = _resolve_case_for_minutes(discipline_case_id)
        if not agenda.strip():
            agenda = f"{discipline_case.case_no} sayılı disiplin dosyasının görüşülmesi"
    elif discipline_case_id is not None:
        raise ValueError("Disiplin dosyası yalnız dosya görüşme tutanağına bağlanabilir.")
    year = okul_selectors.get_school_year(school_year_id)
    if year is None:
        raise ValueError("Ders yılı bulunamadı.")
    school_term = None
    if council_type == CouncilType.HONOR:
        from apps.okul.services.terms import require_term_for_date

        school_term = require_term_for_date(year, meeting_date)
    _validate_attendees(attendees)

    # Defter sırası: (yıl, tür) için en büyük no + 1 (silinmiş dahil; tekrar etmesin).
    last = (
        CouncilMeeting.all_objects.select_for_update()
        .filter(school_year=year, council_type=council_type)
        .order_by("-meeting_no")
        .first()
    )
    next_no = (last.meeting_no + 1) if last else 1

    discipline_committee, honor_board = _resolve_source(council_type, honor_meeting_kind)

    meeting: CouncilMeeting = CouncilMeeting.objects.create(
        school_year=year,
        school_term=school_term,
        council_type=council_type,
        honor_meeting_kind=honor_meeting_kind,
        meeting_no=next_no,
        meeting_date=meeting_date,
        agenda=agenda,
        decision_text=decision_text,
        decision_basis=decision_basis,
        notes=notes,
        minutes_type=minutes_type,
        discipline_case=discipline_case,
        discipline_committee=discipline_committee,
        honor_board=honor_board,
    )
    _create_attendees(meeting, attendees)
    if honor_certificate_ids:
        add_agenda_items(meeting, honor_certificate_ids=honor_certificate_ids)
    return meeting


@transaction.atomic
def update_council_meeting(
    meeting: CouncilMeeting,
    *,
    meeting_date: date | None = None,
    agenda: str | None = None,
    decision_text: str | None = None,
    decision_basis: str | None = None,
    notes: str | None = None,
    attendees: list[dict[str, Any]] | None = None,
) -> CouncilMeeting:
    """Tutanak içeriğini düzeltir (meeting_no/kurul türü/tutanak türü/dosya SABİT).

    Yanlış dosya seçildiyse tutanak silinip yeniden oluşturulur (meeting_no
    atlar — defter mantığıyla tutarlı). `attendees` verilirse mevcut katılımcılar
    soft-delete edilip yeniden oluşturulur.

    Karara bağlanmış gündem maddesi varsa tarih değişmez (karar tarihleri toplantı
    tarihidir) ve Ödül ve Disiplin Kurulunda katılımcı değişikliği yeter sayıyı
    (md. 191/1) bozamaz.
    """
    decided = _decided_items(meeting).exists()
    fields: list[str] = []
    if meeting_date is not None and meeting_date != meeting.meeting_date and decided:
        raise ValueError(
            "Karara bağlanmış gündem maddesi olan toplantının tarihi değiştirilemez; önce "
            "kararları geri alın."
        )
    if meeting_date is not None:
        if meeting.council_type == CouncilType.HONOR:
            from apps.okul.services.terms import require_term_for_date

            meeting.school_term = require_term_for_date(meeting.school_year, meeting_date)
            fields.append("school_term")
        meeting.meeting_date = meeting_date
        fields.append("meeting_date")
    if agenda is not None:
        meeting.agenda = agenda
        fields.append("agenda")
    if decision_text is not None:
        meeting.decision_text = decision_text
        fields.append("decision_text")
    if decision_basis is not None:
        if decision_basis not in CouncilDecisionBasis.values:
            raise ValueError("Geçersiz karar esası.")
        meeting.decision_basis = decision_basis
        fields.append("decision_basis")
    if notes is not None:
        meeting.notes = notes
        fields.append("notes")
    if fields:
        fields.append("updated_at")
        meeting.save(update_fields=fields)

    if attendees is not None:
        _validate_attendees(attendees)
        for old in meeting.attendees.all():
            old.delete()
        _create_attendees(meeting, attendees)
        if decided and meeting.council_type == CouncilType.DISCIPLINE:
            _require_quorum(meeting)
    return meeting


@transaction.atomic
def delete_council_meeting(meeting: CouncilMeeting) -> None:
    """Tutanağı, katılımcılarını ve bekleyen gündem maddelerini soft-delete eder.

    Karara bağlanmış maddesi olan toplantı silinemez: o kararlar bu toplantıya
    dayanır (önce teklifin son adımı geri alınır).
    """
    if _decided_items(meeting).exists():
        raise ValueError(
            "Karara bağlanmış gündem maddesi olan toplantı silinemez; önce kararları geri alın."
        )
    for item in meeting.agenda_items.all():
        item.delete()
    for att in meeting.attendees.all():
        att.delete()
    meeting.delete()


# ---------------------------------------------------------------------------
# Gündem maddeleri — kurul kararı toplantıda alınır (04.10.2026)
# ---------------------------------------------------------------------------
_STAGE_BOARD = "BOARD"
_STAGE_COMMITTEE = "COMMITTEE"


def _decided_items(meeting: CouncilMeeting) -> Any:
    return meeting.agenda_items.exclude(outcome=AgendaItemOutcome.PENDING)


def _agenda_stage(meeting: CouncilMeeting) -> str:
    """Toplantının onur belgesi teklifinde hangi kurul kararını verdiği."""
    if meeting.council_type == CouncilType.HONOR:
        if meeting.honor_meeting_kind != HonorMeetingKind.BOARD:
            raise ValueError(
                "Onur Genel Kurulu onur belgesi teklifi görüşmez; teklifler Onur Kurulunda "
                "görüşülür (md. 183/b)."
            )
        return _STAGE_BOARD
    if meeting.minutes_type != CouncilMinutesType.GENERAL:
        raise ValueError(
            "Dosya görüşme tutanağına onur belgesi teklifi eklenemez; ayrı bir kurul "
            "toplantısı açın."
        )
    return _STAGE_COMMITTEE


def meeting_committee(meeting: CouncilMeeting) -> DisciplineCommittee | None:
    """Toplantının bağlı olduğu Ödül ve Disiplin Kurulu (yoksa toplantı yılının kurulu)."""
    if meeting.council_type != CouncilType.DISCIPLINE:
        return None
    if meeting.discipline_committee_id is not None:
        return meeting.discipline_committee
    committee: DisciplineCommittee | None = DisciplineCommittee.objects.filter(
        school_year_id=meeting.school_year_id
    ).first()
    return committee


def meeting_quorum(meeting: CouncilMeeting) -> dict[str, Any] | None:
    """Ödül ve Disiplin Kurulu toplantısının yeter sayı durumu (md. 191/1).

    Oy hakkı olan katılımcılar sayılır (başkan ve yerine çağrılan yedekler dahil;
    md. 185/6 davetlileri hariç). Onur Kurulu için yönetmelikte yeter sayı yoktur → None.
    """
    from apps.disiplin.services.committee import committee_quorum

    committee = meeting_committee(meeting)
    if committee is None:
        return None
    # `.filter()` önbelleği (prefetch) atlar — katılımcı değişikliğinden hemen sonra da doğru.
    present = meeting.attendees.filter(attendee_role=CouncilAttendeeRole.VOTING_MEMBER).count()
    return committee_quorum(committee, present)


def _require_quorum(meeting: CouncilMeeting) -> None:
    quorum = meeting_quorum(meeting)
    if quorum is None:
        raise ValueError(
            "Bu ders yılı için Ödül ve Disiplin Kurulu tanımlı değil; toplantı yeter sayısı "
            "denetlenemez (md. 191/1)."
        )
    if not quorum["ok"]:
        raise ValueError(
            f"Toplantı yeter sayısı yok: kurul {quorum['full']} kişi, en az "
            f"{quorum['required']} oy hakkı olan üye katılmalı; bu toplantıda "
            f"{quorum['present']} (md. 191/1)."
        )


_EXPECTED_STATUS = {
    _STAGE_BOARD: (
        HonorCertificateStatus.PROPOSED,
        "Yalnız teklif aşamasındaki belge Onur Kurulu gündemine alınabilir.",
    ),
    _STAGE_COMMITTEE: (
        HonorCertificateStatus.HONOR_BOARD_RECOMMENDED,
        "Yalnız Onur Kurulunun uygun gördüğü teklif Ödül ve Disiplin Kurulu gündemine "
        "alınabilir (md. 183/b).",
    ),
}


@transaction.atomic
def add_agenda_items(
    meeting: CouncilMeeting, *, honor_certificate_ids: list[int]
) -> list[CouncilAgendaItem]:
    """Onur belgesi tekliflerini toplantının gündemine ekler.

    Onur Kurulu toplantısı teklif aşamasındakileri, Ödül ve Disiplin Kurulu
    toplantısı Onur Kurulunca uygun görülenleri alır. Teklif aynı anda yalnız bir
    toplantıda karar bekleyebilir; ders yılı toplantıyla aynı olmalıdır.
    """
    stage = _agenda_stage(meeting)
    ids = list(dict.fromkeys(int(i) for i in honor_certificate_ids))
    if not ids:
        raise ValueError("Gündeme alınacak en az bir teklif seçilmelidir.")
    expected_status, status_message = _EXPECTED_STATUS[stage]
    last = meeting.agenda_items.order_by("-order").first()
    order = (last.order if last else 0) + 1
    created: list[CouncilAgendaItem] = []
    for certificate_id in ids:
        certificate = (
            HonorCertificate.objects.select_related("student").filter(pk=certificate_id).first()
        )
        if certificate is None:
            raise ValueError("Onur belgesi teklifi bulunamadı.")
        if certificate.school_year_id != meeting.school_year_id:
            raise ValueError("Teklif ile toplantı aynı ders yılına ait olmalıdır.")
        if certificate.status != expected_status:
            raise ValueError(f"{certificate.student.full_name}: {status_message}")
        if CouncilAgendaItem.objects.filter(
            honor_certificate=certificate, outcome=AgendaItemOutcome.PENDING
        ).exists():
            raise ValueError(
                f"{certificate.student.full_name}: teklif başka bir toplantının gündeminde "
                "karar bekliyor."
            )
        if meeting.agenda_items.filter(honor_certificate=certificate).exists():
            raise ValueError(
                f"{certificate.student.full_name}: teklif bu toplantının gündeminde zaten var."
            )
        item = CouncilAgendaItem(
            meeting=meeting,
            order=order,
            item_type=AgendaItemType.HONOR_PROPOSAL,
            honor_certificate=certificate,
        )
        item.save()
        created.append(item)
        order += 1
    return created


@transaction.atomic
def remove_agenda_item(item: CouncilAgendaItem) -> None:
    """Karar bekleyen maddeyi gündemden çıkarır (soft-delete; teklif başka toplantıya alınabilir)."""
    if item.outcome != AgendaItemOutcome.PENDING:
        raise ValueError(
            "Karara bağlanmış madde gündemden çıkarılamaz; önce teklifin son adımını geri alın."
        )
    item.delete()


@transaction.atomic
def decide_agenda_item(
    item: CouncilAgendaItem,
    *,
    outcome: str,
    decision_text: str = "",
    decision_basis: str = CouncilDecisionBasis.UNANIMITY,
    dissent_note: str = "",
) -> CouncilAgendaItem:
    """Gündem maddesini toplantıda karara bağlar ve teklifin durumunu ilerletir.

    Onur Kurulu: olumlu = uygun görüş (md. 183/b), olumsuz = uygun görmeme.
    Ödül ve Disiplin Kurulu: olumlu = kabul (md. 161/1), olumsuz = ret; toplantı
    yeter sayısı (md. 191/1) yoksa karar verilemez. Olumsuz kararda gerekçe
    zorunludur (md. 196/1, 206/2). Karar tarihi toplantı tarihidir.
    """
    from apps.disiplin.services.honors import (
        apply_committee_decision,
        apply_honor_board_decision,
    )

    if item.outcome != AgendaItemOutcome.PENDING:
        raise ValueError(
            "Bu madde zaten karara bağlandı; değiştirmek için teklifin son adımını geri alın."
        )
    if outcome not in (AgendaItemOutcome.FAVORABLE, AgendaItemOutcome.UNFAVORABLE):
        raise ValueError("Geçersiz karar.")
    if decision_basis not in CouncilDecisionBasis.values:
        raise ValueError("Geçersiz karar esası.")
    certificate = item.honor_certificate
    if certificate is None:
        raise ValueError("Gündem maddesine bağlı teklif bulunamadı.")
    meeting = item.meeting
    favorable = outcome == AgendaItemOutcome.FAVORABLE
    reason = decision_text.strip()
    if _agenda_stage(meeting) == _STAGE_COMMITTEE:
        _require_quorum(meeting)
        apply_committee_decision(certificate, meeting=meeting, favorable=favorable, reason=reason)
    else:
        apply_honor_board_decision(certificate, meeting=meeting, favorable=favorable, reason=reason)
    item.outcome = outcome
    item.decision_text = reason
    item.decision_basis = decision_basis
    item.dissent_note = dissent_note.strip()
    item.save(
        update_fields=["outcome", "decision_text", "decision_basis", "dissent_note", "updated_at"]
    )
    return item


def prefill_attendees(
    council_type: str,
    honor_meeting_kind: str = HonorMeetingKind.BOARD,
) -> list[dict[str, Any]]:
    """Form ön-doldurma: aktif kurulun üyelerini katılımcı taslağına çevirir.

    DISCIPLINE: aktif disiplin kurulu başkanı (md. 188) + asıl üyeler; HONOR:
    aktif onur kurulu başkanı (md. 182) + asıl öğrenci üyeler. Kullanıcı listeyi
    düzenleyebilir (davetli ekleme, çıkarma).
    """
    from apps.disiplin.selectors import (
        get_active_committee,
        get_active_honor_board,
        honor_general_assembly_members,
    )
    from apps.okul import selectors as school_selectors

    out: list[dict[str, Any]] = []
    order = 0

    def _add(
        name: str,
        title: str,
        *,
        is_chair: bool,
        user_id: int | None = None,
        student_id: int | None = None,
    ) -> None:
        nonlocal order
        out.append(
            {
                "person_name": name,
                "title": title,
                "attendee_role": CouncilAttendeeRole.VOTING_MEMBER,
                "is_chair": is_chair,
                "member_user_id": user_id,
                "member_student_id": student_id,
                "order": order,
            }
        )
        order += 1

    if council_type == CouncilType.DISCIPLINE:
        committee = get_active_committee()
        if committee is not None:
            _add(
                committee.chair.full_name,
                "Kurul Başkanı (Müdür Yardımcısı)",
                is_chair=True,
                user_id=committee.chair_id,
            )
            for cm in committee.members.filter(is_substitute=False):
                _add(
                    cm.member_name or str(cm.pk),
                    cm.title or cm.get_member_type_display(),
                    is_chair=False,
                    user_id=cm.member_user_id,
                    student_id=cm.member_student_id,
                )
    elif council_type == CouncilType.HONOR:
        board = get_active_honor_board()
        if board is not None:
            _add(
                board.chair.full_name,
                "Onur Kurulu Başkanı",
                is_chair=True,
                user_id=board.chair_id,
            )
            if honor_meeting_kind == HonorMeetingKind.GENERAL_ASSEMBLY:
                year = school_selectors.active_school_year()
                members = (
                    honor_general_assembly_members(
                        school_year_id=year.pk,
                        active_only=True,
                    )
                    if year is not None
                    else []
                )
                for member in members:
                    _add(
                        member.member_name,
                        f"{member.class_level}/{member.class_section} temsilcisi",
                        is_chair=False,
                        student_id=member.member_student_id,
                    )
            else:
                for hm in board.members.filter(
                    is_substitute=False,
                    effective_until__isnull=True,
                ):
                    _add(
                        hm.member_name or str(hm.pk),
                        hm.title or ("İkinci Başkan" if hm.is_second_chair else "Üye"),
                        is_chair=False,
                        student_id=hm.member_student_id,
                    )

    return out
