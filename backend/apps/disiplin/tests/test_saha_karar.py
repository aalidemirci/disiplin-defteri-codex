"""14.11.2026 saha (Windows uçtan uca) testi — karar/itiraz grubunun regresyon testleri.

Her test önce kırmızıya düşürüldü, sonra düzeltildi. Kod: SK-<bulgu no>.

- SK-2  : itiraz kurulu uzaklaştırma GÜN SAYISINI indirebilir (md. 200/1-ç, 164/2).
- SK-28 : md. 197 — "beklemede"ye çekilen ya da ilçe kararı yanlış girilen karar
          yeniden ilçeye sevk edilebilir / ilçe değişikliği girilebilir (tek yönlü kapan).
- SK-29 : geri alınmış sevkte karar girilemez / geri yüklenemez (md. 163/2).
- SK-59 : uzaklaştırma başlangıcı onay tarihinden önce kalamaz (md. 169/2-a).
- SK-YIL: ders yılı bitişinden sonra verilen ceza biten yıla sayılır (md. 166, 170).
"""

from __future__ import annotations

from datetime import date

import pytest
from rest_framework.test import APIClient

from apps.disiplin import selectors, services
from apps.disiplin.models import (
    AppealResult,
    CaseStage,
    DecisionApprovalStatus,
    DisciplineCase,
    DisciplineDecision,
    PenaltyType,
    PrincipalDecision,
)
from apps.disiplin.services.decisions import update_decision_narrative
from apps.disiplin.tests.factories import SchoolYearFactory, StudentFactory, approve
from apps.okul.models import SchoolYear

pytestmark = pytest.mark.django_db

BASE = "/api/v1/discipline/cases/"


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


def _suspension(case: DisciplineCase, sid: int, *, days: int = 5) -> DisciplineDecision:
    return services.record_decision(
        case,
        student_id=sid,
        penalty_type=PenaltyType.SHORT_TERM_SUSPENSION,
        suspension_days=days,
        decision_date=date(2026, 5, 22),
    )


@pytest.fixture
def client() -> APIClient:
    return APIClient(raise_request_exception=False)


# --- SK-2: itiraz kurulu gün sayısını indirir (md. 200/1-ç "değiştirir") ------------
def test_sk2_itiraz_kurulu_uzaklastirma_gun_sayisini_indirebilir() -> None:
    case, sid = _committee_case()
    d = _suspension(case, sid, days=5)
    approve(d)
    update_decision_narrative(d, fields={}, enforcement_start_date=date(2026, 6, 1))
    services.notify_decision(d, notified_on=date(2026, 5, 25))
    appeal = services.file_appeal(d, filed_on=date(2026, 5, 26), filed_by_role="PARENT")

    services.resolve_appeal(
        appeal,
        result=AppealResult.REDUCED,
        resulted_on=date(2026, 6, 5),
        new_penalty_type=PenaltyType.SHORT_TERM_SUSPENSION,
        new_suspension_days=2,
    )

    d.refresh_from_db()
    appeal.refresh_from_db()
    assert d.penalty_type == PenaltyType.SHORT_TERM_SUSPENSION
    assert d.suspension_days == 2
    # Tür değişmedi: puan (md. 170) ve uygulama başlangıcı korunur; bitiş günü yeni
    # gün sayısından hesaplanır.
    assert d.behavior_point_deduction == 20
    assert d.enforcement_start_date == date(2026, 6, 1)
    assert d.is_enforced is True
    # Eski ceza itiraz kaydında tam olarak (tür + gün) saklanır.
    assert appeal.previous_penalty_type == PenaltyType.SHORT_TERM_SUSPENSION
    assert appeal.previous_suspension_days == 5


def test_sk2_ayni_tur_ayni_gun_degisiklik_sayilmaz() -> None:
    case, sid = _committee_case()
    d = _suspension(case, sid, days=3)
    approve(d)
    services.notify_decision(d, notified_on=date(2026, 5, 25))
    appeal = services.file_appeal(d, filed_on=date(2026, 5, 26), filed_by_role="PARENT")
    with pytest.raises(ValueError, match="gün sayısı"):
        services.resolve_appeal(
            appeal,
            result=AppealResult.REDUCED,
            resulted_on=date(2026, 6, 5),
            new_penalty_type=PenaltyType.SHORT_TERM_SUSPENSION,
            new_suspension_days=3,
        )
    appeal.refresh_from_db()
    assert appeal.result == AppealResult.PENDING


