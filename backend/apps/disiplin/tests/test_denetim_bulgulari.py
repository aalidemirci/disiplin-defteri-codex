"""27.09.2026 kod denetimi — doğrulanmış bulguların regresyon testleri.

Her test önce kırmızıya düşürüldü, sonra düzeltildi. Kod: D-S (servis/seçici),
D-A (API ucu).
"""

from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest
from rest_framework.test import APIClient

from apps.disiplin import selectors, services
from apps.disiplin.models import (
    AppealResult,
    CaseStage,
    DisciplineCase,
    DisciplineDecision,
    PenaltyType,
    PrincipalDecision,
)
from apps.disiplin.tests.factories import SchoolYearFactory, StudentFactory, approve

pytestmark = pytest.mark.django_db


def _committee_case() -> tuple[DisciplineCase, int]:
    SchoolYearFactory()
    s = StudentFactory()
    case = services.create_case(
        petition_date=date(2026, 5, 18),
        petitioner_name="A",
        petitioner_role="IDARE",
        summary="x",
        student_ids=[s.pk],
    )
    services.add_event(
        case,
        CaseStage.DECIDED,
        date(2026, 5, 19),
        override=True,
        override_reason="Rehberlik atlandı.",
        principal_decisions=[PrincipalDecision.DISCIPLINE_COMMITTEE],
    )
    return case, s.pk


@pytest.fixture
def client() -> APIClient:
    return APIClient(raise_request_exception=False)


# --- D-S1: tebliğ/itiraz sonrası ceza onay ucundan değişmez (md. 169/4) -----------
def test_ds1_itiraz_sonucu_kesinlesen_ceza_onay_ucundan_degismez() -> None:
    case, sid = _committee_case()
    d = services.record_decision(
        case,
        student_id=sid,
        penalty_type=PenaltyType.SCHOOL_CHANGE,
        decision_date=date(2026, 5, 22),
    )
    approve(d)
    services.notify_decision(d, notified_on=date(2026, 5, 25))
    appeal = services.file_appeal(d, filed_on=date(2026, 5, 26), filed_by_role="PARENT")
    services.resolve_appeal(
        appeal,
        result=AppealResult.REDUCED,
        resulted_on=date(2026, 6, 5),
        new_penalty_type=PenaltyType.SHORT_TERM_SUSPENSION,
        new_suspension_days=3,
    )
    with pytest.raises(ValueError, match="169/4"):
        services.set_decision_approval(
            d,
            approval_status="APPROVED",
            approved_on=date(2026, 6, 10),
            modified_penalty_type=PenaltyType.REPRIMAND,
        )


def test_ds1_tebligden_sonra_ceza_onay_ucundan_degismez() -> None:
    case, sid = _committee_case()
    d = services.record_decision(
        case,
        student_id=sid,
        penalty_type=PenaltyType.SCHOOL_CHANGE,
        decision_date=date(2026, 5, 22),
    )
    approve(d)
    services.notify_decision(d, notified_on=date(2026, 5, 25))
    with pytest.raises(ValueError, match="169/4"):
        services.set_decision_approval(
            d,
            approval_status="APPROVED",
            approved_on=date(2026, 5, 22),
            modified_penalty_type=PenaltyType.REPRIMAND,
        )


# --- D-S2: onay tarihi tebliğ tarihinin ötesine taşınamaz (md. 163/2) ------------
def test_ds2_teblig_sonrasi_onay_tarihi_teblig_sonrasina_tasinamaz() -> None:
    case, sid = _committee_case()
    d = services.record_decision(
        case, student_id=sid, penalty_type=PenaltyType.REPRIMAND, decision_date=date(2026, 5, 22)
    )
    approve(d)
    services.notify_decision(d, notified_on=date(2026, 5, 25))
    with pytest.raises(ValueError, match="tebliğ"):
        services.set_decision_approval(d, approval_status="APPROVED", approved_on=date(2026, 6, 15))


# --- D-S3: karar düzenlemesi de sevk tarihinden önceki tarihi reddeder ------------
def test_ds3_update_decision_sevkten_onceki_tarihi_reddeder() -> None:
    case, sid = _committee_case()
    d = services.record_decision(
        case, student_id=sid, penalty_type=PenaltyType.REPRIMAND, decision_date=date(2026, 5, 22)
    )
    with pytest.raises(ValueError, match="sevk"):
        services.update_decision(
            d, penalty_type=PenaltyType.REPRIMAND, decision_date=date(2026, 5, 1)
        )


# --- D-S4: imha önizlemesinde kapanış günü yerel saatten (§7.1) -------------------
def test_ds4_imha_onizleme_kapanis_gunu_yerel_tarih() -> None:
    from apps.disiplin.selectors.purge import case_purge_item

    SchoolYearFactory()
    s = StudentFactory()
    case = services.create_case(
        petition_date=date(2026, 5, 18),
        petitioner_name="A",
        petitioner_role="IDARE",
        summary="x",
        student_ids=[s.pk],
    )
    case.closed_at = datetime(2026, 6, 20, 1, 30, tzinfo=ZoneInfo("Europe/Istanbul"))
    case.current_stage = CaseStage.CLOSED
    case.save(update_fields=["closed_at", "current_stage"])
    case.refresh_from_db()
    assert case_purge_item(case).closed_on == date(2026, 6, 20)


