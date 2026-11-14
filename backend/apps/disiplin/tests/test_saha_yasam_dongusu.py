"""Saha (uçtan uca) denetimi — dosya yaşam döngüsü bulguları (14.11.2026).

Windows'ta uçtan uca senaryolarla bulunup yeniden üretilerek doğrulanmış kusurların
testleri: kapalı dosya kilidi (tedbir/uzatma/katılımcı), müdür uyarısı tekilliği ve
md. 157/7-e kapısı, tarih sırası, tedbir başlangıcı, süre panelinin yanlış alarmı,
süre uzatmasının geri alınması, geri alınmış sevk, imha kapsamı/tutanağı ve öğrenci
silme koruması.
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
from typing import Any
from unittest import mock

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.disiplin import deadlines, discipline_periods, selectors, services
from apps.disiplin.models import (
    CaseStage,
    DisciplineCase,
    DisciplineCommittee,
    DisciplineWarning,
    DocumentType,
    PenaltyType,
    PrecautionStatus,
    PrincipalDecision,
)
from apps.disiplin.selectors import purge as purge_selectors
from apps.disiplin.services import purge as purge_service
from apps.disiplin.tests.factories import (
    PersonnelFactory,
    SchoolYearFactory,
    StudentFactory,
    decide,
)
from apps.okul.models import Student, StudentStatus
from apps.okul.services import persons as persons_service
from apps.okul.services import setup as okul_setup
from apps.okul.services.calendar import is_working_day

pytestmark = pytest.mark.django_db

PETITION = date(2026, 5, 18)  # Pazartesi
REFERRED = date(2026, 5, 19)  # Salı — kurula sevk


def _case(student: Student | None = None, *, petition: date = PETITION) -> DisciplineCase:
    SchoolYearFactory()
    s = student or StudentFactory()
    return services.create_case(
        petition_date=petition,
        petitioner_name="İdare",
        petitioner_role="IDARE",
        summary="Sınıf içinde uygunsuz davranış.",
        student_ids=[s.pk],
    )


def _sid(case: DisciplineCase) -> int:
    return int(case.case_students.values_list("student_id", flat=True)[0])


def _refer(case: DisciplineCase, on: date = REFERRED) -> None:
    services.add_event(
        case,
        CaseStage.DECIDED,
        on,
        override=True,
        override_reason="Rehberlik atlandı.",
        principal_decisions=[PrincipalDecision.DISCIPLINE_COMMITTEE],
    )
    case.refresh_from_db()


def _warn_close(case: DisciplineCase, on: date = REFERRED) -> None:
    """Dal A: müdür yazılı uyarı verir → dosya otomatik kapanır."""
    services.add_event(
        case,
        CaseStage.DECIDED,
        on,
        override=True,
        override_reason="Rehberlik atlandı.",
        principal_decisions=[PrincipalDecision.WRITTEN_WARNING],
    )
    case.refresh_from_db()


def _committee_case() -> DisciplineCase:
    case = _case()
    _refer(case)
    return case


def _ensure_committee() -> None:
    year = SchoolYearFactory()
    if not DisciplineCommittee.objects.filter(school_year=year).exists():
        services.create_committee(school_year_id=year.pk, chair_id=PersonnelFactory().pk)


def _closed_committee_case() -> DisciplineCase:
    case = _committee_case()
    services.close_case(case, override=True, override_reason="Test kapanışı.")
    case.refresh_from_db()
    return case


def _titles(today: date) -> list[tuple[str, str]]:
    return [(i.severity, i.title) for i in deadlines.collect_deadline_items(today)]


# ---------------------------------------------------------------------------
# Kapalı dosya kilidi (bulgu 12, 25, 34)
# ---------------------------------------------------------------------------
def test_kapali_dosyaya_tedbir_eklenemez() -> None:
    case = _closed_committee_case()
    with pytest.raises(ValueError, match="Dosya kapalı"):
        services.create_precaution(
            case, student_id=_sid(case), start_date=date(2026, 5, 20), requested_days=3
        )


def test_kapali_dosyada_tedbir_uzatilamaz_ama_sonlandirilabilir() -> None:
    case = _committee_case()
    p = services.create_precaution(
        case, student_id=_sid(case), start_date=date(2026, 5, 20), requested_days=3
    )
    services.close_case(case, override=True, override_reason="Test kapanışı.")
    p.refresh_from_db()
    with pytest.raises(ValueError, match="Dosya kapalı"):
        services.extend_precaution(p, additional_days=2, mne_notified=True)
    # Yürürlükte kalmış tedbir kapalı dosyada da sonlandırılabilmeli (panelde asılı kalmasın).
    services.lift_precaution(p, lifted_on=date(2026, 5, 22))
    p.refresh_from_db()
    assert p.status == PrecautionStatus.LIFTED


def test_kapali_dosyada_sure_uzatmasi_eklenemez_onaylanamaz() -> None:
    case = _committee_case()
    ext = services.create_extension(
        case, requested_days=5, reason="İfade gecikmesi", decided_on=date(2026, 5, 25)
    )
    services.close_case(case, override=True, override_reason="Test kapanışı.")
    ext.refresh_from_db()
    with pytest.raises(ValueError, match="Dosya kapalı"):
        services.approve_extension(ext, approved_on=date(2026, 5, 26))

    other = _closed_committee_case()
    with pytest.raises(ValueError, match="Dosya kapalı"):
        services.create_extension(
            other, requested_days=5, reason="gecikme", decided_on=date(2026, 5, 25)
        )


def test_kapali_dosyada_katilimci_eklenemez_cikarilamaz() -> None:
    case = _committee_case()
    witness = services.add_participant(
        case, role="WITNESS", person_type="EXTERNAL", external_name="Tanık Kişi"
    )
    services.close_case(case, override=True, override_reason="Test kapanışı.")
    case.refresh_from_db()
    with pytest.raises(ValueError, match="Dosya kapalı"):
        services.add_participant(
            case, role="WITNESS", person_type="EXTERNAL", external_name="Geç Gelen"
        )
    witness.refresh_from_db()
    with pytest.raises(ValueError, match="Dosya kapalı"):
        services.remove_participant(witness)


def test_uyariyla_kapanan_dosyada_uyari_kaydi_acilabilir() -> None:
    """Dal A dosyası müdür kararıyla OTOMATİK kapanır; uyarı kaydı sonradan girilir."""
    case = _case()
    _warn_close(case)
    assert case.closed_at is not None
    warning = services.issue_warning(
        case, student_id=_sid(case), warning_date=REFERRED, summary="Kusurlu davranış."
    )
    assert warning.pk


def test_panel_kapali_dosyanin_tedbirini_listelemez() -> None:
    case = _committee_case()
    services.create_precaution(
        case, student_id=_sid(case), start_date=date(2026, 5, 20), requested_days=3
    )
    assert selectors.precautions_awaiting_deadline(date(2026, 6, 30)).count() == 1
    services.close_case(case, override=True, override_reason="Test kapanışı.")
    assert selectors.precautions_awaiting_deadline(date(2026, 6, 30)).count() == 0


def test_kapali_dosyaya_overrideli_olay_dosyayi_yeniden_acar() -> None:
    """13.11 denetimi: kapalı dosyaya override'lı olay eklenince closed_at dolu kalıyordu."""
    case = _closed_committee_case()
    services.add_event(
        case,
        CaseStage.DECIDED,
        date(2026, 5, 28),
        override=True,
        override_reason="Yanlışlıkla kapatıldı.",
        principal_decisions=[PrincipalDecision.DISCIPLINE_COMMITTEE],
    )
    case.refresh_from_db()
    assert case.current_stage == CaseStage.DECIDED
    assert case.closed_at is None