def test_sk2_uzaklastirma_disinda_ayni_tur_reddedilir() -> None:
    case, sid = _committee_case()
    d = services.record_decision(
        case, student_id=sid, penalty_type=PenaltyType.REPRIMAND, decision_date=date(2026, 5, 22)
    )
    approve(d)
    services.notify_decision(d, notified_on=date(2026, 5, 25))
    appeal = services.file_appeal(d, filed_on=date(2026, 5, 26), filed_by_role="PARENT")
    with pytest.raises(ValueError, match="aynı olamaz"):
        services.resolve_appeal(
            appeal,
            result=AppealResult.REDUCED,
            resulted_on=date(2026, 6, 5),
            new_penalty_type=PenaltyType.REPRIMAND,
        )


def test_sk2_tur_degisikliginde_eski_gun_sayisi_da_saklanir() -> None:
    case, sid = _committee_case()
    d = _suspension(case, sid, days=4)
    approve(d)
    services.notify_decision(d, notified_on=date(2026, 5, 25))
    appeal = services.file_appeal(d, filed_on=date(2026, 5, 26), filed_by_role="PARENT")
    services.resolve_appeal(
        appeal,
        result=AppealResult.REDUCED,
        resulted_on=date(2026, 6, 5),
        new_penalty_type=PenaltyType.REPRIMAND,
    )
    appeal.refresh_from_db()
    assert appeal.previous_penalty_type == PenaltyType.SHORT_TERM_SUSPENSION
    assert appeal.previous_suspension_days == 4


def test_sk2_api_gun_indirimi_kabul_edilir_ve_eski_gun_doner(client: APIClient) -> None:
    case, sid = _committee_case()
    d = _suspension(case, sid, days=5)
    approve(d)
    services.notify_decision(d, notified_on=date(2026, 5, 25))
    appeal = services.file_appeal(d, filed_on=date(2026, 5, 26), filed_by_role="PARENT")
    r = client.post(
        f"{BASE}{case.pk}/appeals/{appeal.pk}/resolve/",
        {
            "result": "REDUCED",
            "resulted_on": "2026-06-05",
            "new_penalty_type": "SHORT_TERM_SUSPENSION",
            "new_suspension_days": 2,
        },
        format="json",
    )
    assert r.status_code == 200, r.content
    assert r.json()["previous_suspension_days"] == 5
    d.refresh_from_db()
    assert d.suspension_days == 2


def test_sk2_ilce_kurulu_onayda_gun_sayisini_degistirebilir() -> None:
    """md. 197 sevkinde ilçe kurulu "onaylar veya değiştirir" (md. 200/1-a) — aynı yol."""
    case, sid = _committee_case()
    d = _suspension(case, sid, days=5)
    services.record_principal_review(
        d, action="RETURN", reason="Ağır.", decided_on=date(2026, 5, 25)
    )
    services.record_principal_review(
        d, action="REFER", reason="Israr.", decided_on=date(2026, 5, 27)
    )
    services.set_decision_approval(
        d,
        approval_status="APPROVED",
        approved_on=date(2026, 6, 3),
        modified_penalty_type=PenaltyType.SHORT_TERM_SUSPENSION,
        modified_suspension_days=2,
    )
    d.refresh_from_db()
    assert d.suspension_days == 2
    assert d.approval_status == DecisionApprovalStatus.APPROVED


# --- SK-28: md. 197 tek yönlü kapanlar ---------------------------------------------
def test_sk28_iade_sonrasi_beklemeye_alinan_karar_ilceye_sevk_edilebilir() -> None:
    case, sid = _committee_case()
    d = _suspension(case, sid)
    services.record_principal_review(
        d, action="RETURN", reason="Ağır.", decided_on=date(2026, 5, 25)
    )
    # Kurul yeniden görüşsün diye karar "onay bekliyor"a alındı (düzenleme yalnız böyle açılır).
    services.set_decision_approval(d, approval_status="PENDING")
    assert d.approval_status == DecisionApprovalStatus.PENDING

    services.record_principal_review(
        d, action="REFER", reason="Israr.", decided_on=date(2026, 5, 27)
    )

    d.refresh_from_db()
    assert d.approval_status == DecisionApprovalStatus.REFERRED_TO_DISTRICT
    assert d.referred_to_district is True
    assert "Ağır." in d.return_reason and "Israr." in d.return_reason


