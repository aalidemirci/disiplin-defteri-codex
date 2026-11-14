"""Disiplin kurulu yönetimi — md. 185-192.

OYS `services/discipline_committee.py`'den temizlenerek taşındı: audit +
kullanıcı parametreleri silindi; TEACHER üye `okul.Personnel`, PARENT üye
yalnız ad snapshot'ıyla (tasarım §4.2 — Parent tablosu yok).
"""

from __future__ import annotations

from datetime import date
from typing import Any

from django.db import transaction

from apps.disiplin.models import (
    CommitteeMemberType,
    DisciplineCase,
    DisciplineCommittee,
    DisciplineCommitteeMember,
    DisciplineEvent,
    DisciplineMeeting,
)
from apps.okul import selectors as okul_selectors
from apps.okul.models import Personnel, Student


def _validate_not_honor_board_chair(*, school_year_id: int, personnel_id: int) -> None:
    """md. 182: onur kurulu başkanı (ve yedeği) ödül-disiplin kurulu üyelerinin DIŞINDADIR.

    Onur kurulu kurulurken ters yön zaten denetleniyor; bu da disiplin kuruluna
    sonradan eklenen kişi için aynı kuralı uygular.
    """
    from django.db.models import Q

    from apps.disiplin.models import HonorBoard

    if (
        HonorBoard.objects.filter(school_year_id=school_year_id)
        .filter(Q(chair_id=personnel_id) | Q(substitute_chair_id=personnel_id))
        .exists()
    ):
        raise ValueError(
            "Bu öğretmen onur kurulu başkanı/yedeği; ödül ve disiplin kuruluna üye "
            "olamaz (md. 182)."
        )


@transaction.atomic
def create_committee(*, school_year_id: int, chair_id: int, notes: str = "") -> DisciplineCommittee:
    """Bir ders yılı için disiplin kurulu oluşturur (yıl başına tek — md. 185).

    Başkan bir personel olmalı (md. 188 müdür yardımcısı). Aynı yıl için kurul
    varsa ValueError.
    """
    year = okul_selectors.get_school_year(school_year_id)
    if year is None:
        raise ValueError("Ders yılı bulunamadı.")
    chair = okul_selectors.get_personnel(chair_id)
    if chair is None:
        raise ValueError("Kurul başkanı (personel) bulunamadı.")
    if DisciplineCommittee.objects.filter(school_year=year).exists():
        raise ValueError("Bu ders yılı için zaten bir disiplin kurulu var.")
    _validate_not_honor_board_chair(school_year_id=year.pk, personnel_id=chair.pk)

    committee: DisciplineCommittee = DisciplineCommittee.objects.create(
        school_year=year, chair=chair, notes=notes
    )
    return committee


@transaction.atomic
def set_committee_chair(committee: DisciplineCommittee, chair_id: int) -> DisciplineCommittee:
    """Kurul başkanını günceller (md. 188 — müdür görevlendirir)."""
    chair = okul_selectors.get_personnel(chair_id)
    if chair is None:
        raise ValueError("Kurul başkanı (personel) bulunamadı.")
    _validate_not_honor_board_chair(school_year_id=committee.school_year_id, personnel_id=chair.pk)
    committee.chair = chair
    committee.save(update_fields=["chair", "updated_at"])
    return committee