# ---------------------------------------------------------------------------
# Müdür uyarısı kaydı (bulgu 9, 6)
# ---------------------------------------------------------------------------
def test_ayni_dosyada_ayni_ogrenciye_ikinci_uyari_kaydi_acilamaz() -> None:
    case = _case()
    _warn_close(case)
    services.issue_warning(case, student_id=_sid(case), warning_date=REFERRED, summary="İlk.")
    with pytest.raises(ValueError, match="zaten müdür uyarısı kaydı var"):
        services.issue_warning(
            case, student_id=_sid(case), warning_date=date(2026, 5, 20), summary="İkinci."
        )


def test_yanlis_uyari_kaydi_silinip_yeniden_girilebilir() -> None:
    """§7.6: tekillik kuralı tek yönlü kapan olmasın — yanlış kayıt geri alınabilir."""
    case = _case()
    _warn_close(case)
    warning = services.issue_warning(
        case, student_id=_sid(case), warning_date=REFERRED, summary="Yanlış özet."
    )
    services.delete_warning(warning)
    assert not DisciplineWarning.objects.filter(pk=warning.pk).exists()
    assert DisciplineWarning.all_objects.filter(pk=warning.pk).exists()  # soft delete
    again = services.issue_warning(
        case, student_id=_sid(case), warning_date=REFERRED, summary="Doğru özet."
    )
    assert again.pk != warning.pk


def test_api_uyari_kaydi_silme_ucu() -> None:
    case = _case()
    _warn_close(case)
    warning = services.issue_warning(
        case, student_id=_sid(case), warning_date=REFERRED, summary="Yanlış."
    )
    client = APIClient()
    response = client.delete(f"/api/v1/discipline/cases/{case.pk}/warnings/{warning.pk}/")
    assert response.status_code == 204, response.content
    assert not DisciplineWarning.objects.filter(pk=warning.pk).exists()
    assert client.delete(f"/api/v1/discipline/cases/{case.pk}/warnings/99999/").status_code == 404


def test_gecmisi_olan_ogrenciye_ikinci_dosyada_uyari_kaydi_acilamaz() -> None:
    """md. 157/7-e: ikinci kınamalık davranışta öğrenci doğrudan kurula gönderilir."""
    student = StudentFactory()
    first = _case(student)
    _warn_close(first)
    second = _case(student, petition=date(2026, 5, 25))
    with pytest.raises(ValueError, match="157/7-e"):
        services.issue_warning(
            second, student_id=student.pk, warning_date=date(2026, 5, 26), summary="İkinci dosya."
        )