def test_sk28_iade_edilmemis_karar_ilceye_sevk_edilemez() -> None:
    """md. 197 invariantı korunur: sevk yalnız önce iade edilmiş kararda."""
    case, sid = _committee_case()
    d = _suspension(case, sid)
    with pytest.raises(ValueError, match="iade"):
        services.record_principal_review(
            d, action="REFER", reason="x", decided_on=date(2026, 5, 27)
        )


def test_sk28_beklemeye_alinan_karar_ikinci_kez_iade_edilemez() -> None:
    """md. 197 "bir defa daha görüşülmek üzere" — beklemeye alma iade hakkını yenilemez."""
    case, sid = _committee_case()
    d = _suspension(case, sid)
    services.record_principal_review(
        d, action="RETURN", reason="Ağır.", decided_on=date(2026, 5, 25)
    )
    services.set_decision_approval(d, approval_status="PENDING")
    with pytest.raises(ValueError, match="bir kez"):
        services.record_principal_review(
            d, action="RETURN", reason="Yine.", decided_on=date(2026, 5, 27)
        )


def test_sk28_yanlis_girilen_ilce_karari_duzeltilebilir() -> None:
    case, sid = _committee_case()
    d = _suspension(case, sid, days=5)
    services.record_principal_review(
        d, action="RETURN", reason="Ağır.", decided_on=date(2026, 5, 25)
    )
    services.record_principal_review(
        d, action="REFER", reason="Israr.", decided_on=date(2026, 5, 27)
    )
    # Yanlış giriş: "ilçe aynen onayladı".
    services.set_decision_approval(d, approval_status="APPROVED", approved_on=date(2026, 6, 3))

    # Geri alma: ilçeye gitmiş karar "müdür onayı bekliyor"a DEĞİL "ilçe kurulunda"ya döner.
    services.set_decision_approval(d, approval_status="PENDING")
    d.refresh_from_db()
    assert d.approval_status == DecisionApprovalStatus.REFERRED_TO_DISTRICT
    assert d.approved_at is None
    assert d.is_enforced is False
    assert d not in selectors.decisions_awaiting_approval()

    # Doğru giriş: ilçe kurulu cezayı değiştirerek onayladı (md. 200/1-a).
    services.set_decision_approval(
        d,
        approval_status="APPROVED",
        approved_on=date(2026, 6, 3),
        modified_penalty_type=PenaltyType.SHORT_TERM_SUSPENSION,
        modified_suspension_days=1,
    )
    d.refresh_from_db()
    assert d.approval_status == DecisionApprovalStatus.APPROVED
    assert d.suspension_days == 1


def test_sk28_ilce_onayi_girilmis_kararda_degisiklik_dogrudan_da_girilebilir() -> None:
    """Onay mercii kurul = `referred_to_district`; anlık duruma (REFERRED) bağlı değil."""
    case, sid = _committee_case()
    d = _suspension(case, sid, days=5)
    services.record_principal_review(
        d, action="RETURN", reason="Ağır.", decided_on=date(2026, 5, 25)
    )
    services.record_principal_review(
        d, action="REFER", reason="Israr.", decided_on=date(2026, 5, 27)
    )
    services.set_decision_approval(d, approval_status="APPROVED", approved_on=date(2026, 6, 3))
    services.set_decision_approval(
        d,
        approval_status="APPROVED",
        approved_on=date(2026, 6, 3),
        modified_penalty_type=PenaltyType.REPRIMAND,
    )
    d.refresh_from_db()
    assert d.penalty_type == PenaltyType.REPRIMAND


def test_sk28_mudur_okul_kurulu_kararini_degistiremez() -> None:
    """md. 197 invariantı korunur: ilçeye gitmemiş müdür onaylı kararda değişiklik yok."""
    case, sid = _committee_case()
    d = _suspension(case, sid)
    with pytest.raises(ValueError, match="197"):
        services.set_decision_approval(
            d,
            approval_status="APPROVED",
            approved_on=date(2026, 5, 25),
            modified_penalty_type=PenaltyType.REPRIMAND,
        )


# --- SK-29: geri alınmış sevkte karar yok (md. 163/2) -------------------------------
def test_sk29_sevk_geri_alinmis_dosyada_karar_girilemez() -> None:
    case, sid = _committee_case()
    services.revert_stage(case, target_stage=CaseStage.PETITION, reason="Yanlış sevk.")
    with pytest.raises(ValueError, match="163/2"):
        services.record_decision(
            case,
            student_id=sid,
            penalty_type=PenaltyType.REPRIMAND,
            decision_date=date(2026, 5, 22),
        )
    assert not DisciplineDecision.objects.filter(case=case).exists()