@transaction.atomic
def add_committee_member(
    committee: DisciplineCommittee,
    *,
    member_type: str,
    person_id: int | None = None,
    member_name: str = "",
    is_substitute: bool = False,
    order: int = 0,
    title: str = "",
) -> DisciplineCommitteeMember:
    """Kurula asıl/yedek üye ekler (md. 185-186). Aynı kişi iki kez eklenemez.

    TEACHER→`person_id` Personnel, STUDENT→`person_id` Student; PARENT üyede FK
    YOK — `member_name` zorunludur (ad snapshot yeter, tasarım §4.2).
    """
    m_user: Personnel | None = None
    m_student: Student | None = None
    if member_type == CommitteeMemberType.TEACHER:
        if person_id is None:
            raise ValueError("Öğretmen üye için personel seçilmelidir.")
        m_user = okul_selectors.get_personnel(person_id)
        if m_user is None:
            raise ValueError("Öğretmen üye bulunamadı.")
        _validate_not_honor_board_chair(
            school_year_id=committee.school_year_id, personnel_id=m_user.pk
        )
        name = m_user.full_name
    elif member_type == CommitteeMemberType.STUDENT:
        if person_id is None:
            raise ValueError("Öğrenci üye için öğrenci seçilmelidir.")
        m_student = okul_selectors.get_student(person_id)
        if m_student is None:
            raise ValueError("Öğrenci üye bulunamadı.")
        name = m_student.full_name or f"#{person_id}"
    elif member_type == CommitteeMemberType.PARENT:
        name = (member_name or "").strip()
        if not name:
            raise ValueError("Veli üye için ad-soyad zorunludur.")
    else:
        raise ValueError("Geçersiz üye tipi.")

    # Aynı kişiyi (tipe göre) iki kez eklemeyi engelle; veli üyede ada bakılır.
    dup_qs = DisciplineCommitteeMember.objects.filter(committee=committee)
    if m_user is not None or m_student is not None:
        dup = dup_qs.filter(member_user=m_user, member_student=m_student).exists()
    else:
        dup = dup_qs.filter(member_type=CommitteeMemberType.PARENT, member_name=name).exists()
    if dup:
        raise ValueError("Bu kişi bu kurula zaten üye olarak eklenmiş.")

    member = DisciplineCommitteeMember(
        committee=committee,
        member_type=member_type,
        is_substitute=is_substitute,
        order=order,
        title=title,
        member_user=m_user,
        member_student=m_student,
        member_name=name,
    )
    member.full_clean()
    member.save()
    return member


@transaction.atomic
def remove_committee_member(member: DisciplineCommitteeMember) -> None:
    """Kurul üyesini soft-delete eder (kayıt korunur)."""
    member.delete()


def committee_quorum(committee: DisciplineCommittee, present: int) -> dict[str, Any]:
    """md. 191/1 ölçüsü: kurul üyelerin SALT ÇOĞUNLUĞUYLA toplanır.

    Üye tam sayısı = başkan + asıl üyeler (md. 185/1); `present` toplantıda oy
    hakkı olan katılımcı sayısıdır (başkan ve yerine çağrılan yedekler dahil).
    """
    full = 1 + committee.members.filter(is_substitute=False).count()
    required = full // 2 + 1
    return {"full": full, "required": required, "present": present, "ok": present >= required}


def _check_quorum(
    committee: DisciplineCommittee, attendee_count: int, *, chair_absent: bool = False
) -> None:
    """md. 191/1: kurul üyelerin SALT ÇOĞUNLUĞUYLA toplanır.

    Üye tam sayısı = başkan + asıl üyeler (md. 185/1) — vekâlette de DEĞİŞMEZ. Başkan
    katıldıysa sayılır. Başkan katılmadıysa (`chair_absent`, S7) sayılmaz: md. 188 gereği
    başkanlık eden öğretmen üye ve çağrılan yedek zaten katılımcı listesindedir.
    """
    present = attendee_count + (0 if chair_absent else 1)
    quorum = committee_quorum(committee, present)
    if attendee_count < 1 or not quorum["ok"]:
        counted = (
            "başkanlık eden üye dahil; katılmayan başkan sayılmaz"
            if chair_absent
            else "başkan dahil"
        )
        raise ValueError(
            f"Toplantı yeter sayısı yok: kurul {quorum['full']} kişi, en az "
            f"{quorum['required']} kişi ({counted}) katılmalı (md. 191/1 — üyelerin salt "
            "çoğunluğu)."
        )