def test_gerekceli_override_ile_uyari_verilen_ikinci_dosyada_kayit_acilir() -> None:
    """§8: geçmişi olan öğrencide yazılı uyarı yolu yalnız gerekçeli override ile açıktır.

    Kullanıcı kararı, 14.11.2026 — S10: md. 157/7-e engeli artık aşama atlama
    override'ıyla AŞILMAZ; ayrı işaret + ayrı gerekçe gerekir. Eski test tek
    `override` bayrağıyla iki engeli birden aşıyordu — invariant değişti.
    """
    student = StudentFactory()
    first = _case(student)
    _warn_close(first)
    second = _case(student, petition=date(2026, 5, 25))
    with pytest.raises(ValueError, match=r"md\. 157/7-e"):
        _warn_close(second, on=date(2026, 5, 26))  # yalnız aşama atlama: yetmez
    services.add_event(
        second,
        CaseStage.DECIDED,
        date(2026, 5, 26),
        override=True,
        override_reason="Rehberlik atlandı.",
        warning_block_override=True,
        warning_block_override_reason="Davranışlar arasında bağ yok.",
        principal_decisions=[PrincipalDecision.WRITTEN_WARNING],
    )
    second.refresh_from_db()
    warning = services.issue_warning(
        second, student_id=student.pk, warning_date=date(2026, 5, 26), summary="Override'lı."
    )
    assert warning.pk


def test_kurula_sevkli_dosyada_uyari_kaydi_acilamaz() -> None:
    case = _committee_case()
    with pytest.raises(ValueError, match="kurula sevk"):
        services.issue_warning(
            case, student_id=_sid(case), warning_date=date(2026, 5, 20), summary="Dal B."
        )


# ---------------------------------------------------------------------------
# Tarih tutarlılığı (bulgu 10, 27, 56)
# ---------------------------------------------------------------------------
def _tomorrow() -> date:
    return timezone.localdate() + timedelta(days=1)


def test_gelecek_tarihli_dilekce_reddedilir() -> None:
    SchoolYearFactory()
    s = StudentFactory()
    with pytest.raises(ValueError, match="bugünden ileri"):
        services.create_case(
            petition_date=_tomorrow(),
            petitioner_name="İdare",
            petitioner_role="IDARE",
            summary="x",
            student_ids=[s.pk],
        )
    case = _case(s)
    with pytest.raises(ValueError, match="bugünden ileri"):
        services.update_case(case, petition_date=_tomorrow())


_LOCAL_TODAY = date(2026, 5, 20)  # yamalı "bugün" (Çarşamba) — gerçek bugünden geride
_LOCAL_TOMORROW = date(2026, 5, 21)


def test_ileri_tarih_yardimcisi_yerel_tarihi_kullanir() -> None:
    """§7.1: "bugün" yerel tarihtir — `timezone.localdate()` (UTC'den türetilmez).

    "İleri tarih olamaz" denetiminin TEK yeri `services.common.assert_not_future`.
    """
    from apps.disiplin.services.common import assert_not_future

    with mock.patch("django.utils.timezone.localdate", return_value=_LOCAL_TODAY):
        assert_not_future(_LOCAL_TODAY, "Tarih")  # bugün serbest
        assert_not_future(date(2026, 5, 1), "Tarih")  # geçmiş serbest
        with pytest.raises(ValueError, match=r"Tarih bugünden ileri olamaz \(21\.05\.2026\)"):
            assert_not_future(_LOCAL_TOMORROW, "Tarih")
        with pytest.raises(ValueError, match="özel ileti"):
            assert_not_future(_LOCAL_TOMORROW, "Tarih", message="özel ileti")


def _ileri_dilekce() -> None:
    SchoolYearFactory()
    services.create_case(
        petition_date=_LOCAL_TOMORROW,
        petitioner_name="İdare",
        petitioner_role="IDARE",
        summary="x",
        student_ids=[StudentFactory().pk],
    )


def _ileri_dilekce_duzeltme() -> None:
    services.update_case(_case(), petition_date=_LOCAL_TOMORROW)


def _ileri_asama() -> None:
    services.add_event(
        _case(), CaseStage.GUIDANCE_REFERRED, _LOCAL_TOMORROW, assigned_guidance_name="Rehber"
    )


def _ileri_ara_karar() -> None:
    services.create_extension(
        _committee_case(), requested_days=5, reason="x", decided_on=_LOCAL_TOMORROW
    )


def _ileri_uzatma_onayi() -> None:
    ext = services.create_extension(
        _committee_case(), requested_days=5, reason="x", decided_on=_LOCAL_TODAY
    )
    services.approve_extension(ext, approved_on=_LOCAL_TOMORROW)


def _ileri_uyari() -> None:
    case = _case()
    _warn_close(case)
    services.issue_warning(case, student_id=_sid(case), warning_date=_LOCAL_TOMORROW, summary="x")