def test_sk29_sevk_geri_alinmis_dosyada_silinmis_karar_geri_yuklenemez() -> None:
    case, sid = _committee_case()
    d = services.record_decision(
        case, student_id=sid, penalty_type=PenaltyType.REPRIMAND, decision_date=date(2026, 5, 22)
    )
    services.delete_decision(d)
    services.revert_stage(case, target_stage=CaseStage.PETITION, reason="Yanlış sevk.")
    deleted = selectors.get_any_decision(case, d.pk)
    assert deleted is not None
    with pytest.raises(ValueError, match="163/2"):
        services.restore_decision(deleted)
    assert not DisciplineDecision.objects.filter(case=case).exists()


def test_sk29_kurul_tamamlandi_asamasinda_karar_girilebilir() -> None:
    """Denetim yalnız sevk ÖNCESİ aşamaları kapatır; kurul sonrası giriş açık kalır."""
    case, sid = _committee_case()
    case.current_stage = CaseStage.COMMITTEE_DONE
    case.save(update_fields=["current_stage"])
    d = services.record_decision(
        case, student_id=sid, penalty_type=PenaltyType.REPRIMAND, decision_date=date(2026, 5, 22)
    )
    assert d.pk is not None


# --- SK-59: uygulama başlangıcı onaydan önce kalamaz (md. 169/2-a) ------------------
def test_sk59_onay_tarihi_onceden_girilmis_baslangictan_sonra_olamaz() -> None:
    """Karar formunda başlangıç baştan girilince onay denetimi atlanıyordu."""
    case, sid = _committee_case()
    d = services.record_decision(
        case,
        student_id=sid,
        penalty_type=PenaltyType.SHORT_TERM_SUSPENSION,
        suspension_days=2,
        enforcement_start_date=date(2026, 5, 25),
        decision_date=date(2026, 5, 22),
    )
    with pytest.raises(ValueError, match="başlangıcı"):
        services.set_decision_approval(d, approval_status="APPROVED", approved_on=date(2026, 5, 27))
    d.refresh_from_db()
    assert d.approval_status == DecisionApprovalStatus.PENDING
    # Başlangıç onay günü ya da sonrasıysa onay kabul edilir.
    services.set_decision_approval(d, approval_status="APPROVED", approved_on=date(2026, 5, 25))
    assert d.approval_status == DecisionApprovalStatus.APPROVED


# --- SK-YIL: ders yılı bitişinden sonra verilen ceza (md. 166 ile aynı yıl tanımı) ---
def test_skyil_ders_yili_bitisinden_sonra_verilen_ceza_puani_dusurur() -> None:
    case, sid = _committee_case()  # 2025-2026: 08.09.2025 – 26.06.2026
    d = services.record_decision(
        case, student_id=sid, penalty_type=PenaltyType.REPRIMAND, decision_date=date(2026, 6, 30)
    )
    approve(d)
    year = SchoolYear.objects.get(name="2025-2026")
    # md. 166 seçicisi bu cezayı zaten 2025-2026'ya sayıyor; puan da aynı yılı görmeli.
    prior = selectors.same_year_prior_penalty(sid, date(2026, 7, 2))
    assert prior is not None and prior.pk == d.pk
    assert selectors.behavior_point_for_student(sid) == 90
    assert selectors.behavior_point_for_student(sid, year.pk) == 90


def test_skyil_yaz_karari_yeni_yila_degil_biten_yila_sayilir() -> None:
    case, sid = _committee_case()
    d = services.record_decision(
        case, student_id=sid, penalty_type=PenaltyType.REPRIMAND, decision_date=date(2026, 6, 30)
    )
    approve(d)
    old = SchoolYear.objects.get(name="2025-2026")
    new = SchoolYear.objects.create(
        name="2026-2027", start_date=date(2026, 9, 7), end_date=date(2027, 6, 25), is_active=False
    )
    assert selectors.behavior_point_for_student(sid, old.pk) == 90
    assert selectors.behavior_point_for_student(sid, new.pk) == 100
    # Yeni yılın ilk gününden itibaren md. 166 da eski cezayı "aynı yıl" saymaz.
    assert selectors.same_year_prior_penalty(sid, date(2026, 9, 8)) is None