# --- D-S5: geri alınan yazılı uyarı kararı "uyarı almış" saydırmaz (md. 157/7-e) ---
def test_ds5_geri_alinan_yazili_uyari_sayilmaz() -> None:
    SchoolYearFactory()
    s = StudentFactory()
    case = services.create_case(
        petition_date=date(2026, 5, 18),
        petitioner_name="A",
        petitioner_role="IDARE",
        summary="x",
        student_ids=[s.pk],
    )
    services.add_event(
        case,
        CaseStage.DECIDED,
        date(2026, 5, 19),
        override=True,
        override_reason="r",
        principal_decisions=[PrincipalDecision.WRITTEN_WARNING],
    )
    case.refresh_from_db()
    assert case.current_stage == CaseStage.CLOSED
    services.revert_stage(case, target_stage=CaseStage.PETITION, reason="yanlış giriş")
    services.add_event(
        case,
        CaseStage.DECIDED,
        date(2026, 5, 20),
        override=True,
        override_reason="r",
        principal_decisions=[PrincipalDecision.DISCIPLINE_COMMITTEE],
    )
    assert selectors.student_discipline_history(s.pk).warning_count == 0


# --- D-A1: tür hatalı gövde 500 değil 400 ------------------------------------------
@pytest.mark.parametrize(
    ("yol", "govde"),
    [
        ("warnings/", {"student": None, "warning_date": "2026-05-20"}),
        ("extensions/", {"requested_days": None, "reason": "x"}),
    ],
)
def test_da1_tur_hatali_govde_400(client: APIClient, yol: str, govde: dict[str, object]) -> None:
    case, _sid = _committee_case()
    r = client.post(f"/api/v1/discipline/cases/{case.pk}/{yol}", govde, format="json")
    assert r.status_code == 400, (r.status_code, r.content[:200])


def test_da1_imha_tutanak_null_id_400(client: APIClient) -> None:
    r = client.post(
        "/api/v1/disiplin/imha/tutanak/", {"case_ids": [None], "onay": True}, format="json"
    )
    assert r.status_code == 400, (r.status_code, r.content[:200])


# --- D-A2: çok parçalı "false" MEM onay kapısını aşamaz (md. 175/2) ---------------
def test_da2_multipart_false_mem_onayini_asamaz(client: APIClient) -> None:
    case, sid = _committee_case()
    p = services.create_precaution(
        case, student_id=sid, start_date=date(2026, 5, 20), requested_days=5
    )
    r = client.post(
        f"/api/v1/discipline/cases/{case.pk}/precautions/{p.pk}/extend/",
        {"additional_days": "3", "mne_notified": "false"},
    )
    assert r.status_code == 400, (r.status_code, r.content[:200])


# --- D-A3: dosya araması Türkçe büyük/küçük harfe duyarsız -------------------------
def test_da3_dosya_aramasi_turkce_harf_duyarsiz(client: APIClient) -> None:
    SchoolYearFactory()
    s = StudentFactory()
    services.create_case(
        petition_date=date(2026, 5, 18),
        petitioner_name="Şükrü Işık",
        petitioner_role="IDARE",
        summary="x",
        student_ids=[s.pk],
    )
    for arama in ("Şükrü", "şükrü", "IŞIK", "ışık"):
        data = client.get("/api/v1/discipline/cases/", {"search": arama}).json()
        assert data["count"] == 1, arama


# --- D-K1: nakil imhası tutanaktan sonra dosyaya eklenen öğrenciyi silmez (md. 157/7-d)
def test_dk1_tutanak_sonrasi_eklenen_ogrenci_imha_kapsamini_bozar() -> None:
    from unittest import mock

    from apps.disiplin.models import (
        DisciplineWarning,
        ParticipantPersonType,
        ParticipantRole,
    )
    from apps.disiplin.services import purge as purge_service
    from apps.disiplin.tests.test_purge import _setup_school, _warning_case
    from apps.okul.models import Student, StudentStatus

    _setup_school()
    case, giden = _warning_case()
    Student.objects.filter(pk=giden.pk).update(status=StudentStatus.LEFT)
    kalan = StudentFactory(first_name="OKULDA", last_name="KALAN")
    with mock.patch("django.utils.timezone.localdate", return_value=date(2026, 4, 1)):
        record = purge_service.issue_record(
            student_id=giden.pk, transfer_date=date(2026, 3, 30), confirmed=True
        )
        services.add_participant(
            case,
            role=ParticipantRole.ACCUSED,
            person_type=ParticipantPersonType.STUDENT,
            person_id=kalan.pk,
        )
        services.issue_warning(
            case, student_id=kalan.pk, warning_date=date(2026, 3, 31), summary="Dikkat."
        )
        with pytest.raises(ValueError, match="kapsamı değişti"):
            purge_service.execute(token=record.token, confirmed=True)
    assert DisciplineWarning.all_objects.filter(student_id=kalan.pk).exists()