@pytest.mark.parametrize(
    "giris",
    [
        _ileri_dilekce,
        _ileri_dilekce_duzeltme,
        _ileri_asama,
        _ileri_ara_karar,
        _ileri_uzatma_onayi,
        _ileri_uyari,
    ],
    ids=lambda f: f.__name__.lstrip("_"),
)
def test_bugun_yerel_tarihtir(giris: Any) -> None:
    """Her giriş noktası ortak yardımcıdan geçer: "bugün" yamalı YEREL tarihtir.

    Gerçek bugün yamalı tarihten ileridedir; denetim `timezone.localdate()` dışında bir
    kaynaktan (ör. UTC `now().date()`) türeseydi 21.05.2026 reddedilmezdi (§7.1).
    Eski tek kopyalı test yalnız dosya açmayı sınıyordu (gözden geçirme 14.11.2026).
    """
    with mock.patch("django.utils.timezone.localdate", return_value=_LOCAL_TODAY):
        with pytest.raises(ValueError, match="bugünden ileri"):
            giris()


def test_dilekce_tarihi_ilk_asama_olayindan_sonraya_alinamaz() -> None:
    case = _case()
    services.add_event(
        case, CaseStage.GUIDANCE_REFERRED, date(2026, 5, 19), assigned_guidance_name="Rehber"
    )
    with pytest.raises(ValueError, match="aşama olayından sonra"):
        services.update_case(case, petition_date=date(2026, 5, 20))
    services.update_case(case, petition_date=date(2026, 5, 15))  # geriye çekmek serbest
    case.refresh_from_db()
    assert case.petition_date == date(2026, 5, 15)


def test_asama_tarihi_gelecekte_olamaz() -> None:
    case = _case()
    with pytest.raises(ValueError, match="bugünden ileri"):
        services.add_event(
            case, CaseStage.GUIDANCE_REFERRED, _tomorrow(), assigned_guidance_name="Rehber"
        )


def test_asama_tarihi_dilekceden_once_olamaz() -> None:
    case = _case()
    with pytest.raises(ValueError, match="dilekçe tarihinden"):
        services.add_event(
            case, CaseStage.GUIDANCE_REFERRED, date(2026, 5, 15), assigned_guidance_name="Rehber"
        )


def test_asama_tarihi_onceki_asamadan_once_olamaz() -> None:
    case = _case()
    services.add_event(
        case, CaseStage.GUIDANCE_REFERRED, date(2026, 5, 20), assigned_guidance_name="Rehber"
    )
    # İleti çıkış yolunu da söyler (yanlış girilmiş önceki tarih tek yönlü kapan olmasın).
    with pytest.raises(ValueError, match="önceki aşama.*geri alıp doğru tarihle"):
        services.add_event(
            case, CaseStage.GUIDANCE_RETURNED, date(2026, 5, 19), guidance_outcome="NO_RESULT"
        )


def test_ileri_tarihli_onceki_olay_sirayi_baglamaz() -> None:
    """Eski sürüm tarih denetlemiyordu: ileri tarihle kaydedilmiş olayı olan dosyada
    sonraki aşama girilebilmeli (önceki olayın tarihi bugünden ileriyse sıra atlanır)."""
    from apps.disiplin.models import DisciplineEvent

    case = _case()
    services.add_event(
        case, CaseStage.GUIDANCE_REFERRED, date(2026, 5, 20), assigned_guidance_name="Rehber"
    )
    # Eski sürüm kaydı: planlanan ileri bir tarih (servis artık buna izin vermez).
    DisciplineEvent.objects.filter(case=case, stage=CaseStage.GUIDANCE_REFERRED).update(
        event_date=timezone.localdate() + timedelta(days=30)
    )
    case.refresh_from_db()
    services.add_event(
        case, CaseStage.GUIDANCE_RETURNED, date(2026, 5, 21), guidance_outcome="NO_RESULT"
    )
    case.refresh_from_db()
    assert case.current_stage == CaseStage.GUIDANCE_RETURNED
    # Yeni olayın kendisi yine ileri tarihli olamaz.
    with pytest.raises(ValueError, match="bugünden ileri"):
        _refer(case, on=_tomorrow())


def test_geri_alinan_asamanin_tarihi_sirayi_kilitlemez() -> None:
    """Yanlış (geç) tarihli sevk geri alınıp doğru (erken) tarihle yeniden girilebilmeli."""
    case = _case()
    _refer(case, on=date(2026, 5, 27))  # yanlış: geç tarih
    services.revert_stage(case, target_stage=CaseStage.PETITION, reason="Tarih yanlış girildi.")
    case.refresh_from_db()
    _refer(case, on=date(2026, 5, 19))  # doğru tarih — geri alınan olay sırayı bağlamaz
    assert case.current_stage == CaseStage.DECIDED
    # Kurula sevk tarihi = SON (en son KAYDEDİLEN) müdür kararı; geri alınmış, daha geç
    # tarihli sevk sayılmaz (CLAUDE.md §8). Olay tarihine göre sıralama 27.05 verirdi.
    assert selectors.committee_referred_on(case) == date(2026, 5, 19)