def conflicted_ids(case: DisciplineCase) -> tuple[set[int], set[int]]:
    """md. 191/2 kümesi: dosyada şikâyetçi / zarar gören (veya hakkında işlem yapılan)
    kişilerin (personel id'leri, öğrenci id'leri)."""
    from apps.disiplin.models import ParticipantRole

    conflicted_users = set(
        case.participants.filter(role=ParticipantRole.VICTIM, user__isnull=False).values_list(
            "user_id", flat=True
        )
    )
    conflicted_students = set(
        case.participants.filter(
            role__in=[ParticipantRole.VICTIM, ParticipantRole.ACCUSED], student__isnull=False
        ).values_list("student_id", flat=True)
    )
    if case.petitioner_user_id is not None:
        conflicted_users.add(case.petitioner_user_id)
    if case.petitioner_student_id is not None and case.petitioner_role == "OGRENCI":
        conflicted_students.add(case.petitioner_student_id)
    return conflicted_users, conflicted_students


# ---------------------------------------------------------------------------
# VEKÂLET KAYDI (kullanıcı kararı, 14.11.2026 — S7) — md. 188, 191/2
# ---------------------------------------------------------------------------
def chair_conflicted(case: DisciplineCase, committee: DisciplineCommittee) -> bool:
    """Kurul başkanı bu dosyada şikâyetçi ya da zarar gören mi? (md. 191/2)

    Başkan da kurulun üyesidir (md. 185/1-a); "şikâyetçi olan veya zarar gören üye kurula
    katılamaz" hükmü onu da kapsar.
    """
    return committee.chair_id in conflicted_ids(case)[0]


def acting_chair_candidates(
    committee: DisciplineCommittee, case: DisciplineCase | None = None
) -> list[DisciplineCommitteeMember]:
    """Başkanın yokluğunda kurula başkanlık edebilecek üyeler (md. 188).

    md. 188/1: "Başkan bulunmadığında müdürün görevlendireceği ÖĞRETMEN ÜYELERDEN biri
    kurula başkanlık eder." Dar yorum: kurulun ASIL öğretmen üyeleri (md. 185/1-b). Öğrenci
    ve veli üye başkanlık edemez; yedek öğretmen üye metinde açıkça sayılmadığı için aday
    değildir. Dosya verilirse o dosyada şikâyetçi / zarar gören öğretmen üye de çıkarılır
    (md. 191/2 — kurula katılamayan üye başkanlık da edemez).
    """
    members = DisciplineCommitteeMember.objects.filter(
        committee=committee,
        member_type=CommitteeMemberType.TEACHER,
        is_substitute=False,
        member_user__isnull=False,
    )
    if case is None:
        return list(members)
    conflicted_users, _students = conflicted_ids(case)
    return [m for m in members if m.member_user_id not in conflicted_users]


def acting_chair_options(
    committee: DisciplineCommittee, case: DisciplineCase | None = None
) -> dict[str, Any]:
    """Toplantı formları için vekâlet bilgisi: başkan, başkan bu dosyada engelli mi, adaylar."""
    return {
        "chair": committee.chair_id,
        "chair_name": committee.chair.full_name,
        "chair_conflicted": case is not None and chair_conflicted(case, committee),
        "eligible": [
            {
                "member_id": m.pk,
                "member_user": m.member_user_id,
                "member_name": m.member_name,
                "title": m.title,
            }
            for m in acting_chair_candidates(committee, case)
        ],
    }


#: md. 188 son cümlesi + md. 191/2 — UYARI metni (engel değil; `meeting_chair_warnings`).
NO_SUBSTITUTE_WARNING = (
    "Başkan katılmadı ama katılanlar arasında yedek üye yok: üyenin başkanlık yaptığı "
    "durumlarda yedek üye toplantıya katılır (md. 188); kurula katılmayan üyenin yerine yedek "
    "üye çağrılır (md. 191/2). Yedek üye katıldıysa katılanlara ekleyin."
)