# --- Karar 1 (27.09.2026): yeniden sevkte kurul süresi SON sevkten işler (md. 192/3)
def test_karar1_yeniden_sevkte_son_sevk_esas() -> None:
    case, sid = _committee_case()  # ilk sevk 19.05
    services.revert_stage(case, target_stage=CaseStage.PETITION, reason="rehberliğe dönüldü")
    services.add_event(
        case,
        CaseStage.DECIDED,
        date(2026, 6, 1),
        override=True,
        override_reason="r",
        principal_decisions=[PrincipalDecision.DISCIPLINE_COMMITTEE],
    )
    assert selectors.committee_referred_on(case) == date(2026, 6, 1)
    with pytest.raises(ValueError, match="sevk"):
        services.record_decision(
            case,
            student_id=sid,
            penalty_type=PenaltyType.REPRIMAND,
            decision_date=date(2026, 5, 25),
        )


def test_karar1_sevk_geri_alinip_uyariya_donerse_sevk_yok() -> None:
    case, _sid = _committee_case()
    services.revert_stage(case, target_stage=CaseStage.PETITION, reason="yanlış giriş")
    services.add_event(
        case,
        CaseStage.DECIDED,
        date(2026, 5, 20),
        override=True,
        override_reason="r",
        principal_decisions=[PrincipalDecision.WRITTEN_WARNING],
    )
    assert selectors.committee_referred_on(case) is None


# --- Karar 2 (27.09.2026): okul değiştirmede süresinde itiraz → uygulama bekler (md. 172/2-ç)
def _okul_degistirme_teblig() -> DisciplineDecision:
    case, sid = _committee_case()
    d = services.record_decision(
        case,
        student_id=sid,
        penalty_type=PenaltyType.SCHOOL_CHANGE,
        decision_date=date(2026, 5, 22),
    )
    approve(d)
    services.notify_decision(d, notified_on=date(2026, 5, 25))
    d.refresh_from_db()
    return d


def test_karar2_okul_degistirme_onayla_uygulanir_itirazla_bekler_onanirsa_doner() -> None:
    d = _okul_degistirme_teblig()
    assert d.is_enforced is True
    appeal = services.file_appeal(d, filed_on=date(2026, 5, 26), filed_by_role="PARENT")
    d.refresh_from_db()
    assert d.is_enforced is False  # itiraz sonuçlanana kadar ceza uygulanmaz
    services.resolve_appeal(appeal, result=AppealResult.UPHELD, resulted_on=date(2026, 6, 5))
    d.refresh_from_db()
    assert d.is_enforced is True


def test_karar2_suresi_disinda_itiraz_uygulamayi_durdurmaz() -> None:
    d = _okul_degistirme_teblig()
    services.file_appeal(d, filed_on=date(2026, 6, 20), filed_by_role="PARENT")
    d.refresh_from_db()
    assert d.is_enforced is True


def test_karar2_itiraz_degistirirse_yeni_ceza_uygulanir() -> None:
    d = _okul_degistirme_teblig()
    appeal = services.file_appeal(d, filed_on=date(2026, 5, 26), filed_by_role="PARENT")
    services.resolve_appeal(
        appeal,
        result=AppealResult.REDUCED,
        resulted_on=date(2026, 6, 5),
        new_penalty_type=PenaltyType.REPRIMAND,
    )
    d.refresh_from_db()
    assert d.penalty_type == PenaltyType.REPRIMAND
    assert d.is_enforced is True


# --- Karar 3 (27.09.2026): kapalı dosyada kapanış dayanağı kilitli ------------------
def _kapali_dosyada_teblig_edilmis_karar() -> DisciplineDecision:
    from django.utils import timezone

    case, sid = _committee_case()
    d = services.record_decision(
        case, student_id=sid, penalty_type=PenaltyType.REPRIMAND, decision_date=date(2026, 5, 22)
    )
    approve(d)
    services.notify_decision(d, notified_on=date(2026, 5, 25))
    case.closed_at = timezone.now()
    case.current_stage = CaseStage.CLOSED
    case.save(update_fields=["closed_at", "current_stage"])
    d.refresh_from_db()
    return d


def test_karar3_kapali_dosyada_onay_ve_teblig_degismez() -> None:
    d = _kapali_dosyada_teblig_edilmis_karar()
    with pytest.raises(ValueError, match="kapal"):
        services.set_decision_approval(d, approval_status="APPROVED", approved_on=date(2026, 5, 23))
    with pytest.raises(ValueError, match="kapal"):
        services.notify_decision(d, notified_on=date(2026, 5, 26))


def test_karar3_kapali_dosyada_sonradan_gelen_islemler_serbest() -> None:
    d = _kapali_dosyada_teblig_edilmis_karar()
    # Süre dışı itiraz kaydı + sonucu, e-Okul ve md. 171/2 ceza kaldırma serbest.
    appeal = services.file_appeal(d, filed_on=date(2026, 6, 20), filed_by_role="PARENT")
    services.resolve_appeal(appeal, result=AppealResult.UPHELD, resulted_on=date(2026, 6, 25))
    services.confirm_e_school_entry(d, processed_on=date(2026, 6, 26))