def test_geri_alinmis_gec_tarihli_sevk_gecerli_mudur_karari_sayilmaz() -> None:
    """Yanlış (geç tarihli) sevk geri alınıp müdür YAZILI UYARI verirse geçerli karar uyarıdır.

    Gözden geçirme (14.11.2026): "geçerli müdür kararı" olay TARİHİNE göre seçilince
    geri alınmış 27.05 tarihli sevk, 19.05 tarihli uyarı kararının önüne geçiyor; dosya
    "kurula sevkli" sayılıp uyarı kaydı reddediliyordu. Ölçüt kayıt sırasıdır.
    """
    case = _case()
    _refer(case, on=date(2026, 5, 27))
    services.revert_stage(case, target_stage=CaseStage.PETITION, reason="Yanlış karar.")
    case.refresh_from_db()
    _warn_close(case, on=date(2026, 5, 19))
    assert selectors.committee_referred_on(case) is None
    latest = selectors.latest_principal_decision_event(case)
    assert latest is not None and latest.event_date == date(2026, 5, 19)
    warning = services.issue_warning(
        case, student_id=_sid(case), warning_date=date(2026, 5, 19), summary="Yazılı uyarı."
    )
    assert warning.pk is not None


def test_gecmise_donuk_kayit_serbest() -> None:
    """Geç girilen eski tarihli kayıt meşru kullanımdır; yalnız sıra ve gelecek denetlenir."""
    case = _case(petition=date(2025, 10, 6))
    services.add_event(
        case, CaseStage.GUIDANCE_REFERRED, date(2025, 10, 7), assigned_guidance_name="Rehber"
    )
    case.refresh_from_db()
    assert case.current_stage == CaseStage.GUIDANCE_REFERRED


def test_uyari_tarihi_gelecekte_ya_da_dilekceden_once_olamaz() -> None:
    case = _case()
    _warn_close(case)
    with pytest.raises(ValueError, match="bugünden ileri"):
        services.issue_warning(case, student_id=_sid(case), warning_date=_tomorrow(), summary="x")
    with pytest.raises(ValueError, match="dilekçe tarihinden"):
        services.issue_warning(
            case, student_id=_sid(case), warning_date=date(2026, 5, 1), summary="x"
        )


def test_tedbir_kaldirma_tarihi_baslangictan_once_olamaz() -> None:
    case = _committee_case()
    p = services.create_precaution(
        case, student_id=_sid(case), start_date=date(2026, 5, 20), requested_days=3
    )
    with pytest.raises(ValueError, match="başlangıcından önce"):
        services.lift_precaution(p, lifted_on=date(2026, 5, 19))


def test_uzatma_ara_karari_gelecekte_olamaz_onay_ara_karardan_once_olamaz() -> None:
    case = _committee_case()
    with pytest.raises(ValueError, match="bugünden ileri"):
        services.create_extension(case, requested_days=5, reason="x", decided_on=_tomorrow())
    ext = services.create_extension(
        case, requested_days=5, reason="İfade gecikmesi", decided_on=date(2026, 5, 25)
    )
    with pytest.raises(ValueError, match="ara karar tarihinden önce"):
        services.approve_extension(ext, approved_on=date(2026, 5, 22))
    with pytest.raises(ValueError, match="bugünden ileri"):
        services.approve_extension(ext, approved_on=_tomorrow())


def test_onayli_uzatma_yeniden_onaylanamaz() -> None:
    """İkinci onay çağrısı onay tarihini sessizce değiştiriyordu."""
    case = _committee_case()
    ext = services.create_extension(
        case, requested_days=5, reason="İfade gecikmesi", decided_on=date(2026, 5, 25)
    )
    services.approve_extension(ext, approved_on=date(2026, 5, 25))
    with pytest.raises(ValueError, match="zaten onaylanmış"):
        services.approve_extension(ext, approved_on=date(2026, 5, 28))
    ext.refresh_from_db()
    assert ext.approved_on == date(2026, 5, 25)


# ---------------------------------------------------------------------------
# Tedbir başlangıcı tatil günü olabilir (bulgu 64 — gözden geçirmede GERİ ALINDI)
# ---------------------------------------------------------------------------
def test_tedbir_baslangici_tatil_gunu_olabilir() -> None:
    """md. 175/2: "tedbir kararının alınmasını izleyen en geç üç iş günü" KARAR gününden sayılır.

    Eski test (`test_tedbir_baslangici_is_gunu_olmali`) tatil günü başlangıcını
    reddediyordu. Gözden geçirme (14.11.2026) bunu geri aldırdı: modelde ayrı karar
    tarihi yok, başlangıç = karar günü; karar hafta sonu alınabilir (pansiyonlu okul) ve
    ilk iş gününe ötelemek işleme başlama son gününü bir gün GEÇ hesaplatır.
    """
    case = _committee_case()
    saturday = date(2026, 5, 23)
    precaution = services.create_precaution(
        case, student_id=_sid(case), start_date=saturday, requested_days=2
    )
    assert precaution.start_date == saturday
    # Cumartesi kararını izleyen 3 iş günü: Pzt 25, Sal 26, Çar 27.
    assert precaution.process_start_deadline == date(2026, 5, 27)
    # Pazartesiye ötelenseydi son gün 28.05 olurdu (bir gün geç).
    assert discipline_periods.precaution_process_start_deadline(
        date(2026, 5, 25), is_working_day=is_working_day
    ) == date(2026, 5, 28)