def meeting_chair_warnings(meeting: DisciplineMeeting) -> list[str]:
    """Dosya toplantısının VEKÂLET KAYDI uyarıları (S7) — UYARIDIR, kaydı engellemez.

    Başkan katılmadıysa ve katılanlar arasında yedek üye yoksa md. 188 son cümlesi hatırlatılır.
    Engel değildir (S5/S6 çizgisi): yedek de mazeretli olabilir; yeter sayı ayrıca denetlenir.
    """
    if not meeting.chair_absent:
        return []
    if any(member.is_substitute for member in meeting.attendees.all()):
        return []
    return [NO_SUBSTITUTE_WARNING]


#: Uygun asıl öğretmen üye yokken verilen ileti (kullanıcı kararı, 14.11.2026 — S7/K2).
#: Vekil yalnız ASIL öğretmen üyedir (md. 188 — dar yorum kalır). İleti kurula öğretmen üye
#: EKLEMEYİ önermez: kurulda iki öğretmen bulunur (md. 185/1-b), üçüncü asıl öğretmen üye
#: tam sayıyı ve yeter sayıyı büyütür. Yalnız durum ve yönetmeliğin kendi yolu söylenir:
#: md. 186 "Asıl üyeliğin boşalması veya üyenin özürlü ya da izinli bulunması hâlinde bu
#: üyelik, sıraya göre yedek üyelerle doldurulur"; md. 187 "Asıl ve yedek üyeliklerin boşalması
#: nedeniyle … kurulunun kurulamaması hâlinde açık bulunan üyelikler için yeniden gizli oyla
#: seçim yapılır".
_NO_CANDIDATE_HINT = (
    "Kurulda bu toplantıya başkanlık edebilecek asıl öğretmen üye yok (md. 188: başkan "
    "bulunmadığında kurula öğretmen üyelerden biri başkanlık eder; md. 191/2: şikâyetçi/zarar "
    "gören üye kurula katılamaz). Asıl öğretmen üyeliği boşalmışsa bu üyelik sıraya göre yedek "
    "üyeyle doldurulur (md. 186); asıl ve yedek üyelikler boşaldığı için kurul kurulamıyorsa "
    "açık üyelikler için yeniden seçim yapılır (md. 187). Kurul kaydı bu duruma getirilmeden "
    "toplantı kaydedilemez."
)


#: Başkanı şikâyetçi / zarar gören dosyada vekâlet kaydı yokken gösterilen KALICI uyarı
#: (kullanıcı kararı, 14.11.2026 — S7/K4). Eski kayıt kendiliğinden değiştirilmez.
_CHAIR_CONFLICT_CASE_WARNING = (
    "Kurul başkanı bu dosyada şikâyetçi/zarar gören (md. 191/2); {action} — o zamana dek "
    "belgelerde başkan hanesi boş basılır."
)


def case_chair_warnings(case: DisciplineCase) -> list[str]:
    """Dosya ekranının VEKÂLET uyarısı (S7/K4) — UYARIDIR, hiçbir işlemi engellemez.

    Kurula sevkli dosyada kurul başkanı şikâyetçi / zarar gören ise (md. 191/2) ve dosyanın
    SON toplantı kaydı vekâletli değilse (toplantı kaydı yok ya da S7 öncesi / vekâletsiz
    kayıt) kurul evrakında başkan hanesi boş basılır (`documents._signing_panel`,
    `documents._case_committee`). Kayıt kendiliğinden DEĞİŞTİRİLMEZ; kullanıcı toplantıyı
    "Başkan toplantıya katılmadı" kaydıyla (yeniden) kaydedince uyarı kalkar. Kurula sevk
    edilmemiş dosyada kurul evrakı üretilmediğinden uyarı da yoktur.
    """
    from apps.disiplin.selectors import committee_for_case, committee_referred_on

    if committee_referred_on(case) is None:
        return []
    committee = committee_for_case(case)
    if committee is None or not chair_conflicted(case, committee):
        return []
    meeting = case.meetings.first()
    if meeting is None:
        action = "kurul toplantısını 'Başkan toplantıya katılmadı' kaydıyla kaydedin"
    elif meeting.chair_absent and meeting.acting_chair_id is not None:
        return []
    else:
        action = (
            "toplantıyı 'Başkan toplantıya katılmadı' kaydıyla yeniden kaydedin (kaydı silip "
            "doğrusunu girin)"
        )
    if case.closed_at is not None:
        # Kapalı dosyada toplantı kaydı reddedilir; yapılamayan adımı önerme (§7.6).
        action = f"önce dosyayı yeniden açın (aşama geri alma), sonra {action}"
    return [_CHAIR_CONFLICT_CASE_WARNING.format(action=action)]