# ---------------------------------------------------------------------------
# Süre paneli (bulgu 14, 23, 65)
# ---------------------------------------------------------------------------
def test_panel_islem_basladiysa_isleme_baslama_uyarisi_vermez() -> None:
    """md. 175/2: tedbirden sonra 3 iş günü içinde işleme BAŞLANIR — başladıysa alarm yok."""
    pending = _case()
    services.create_precaution(
        pending, student_id=_sid(pending), start_date=date(2026, 5, 18), requested_days=10
    )
    today = date(2026, 5, 27)
    rows = _titles(today)
    assert any(sev == "GEÇTİ" and "işlemine başlanmalı" in title for sev, title in rows)

    # İşlem başladı (kurula sevk) → eşik düşer; tedbir bitiş satırı kalır.
    _refer(pending)
    rows = _titles(today)
    assert not any("işlemine başlanmalı" in title for _sev, title in rows)
    assert any("Tedbir süresi doluyor" in title for _sev, title in rows)


def test_panel_tedbir_satirinda_ogrenci_adi_var() -> None:
    student = StudentFactory(first_name="ÇAĞRI", last_name="IŞIKGÖZ")
    case = _case(student)
    services.create_precaution(
        case, student_id=student.pk, start_date=date(2026, 5, 18), requested_days=2
    )
    rows = _titles(date(2026, 5, 27))
    assert any("IŞIKGÖZ" in title for _sev, title in rows)


def test_panel_karari_girilmis_dosyada_kurul_karar_suresi_alarmi_vermez() -> None:
    case = _committee_case()
    _ensure_committee()
    horizon = date(2026, 6, 30)
    assert [c.pk for c, _d in selectors.cases_awaiting_committee_decision(horizon)] == [case.pk]
    decide(
        case,
        student_id=_sid(case),
        penalty_type=PenaltyType.REPRIMAND,
        decision_date=date(2026, 5, 22),
    )
    # Bütün suçlananlar hakkında karar var → "kurul karar süresi doluyor" satırı düşer
    # (COMMITTEE_DONE olayı henüz girilmemiş olsa da).
    assert selectors.cases_awaiting_committee_decision(horizon) == []


def test_panel_cok_ogrencili_dosyada_karari_eksik_ogrenci_varsa_alarm_surer() -> None:
    SchoolYearFactory()
    a, b = StudentFactory(), StudentFactory()
    case = services.create_case(
        petition_date=PETITION,
        petitioner_name="İdare",
        petitioner_role="IDARE",
        summary="x",
        student_ids=[a.pk, b.pk],
    )
    _refer(case)
    _ensure_committee()
    decide(
        case, student_id=a.pk, penalty_type=PenaltyType.REPRIMAND, decision_date=date(2026, 5, 22)
    )
    assert len(selectors.cases_awaiting_committee_decision(date(2026, 6, 30))) == 1


def test_panel_md197_askisindaki_karari_gosterir() -> None:
    case = _committee_case()
    _ensure_committee()
    decision = decide(
        case,
        student_id=_sid(case),
        penalty_type=PenaltyType.REPRIMAND,
        decision_date=date(2026, 5, 22),
    )
    services.record_principal_review(
        decision, action="RETURN", reason="Gerekçe yetersiz.", decided_on=date(2026, 5, 25)
    )
    rows = _titles(date(2026, 5, 26))
    assert any(sev == "BİLGİ" and "kurula iade edildi" in title for sev, title in rows)

    decision.refresh_from_db()
    services.record_principal_review(
        decision, action="REFER", reason="Kurul ısrar etti.", decided_on=date(2026, 5, 27)
    )
    rows = _titles(date(2026, 5, 28))
    assert any(sev == "BİLGİ" and "ilçe" in title for sev, title in rows)
    assert not any("kurula iade edildi" in title for _sev, title in rows)


# ---------------------------------------------------------------------------
# Süre uzatmasının geri alınması (bulgu 26)
# ---------------------------------------------------------------------------
def test_onaysiz_sure_uzatmasi_silinir_yenisi_girilebilir() -> None:
    case = _committee_case()
    ext = services.create_extension(
        case, requested_days=5, reason="Yanlış gün sayısı", decided_on=date(2026, 5, 25)
    )
    services.delete_extension(ext)
    assert selectors.get_extension(case, ext.pk) is None
    again = services.create_extension(
        case, requested_days=3, reason="Doğru kayıt", decided_on=date(2026, 5, 25)
    )
    assert again.requested_days == 3


def test_onayli_sure_uzatmasi_silinemez() -> None:
    case = _committee_case()
    ext = services.create_extension(
        case, requested_days=5, reason="İfade gecikmesi", decided_on=date(2026, 5, 25)
    )
    services.approve_extension(ext, approved_on=date(2026, 5, 25))
    with pytest.raises(ValueError, match="onayladığı süre uzatması silinemez"):
        services.delete_extension(ext)


def test_api_sure_uzatmasi_silme_ucu() -> None:
    case = _committee_case()
    ext = services.create_extension(
        case, requested_days=5, reason="Yanlış", decided_on=date(2026, 5, 25)
    )
    client = APIClient()
    base = f"/api/v1/discipline/cases/{case.pk}/extensions"
    assert client.delete(f"{base}/99999/").status_code == 404
    response = client.delete(f"{base}/{ext.pk}/")
    assert response.status_code == 204, response.content
    assert selectors.get_extension(case, ext.pk) is None


# ---------------------------------------------------------------------------
# Geri alınmış sevk (bulgu 29)
# ---------------------------------------------------------------------------
def test_geri_alinmis_sevk_kurula_sevk_sayilmaz() -> None:
    case = _committee_case()
    assert selectors.committee_referred_on(case) == REFERRED
    services.revert_stage(case, target_stage=CaseStage.PETITION, reason="Yanlış sevk.")
    case.refresh_from_db()
    assert selectors.committee_referred_on(case) is None
    assert selectors.committee_decision_deadline(case) is None
    _ensure_committee()
    with pytest.raises(ValueError, match=r"md\. 163/2"):
        decide(
            case,
            student_id=_sid(case),
            penalty_type=PenaltyType.REPRIMAND,
            decision_date=date(2026, 5, 22),
        )


def test_yeniden_sevkte_sure_uzatmasi_son_gunu_yeni_sevkten_hesaplanir() -> None:
    case = _committee_case()  # sevk 19.05 → son gün 02.06
    ext = services.create_extension(
        case, requested_days=5, reason="İfade gecikmesi", decided_on=date(2026, 5, 25)
    )
    services.approve_extension(ext, approved_on=date(2026, 5, 25))
    assert selectors.committee_decision_deadline(case) == date(2026, 6, 9)

    services.revert_stage(case, target_stage=CaseStage.PETITION, reason="Yanlış sevk.")
    case.refresh_from_db()
    _refer(case, on=date(2026, 5, 20))  # yeniden sevk → son gün 03.06, uzatmayla 10.06
    ext.refresh_from_db()
    assert ext.original_deadline == date(2026, 6, 3)
    assert ext.new_deadline == date(2026, 6, 10)
    assert selectors.committee_decision_deadline(case) == date(2026, 6, 10)


# ---------------------------------------------------------------------------
# İmha (bulgu 7, 43, 47)
# ---------------------------------------------------------------------------
def _setup_school() -> None:
    SchoolYearFactory()
    okul_setup.update_school_config(
        fields={
            "school_name": "Deneme Anadolu Lisesi",
            "district": "Menteşe",
            "principal_name": "ALİ ÖRNEK",
        }
    )


def _log(case: DisciplineCase, doc_type: str, student_id: int) -> None:
    services.log_generated_document(
        case,
        document_type=doc_type,
        title="Belge",
        generated_on=REFERRED,
        student_id=student_id,
    )


def test_uyari_kaydi_olmayan_dal_a_dosyasi_nakil_imhasina_girer() -> None:
    """md. 157/7-d: uyarı kaydı ayrıca açılmamış olsa da dosya "uyarı" dosyasıdır."""
    _setup_school()
    student = StudentFactory(first_name="BARIŞ", last_name="ÇELİK", status=StudentStatus.LEFT)
    case = _case(student)
    _warn_close(case)
    _log(case, DocumentType.WARNING_LETTER, student.pk)

    assert [s.student_id for s in purge_selectors.students_with_purgeable_warnings()] == [
        student.pk
    ]
    preview = purge_service.preview_student(student.pk)
    assert preview.whole_case_ids == [case.pk]
    assert len(preview.warnings) == 1
    assert preview.warnings[0].warning_id is None
    assert preview.warnings[0].warning_date == REFERRED  # müdür kararının tarihi

    record = purge_service.issue_record(student_id=student.pk, confirmed=True)
    result = purge_service.execute(token=record.token, confirmed=True)
    assert result.purged_cases == 1
    assert not DisciplineCase.all_objects.filter(pk=case.pk).exists()


def test_cok_ogrencili_dosyada_kayitsiz_ogrencinin_belgeleri_imha_edilir() -> None:
    _setup_school()
    leaving = StudentFactory(status=StudentStatus.LEFT)
    staying = StudentFactory()
    case = services.create_case(
        petition_date=PETITION,
        petitioner_name="İdare",
        petitioner_role="IDARE",
        summary="x",
        student_ids=[leaving.pk, staying.pk],
    )
    _warn_close(case)
    _log(case, DocumentType.WARNING_LETTER, leaving.pk)
    _log(case, DocumentType.WARNING_LETTER, staying.pk)

    record = purge_service.issue_record(student_id=leaving.pk, confirmed=True)
    result = purge_service.execute(token=record.token, confirmed=True)
    assert result.purged_cases == 0
    assert result.purged_documents == 1
    assert DisciplineCase.objects.filter(pk=case.pk).exists()
    assert selectors.documents_for_case(case).count() == 1