def chair_conflict_message(
    committee: DisciplineCommittee, case: DisciplineCase, *, has_candidate: bool
) -> str:
    """Şikâyetçi / zarar gören başkanın dosyasında vekâletsiz toplantı reddi (eyleme dönük)."""
    message = (
        f"Kurul başkanı {committee.chair.full_name} bu dosyada şikâyetçi/zarar gören kişi; "
        "kurula katılamaz (md. 191/2). Toplantıyı 'Başkan toplantıya katılmadı' seçeneğiyle "
        "kaydedin ve kurula başkanlık eden öğretmen üyeyi seçin (md. 188)."
    )
    return message if has_candidate else f"{message} {_NO_CANDIDATE_HINT}"


def acting_chair_rule_message(*, has_candidate: bool, conflicted: bool = False) -> str:
    """Başkanlık eden kişinin md. 188'e uymadığı durumun iletisi."""
    reason = (
        " Seçilen üye bu dosyada şikâyetçi/zarar gören olduğundan kurula katılamaz (md. 191/2)."
        if conflicted
        else ""
    )
    message = (
        "Kurula başkanlık eden kişi kurulun asıl öğretmen üyelerinden biri olmalıdır (md. 188: "
        f"başkan bulunmadığında müdürün görevlendireceği öğretmen üyelerden biri).{reason}"
    )
    return message if has_candidate else f"{message} {_NO_CANDIDATE_HINT}"


def _check_conflicts(case: DisciplineCase, members: Any) -> None:
    """md. 191/2: şikâyetçi veya zarar gören üye kurula katılamaz (yerine yedek)."""
    conflicted_users, conflicted_students = conflicted_ids(case)
    names = [
        m.member_name
        for m in members
        if (m.member_user_id is not None and m.member_user_id in conflicted_users)
        or (m.member_student_id is not None and m.member_student_id in conflicted_students)
    ]
    if names:
        raise ValueError(
            f"{', '.join(names)} bu dosyada şikâyetçi/zarar gören (veya hakkında işlem "
            "yapılan) kişi; kurula katılamaz, yerine yedek üye çağrılır (md. 191/2)."
        )