def test_tekil_onizleme_belge_sayisi_silinenle_ayni() -> None:
    """Bütünüyle silinecek dosyada önizleme, dosyanın TÜM kütük satırlarını sayar."""
    _setup_school()
    student = StudentFactory(status=StudentStatus.LEFT)
    case = _case(student)
    _warn_close(case)
    services.issue_warning(case, student_id=student.pk, warning_date=REFERRED, summary="x")
    _log(case, DocumentType.WARNING_LETTER, student.pk)
    _log(case, DocumentType.PARENT_MEETING, student.pk)
    _log(case, DocumentType.INDEX_SHEET, student.pk)  # uyarı belgesi değil ama dosyayla gider

    preview = purge_service.preview_student(student.pk)
    record = purge_service.issue_record(student_id=student.pk, confirmed=True)
    result = purge_service.execute(token=record.token, confirmed=True)
    assert preview.totals["documents"] == result.purged_documents == 3


def test_uygulanmayan_imhanin_tutanagi_kalici_klasore_yazilmaz(
    settings: Any, tmp_path: Path
) -> None:
    """Tutanak ikinci onaya kadar `imha/bekleyen/` altında durur; imha uygulanınca
    kalıcı klasöre taşınır — "imha edilmiştir" diyen sahipsiz tutanak kalmaz."""
    settings.MEDIA_ROOT = str(tmp_path)
    _setup_school()
    student = StudentFactory(status=StudentStatus.LEFT)
    case = _case(student)
    _warn_close(case)

    record = purge_service.issue_record(student_id=student.pk, confirmed=True)
    assert Path(record.stored_path).parent.name == "bekleyen"
    assert (tmp_path / record.stored_path).is_file()
    assert list((tmp_path / "imha").glob("*.pdf")) == []  # kalıcı klasörde henüz yok

    result = purge_service.execute(token=record.token, confirmed=True)
    assert Path(result.record_path).parent.name == "imha"
    assert (tmp_path / result.record_path).is_file()
    assert not (tmp_path / record.stored_path).exists()


def test_eskimis_bekleyen_tutanak_temizlenir(settings: Any, tmp_path: Path) -> None:
    import os
    import time

    settings.MEDIA_ROOT = str(tmp_path)
    _setup_school()
    student = StudentFactory(status=StudentStatus.LEFT)
    case = _case(student)
    _warn_close(case)

    first = purge_service.issue_record(student_id=student.pk, confirmed=True)
    fresh = tmp_path / first.stored_path
    # Aynı saniyede üretilen ikinci tutanak aynı adı alır; eskimiş kopyayı ayrı adla kur.
    stale = fresh.with_name("imha-tutanagi-20260101-000000.pdf")
    stale.write_bytes(fresh.read_bytes())
    old = time.time() - purge_service.TOKEN_MAX_AGE_SECONDS - 60
    os.utime(stale, (old, old))  # jetonun süresi dolmuş — bu tutanakla imha yapılamaz

    purge_service.issue_record(student_id=student.pk, confirmed=True)
    assert not stale.exists()
    assert fresh.exists()  # süresi dolmamış bekleyen tutanağa dokunulmaz


# ---------------------------------------------------------------------------
# Öğrenci silme koruması (13.11 denetimi)
# ---------------------------------------------------------------------------
def test_acik_dosyasi_olan_ogrenci_silinemez() -> None:
    case = _case()
    student = Student.objects.get(pk=_sid(case))
    with pytest.raises(ValueError, match="Ayrıldı"):
        persons_service.delete_student(student)
    assert Student.objects.filter(pk=student.pk).exists()


def test_uyari_kaydi_ya_da_karari_olan_ogrenci_silinemez() -> None:
    warned_case = _case()
    _warn_close(warned_case)
    services.issue_warning(
        warned_case, student_id=_sid(warned_case), warning_date=REFERRED, summary="x"
    )
    with pytest.raises(ValueError, match="uyarı kaydı"):
        persons_service.delete_student(Student.objects.get(pk=_sid(warned_case)))

    decided = _committee_case()
    _ensure_committee()
    decide(
        decided,
        student_id=_sid(decided),
        penalty_type=PenaltyType.REPRIMAND,
        decision_date=date(2026, 5, 22),
    )
    services.close_case(decided, override=True, override_reason="Test kapanışı.")
    with pytest.raises(ValueError, match="disiplin kararı"):
        persons_service.delete_student(Student.objects.get(pk=_sid(decided)))


def test_disiplin_kaydi_olmayan_ogrenci_silinir() -> None:
    student = StudentFactory()
    persons_service.delete_student(student)
    assert not Student.objects.filter(pk=student.pk).exists()


def test_api_ogrenci_silme_reddi_400_doner() -> None:
    case = _case()
    response = APIClient().delete(f"/api/v1/students/{_sid(case)}/")
    assert response.status_code == 400, response.content
    assert "Ayrıldı" in response.content.decode()