@transaction.atomic
def record_meeting(
    case: DisciplineCase,
    *,
    meeting_date: date,
    attendee_member_ids: list[int],
    notes: str = "",
    event: DisciplineEvent | None = None,
    chair_absent: bool = False,
    acting_chair_member_id: int | None = None,
) -> DisciplineMeeting:
    """Bir dosya için kurul toplantısı kaydeder; katılanlar kurul üyelerinden seçilir.

    Katılımcılar aktif kurulun üyeleri olmalı (md. 191). Tutanak/PDF veriyi
    buradan çeker.

    VEKÂLET KAYDI (S7, 14.11.2026): başkan bu kayıtta katılımcı satırı değildir, katıldığı
    varsayılır. `chair_absent=True` ise başkan katılmamıştır ve `acting_chair_member_id`
    kurula başkanlık eden asıl öğretmen üyedir (md. 188) — katılanlar arasında olmalıdır.
    Başkan dosyada şikâyetçi / zarar gören ise toplantı ANCAK böyle kaydedilir (md. 191/2).
    Yeter sayıda katılmayan başkan sayılmaz (md. 191/1).
    """
    from apps.disiplin.selectors import committee_referred_on, get_active_committee

    # Kurul yalnız kendisine sevk edilen, açık dosyayı görüşür (md. 163/2, 189/h) — karar
    # girişiyle aynı koşul. Kapalı dosyada toplantı kaydı kapanış dayanağını bulandırır.
    if case.closed_at is not None:
        raise ValueError(
            "Dosya kapalı: kurul toplantısı kaydedilemez. Gerekiyorsa önce dosyayı yeniden "
            "açın (aşama geri alma)."
        )
    referred_on = committee_referred_on(case)
    if referred_on is None:
        raise ValueError(
            "Dosya disiplin kuruluna sevk edilmemiş; kurul toplantısı kaydedilemez. Önce "
            "müdür kararıyla dosyayı kurula sevk edin (md. 163/2)."
        )
    if meeting_date < referred_on:
        raise ValueError(
            f"Toplantı tarihi, dosyanın kurula sevk tarihinden ({referred_on:%d.%m.%Y}) önce "
            "olamaz."
        )

    committee = get_active_committee()
    if committee is None:
        raise ValueError("Aktif ders yılı için tanımlı bir disiplin kurulu yok.")

    valid_ids = set(
        committee.members.filter(pk__in=attendee_member_ids).values_list("id", flat=True)
    )
    unknown = set(attendee_member_ids) - valid_ids
    if unknown:
        raise ValueError("Katılımcılar aktif kurulun üyeleri arasından seçilmelidir.")
    candidates = acting_chair_candidates(committee, case)
    if not chair_absent:
        if acting_chair_member_id is not None:
            raise ValueError(
                "Başkanlık eden üye yalnız 'Başkan toplantıya katılmadı' işaretliyken seçilir."
            )
        if chair_conflicted(case, committee):
            raise ValueError(
                chair_conflict_message(committee, case, has_candidate=bool(candidates))
            )
    _check_conflicts(case, committee.members.filter(pk__in=valid_ids))
    if chair_absent:
        if acting_chair_member_id is None:
            hint = "" if candidates else f" {_NO_CANDIDATE_HINT}"
            raise ValueError(
                "Başkan toplantıya katılmadıysa kurula başkanlık eden öğretmen üye seçilmelidir "
                f"(md. 188).{hint}"
            )
        if acting_chair_member_id not in {m.pk for m in candidates}:
            raise ValueError(acting_chair_rule_message(has_candidate=bool(candidates)))
        if acting_chair_member_id not in valid_ids:
            raise ValueError(
                "Başkanlık eden üye toplantıya katılanlar arasında olmalıdır; katılan üyeler "
                "listesinde işaretleyin."
            )
    _check_quorum(committee, len(valid_ids), chair_absent=chair_absent)

    meeting = DisciplineMeeting(
        case=case,
        event=event,
        meeting_date=meeting_date,
        notes=notes,
        chair_absent=chair_absent,
        acting_chair_id=acting_chair_member_id if chair_absent else None,
    )
    meeting.full_clean(exclude=["event"])
    meeting.save()
    if valid_ids:
        meeting.attendees.set(valid_ids)
    return meeting


@transaction.atomic
def delete_meeting(meeting: DisciplineMeeting) -> None:
    """Yanlış girilen dosya toplantısı kaydını siler (soft-delete).

    Toplantı kaydı EK-1 imza heyetini belirler; yanlış kayıt düzeltilemezse tek yönlü
    kapan olur (§7.6). Kapalı dosyada reddedilir (kapanış dayanağı kilitli).
    """
    if meeting.case.closed_at is not None:
        raise ValueError(
            "Dosya kapalı: kurul toplantısı kaydı silinemez. Gerekiyorsa önce dosyayı yeniden "
            "açın (aşama geri alma)."
        )
    meeting.delete()
