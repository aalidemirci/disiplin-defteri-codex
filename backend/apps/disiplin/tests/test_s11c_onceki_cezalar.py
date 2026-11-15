"""Kullanıcı kararı 14.11.2026 — S11c: EK-1 "önceki cezalar" özeti bayatlayınca uyarı.

`prior_penalties_summary` karar anında derlenen, kullanıcının düzenleyebildiği bir
ANLIK KOPYADIR. Sonradan itirazla bozulan / md. 171/2 ile kaldırılan / değişen bir
önceki ceza kopyada eski hâliyle kalır. Karar: açık dosyada "özet güncel değil —
yeniden derle" uyarısı ve düğmesi; otomatik yeniden derleme YOK (kullanıcının
düzenlemesi ezilmesin); kapalı dosyada yalnız bilgi (kapanış dayanağı kilitli).

Bayatlık ölçütü kullanıcının metni DEĞİL, kopyanın derlendiği andaki otomatik derleme
(`prior_penalties_compiled`) ile güncel derlemenin karşılaştırmasıdır — elle düzenleme
bayat sayılmaz.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date
from pathlib import Path
from typing import Any

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.utils import timezone
from rest_framework.test import APIClient

from apps.disiplin import selectors, services
from apps.disiplin.models import (
    AppealResult,
    CaseNumberCounter,
    CaseStage,
    DisciplineCase,
    DisciplineDecision,
    PenaltyType,
    PrincipalDecision,
)
from apps.disiplin.serializers import DecisionSerializer
from apps.disiplin.services.decisions import ensure_decision_no, update_decision_narrative
from apps.disiplin.tests.factories import (
    SchoolYearFactory,
    StudentFactory,
    approve,
    decide,
    ensure_meeting,
)
from apps.okul.services import app_password
from apps.okul.tests._fixtures import TCKN_OGRENCI_1
from shared import crypto

pytestmark = pytest.mark.django_db


def _case(student_id: int) -> DisciplineCase:
    case = services.create_case(
        petition_date=date(2026, 5, 18),
        petitioner_name="İdare",
        petitioner_role="IDARE",
        summary="olay",
        student_ids=[student_id],
    )
    services.add_event(
        case,
        CaseStage.DECIDED,
        date(2026, 5, 19),
        override=True,
        override_reason="Rehberlik atlandı.",
        principal_decisions=[PrincipalDecision.DISCIPLINE_COMMITTEE],
    )
    return case


def _prior_penalty(
    student_id: int, penalty: str = PenaltyType.REPRIMAND, **kwargs: Any
) -> DisciplineDecision:
    """Önceki dosya: 22.05.2026'da verilmiş, onaylı ve tebliğli ceza."""
    d = decide(
        _case(student_id),
        student_id=student_id,
        penalty_type=penalty,
        decision_date=date(2026, 5, 22),
        **kwargs,
    )
    approve(d)
    services.notify_decision(d, notified_on=date(2026, 5, 22))
    return d


def _later_decision(student_id: int) -> DisciplineDecision:
    """Sonraki dosya: 03.06.2026 tarihli (onay bekleyen) karar — EK-1 özeti derlenir."""
    return decide(
        _case(student_id),
        student_id=student_id,
        penalty_type=PenaltyType.SHORT_TERM_SUSPENSION,
        suspension_days=2,
        decision_date=date(2026, 6, 3),
        md166_override_reason="Kurul fiili farklı değerlendirdi.",
    )


def _scenario() -> tuple[int, DisciplineDecision, DisciplineDecision]:
    SchoolYearFactory()
    sid = StudentFactory().pk
    prior = _prior_penalty(sid)
    later = _later_decision(sid)
    return sid, prior, later


def _overturn(prior: DisciplineDecision) -> None:
    ap = services.file_appeal(prior, filed_on=date(2026, 5, 25), filed_by_role="PARENT")
    services.resolve_appeal(ap, result=AppealResult.OVERTURNED, resulted_on=date(2026, 6, 5))


def _stale(decision: DisciplineDecision) -> bool:
    decision.refresh_from_db()
    return selectors.prior_penalties_summary_is_stale(decision)


# ---------------------------------------------------------------------------
# Bayatlık denetimi
# ---------------------------------------------------------------------------
def test_s11c_yeni_kararda_ozet_guncel_ve_derleme_izi_saklanir() -> None:
    _sid, _prior, later = _scenario()
    assert "22.05.2026 — Kınama" in later.prior_penalties_summary
    # İz karar no'suz imzadır; özet ise önceki kararın numarasını da taşır.
    assert later.prior_penalties_compiled == "22.05.2026 — Kınama"
    assert _stale(later) is False
    assert DecisionSerializer(later).data["prior_penalties_stale"] is False


def test_s11c_onceki_ceza_itirazla_bozulunca_sonraki_karar_bayat_isaretlenir() -> None:
    _sid, prior, later = _scenario()
    _overturn(prior)
    assert _stale(later) is True
    # Otomatik yeniden derleme YOK: kopya eski hâliyle durur.
    assert "Kınama" in later.prior_penalties_summary
    assert DecisionSerializer(later).data["prior_penalties_stale"] is True


def test_s11c_md171_kaldirma_bayatlatir_geri_alma_bayatligi_kaldirir() -> None:
    _sid, prior, later = _scenario()
    ap = services.file_appeal(prior, filed_on=date(2026, 5, 25), filed_by_role="PARENT")
    services.resolve_appeal(ap, result=AppealResult.UPHELD, resulted_on=date(2026, 6, 1))
    assert _stale(later) is False  # onanan ceza aynen yürürlükte
    services.remove_penalty(prior, removed_on=date(2026, 6, 10))
    assert _stale(later) is True
    services.undo_penalty_removal(prior)
    assert _stale(later) is False


def test_s11c_itirazla_degisen_onceki_ceza_bayatlatir() -> None:
    SchoolYearFactory()
    sid = StudentFactory().pk
    prior = _prior_penalty(sid, PenaltyType.SHORT_TERM_SUSPENSION, suspension_days=3)
    later = _later_decision(sid)
    ap = services.file_appeal(prior, filed_on=date(2026, 5, 25), filed_by_role="PARENT")
    services.resolve_appeal(
        ap,
        result=AppealResult.REDUCED,
        resulted_on=date(2026, 6, 5),
        new_penalty_type=PenaltyType.REPRIMAND,
    )
    assert _stale(later) is True
    services.recompile_prior_penalties(later)
    later.refresh_from_db()
    assert "22.05.2026 — Kınama" in later.prior_penalties_summary
    assert "uzaklaştırma" not in later.prior_penalties_summary


def test_s11c_sonradan_onaylanan_onceki_ceza_bayatlatir() -> None:
    """Onay değişikliği: kopya derlenirken onaysız olan önceki karar sonradan onaylanır."""
    SchoolYearFactory()
    sid = StudentFactory().pk
    prior = decide(
        _case(sid),
        student_id=sid,
        penalty_type=PenaltyType.REPRIMAND,
        decision_date=date(2026, 5, 22),
    )
    later = _later_decision(sid)
    assert later.prior_penalties_summary == ""
    approve(prior)
    assert _stale(later) is True


def test_s11c_yalniz_elle_duzenleme_bayat_sayilmaz() -> None:
    _sid, _prior, later = _scenario()
    update_decision_narrative(
        later, fields={"prior_penalties_summary": "Kınama almıştır. Genel durumu iyidir."}
    )
    assert _stale(later) is False
    # Kullanıcı özeti tümüyle silse de bayat değildir.
    update_decision_narrative(later, fields={"prior_penalties_summary": ""})
    assert _stale(later) is False


def test_s11c_elle_duzenlenmis_ozet_kaynak_degisince_bayatlar() -> None:
    _sid, prior, later = _scenario()
    update_decision_narrative(
        later, fields={"prior_penalties_summary": "Kınama almıştır. Genel durumu iyidir."}
    )
    _overturn(prior)
    assert _stale(later) is True


def test_s11c_sonraki_tarihli_ceza_onceki_ceza_sayilmaz() -> None:
    """Karar tarihinden SONRA verilmiş ceza "şimdiye kadar aldığı cezalar"a girmez;
    eski kararı da bayatlatmaz."""
    SchoolYearFactory()
    sid = StudentFactory().pk
    early = _prior_penalty(sid)  # 22.05.2026
    later = _later_decision(sid)  # 03.06.2026
    approve(later)
    assert _stale(early) is False
    assert early.prior_penalties_summary == ""


def test_s11c_silinmis_karar_bayat_isaretlenmez() -> None:
    _sid, prior, later = _scenario()
    services.delete_decision(later)
    _overturn(prior)
    later = DisciplineDecision.all_objects.get(pk=later.pk)
    assert selectors.prior_penalties_summary_is_stale(later) is False


def _same_day_pair() -> tuple[DisciplineDecision, DisciplineDecision]:
    """Kurul aynı toplantıda (03.06.2026) aynı öğrencinin iki dosyasını karara bağlar."""
    SchoolYearFactory()
    sid = StudentFactory().pk
    first, second = (
        decide(
            _case(sid),
            student_id=sid,
            penalty_type=PenaltyType.REPRIMAND,
            decision_date=date(2026, 6, 3),
        )
        for _ in range(2)
    )
    return first, second


def test_s11c_ayni_gun_iki_dosyada_yalniz_once_kaydedilen_onceki_ceza_sayilir() -> None:
    """Öncelik = tarih + kayıt sırası: iki karar birbirini karşılıklı "önceki ceza"
    sayamaz. Önce kaydedilenin özeti bayatlamaz; sonra kaydedileninki (ilk karar
    onaylanınca) bayatlar ve yeniden derlenince yalnız ilk kararı listeler."""
    first, second = _same_day_pair()
    assert first.prior_penalties_summary == second.prior_penalties_summary == ""
    approve(first)
    approve(second)

    assert _stale(first) is False
    assert _stale(second) is True
    services.recompile_prior_penalties(second)
    second.refresh_from_db()
    assert second.prior_penalties_summary.startswith("03.06.2026 — Kınama")
    assert second.prior_penalties_compiled == "03.06.2026 — Kınama"
    services.recompile_prior_penalties(first)
    first.refresh_from_db()
    assert first.prior_penalties_summary == ""
    assert _stale(first) is False
    assert _stale(second) is False


def test_s11c_ayni_gun_onceden_onayli_karar_yeni_kayitta_onceki_ceza_sayilir() -> None:
    """Kayıt anında aynı günün ONAYLI kararı zaten varsa yeni kararın özetine girer."""
    SchoolYearFactory()
    sid = StudentFactory().pk
    first = decide(
        _case(sid),
        student_id=sid,
        penalty_type=PenaltyType.REPRIMAND,
        decision_date=date(2026, 6, 3),
    )
    approve(first)
    second = decide(
        _case(sid),
        student_id=sid,
        penalty_type=PenaltyType.SHORT_TERM_SUSPENSION,
        suspension_days=1,
        decision_date=date(2026, 6, 3),
    )
    assert second.prior_penalties_summary.startswith("03.06.2026 — Kınama")
    assert second.prior_penalties_compiled == "03.06.2026 — Kınama"
    assert _stale(second) is False
    assert _stale(first) is False


def test_s11c_onceki_kararin_numarasi_sonradan_atanirsa_bayat_sayilmaz() -> None:
    """Bayatlık karar NUMARASINA duyarlı değildir: iz karar no'suz imzadır. Numara
    sonradan atanabilir/düzeltilebilir (`ensure_decision_no`, karar düzenleme) — ceza
    değişmiş değildir."""
    SchoolYearFactory()
    sid = StudentFactory().pk
    prior = _prior_penalty(sid)
    DisciplineDecision.objects.filter(pk=prior.pk).update(decision_no="")  # numarasız karar
    later = _later_decision(sid)
    assert later.prior_penalties_summary == "22.05.2026 — Kınama"
    assert later.prior_penalties_compiled == "22.05.2026 — Kınama"

    prior.refresh_from_db()
    ensure_decision_no(prior)  # evrak üretiminde olduğu gibi numara atanır
    prior.refresh_from_db()
    assert prior.decision_no

    assert _stale(later) is False
    # Yeniden derlenirse ÖZET numarayı taşır; iz numarasız kalır.
    services.recompile_prior_penalties(later)
    later.refresh_from_db()
    assert later.prior_penalties_summary == f"22.05.2026 — Kınama (karar no {prior.decision_no})"
    assert later.prior_penalties_compiled == "22.05.2026 — Kınama"
    assert _stale(later) is False


def test_s11c_karar_tarihi_duzenlenirse_iz_korunur_ozet_kendiliginden_degismez() -> None:
    """`update_decision` karar tarihini değiştirirse özet de iz de YENİDEN YAZILMAZ
    (kullanıcının düzenlemesi ezilmesin). "Önceki" cezalar kümesi yeni tarihe göre
    değişiyorsa uyarı çıkar ve kullanıcı yeniden derler; değişmiyorsa uyarı çıkmaz."""
    _sid, _prior, later = _scenario()  # önceki ceza 22.05.2026, bu karar 03.06.2026
    summary = later.prior_penalties_summary

    def edit(on: date) -> None:
        services.update_decision(
            later,
            penalty_type=PenaltyType.SHORT_TERM_SUSPENSION,
            suspension_days=2,
            # S8: karar tarihi toplantı tarihidir — tarih, başka toplantıya bağlanarak değişir.
            meeting=ensure_meeting(later.case, on),
        )
        later.refresh_from_db()

    edit(date(2026, 6, 5))  # küme aynı: önceki ceza hâlâ "önce"
    assert later.prior_penalties_summary == summary
    assert later.prior_penalties_compiled == "22.05.2026 — Kınama"
    assert _stale(later) is False

    edit(date(2026, 5, 20))  # karar öne alındı: 22.05 cezası artık "önceki" değil
    assert later.prior_penalties_summary == summary  # kendiliğinden yeniden derleme YOK
    assert later.prior_penalties_compiled == "22.05.2026 — Kınama"
    assert _stale(later) is True
    services.recompile_prior_penalties(later)
    later.refresh_from_db()
    assert later.prior_penalties_summary == ""
    assert _stale(later) is False


# ---------------------------------------------------------------------------
# Yeniden derleme
# ---------------------------------------------------------------------------
def test_s11c_yeniden_derleme_kopyayi_gunceller_ve_isareti_kaldirir() -> None:
    _sid, prior, later = _scenario()
    update_decision_narrative(
        later, fields={"prior_penalties_summary": "Kınama almıştır. Genel durumu iyidir."}
    )
    _overturn(prior)
    later.refresh_from_db()

    services.recompile_prior_penalties(later)

    later.refresh_from_db()
    assert later.prior_penalties_summary == ""  # bozulan ceza yazılmaz (md. 171/3)
    assert later.prior_penalties_compiled == ""
    assert _stale(later) is False


def test_s11c_yeniden_derleme_diger_anlati_alanlarina_dokunmaz() -> None:
    _sid, prior, later = _scenario()
    update_decision_narrative(later, fields={"committee_opinion": "Kurulun kanaati."})
    _overturn(prior)
    later.refresh_from_db()
    services.recompile_prior_penalties(later)
    later.refresh_from_db()
    assert later.committee_opinion == "Kurulun kanaati."
    assert later.penalty_type == PenaltyType.SHORT_TERM_SUSPENSION


def _close(case: DisciplineCase) -> None:
    services.close_case(case, override=True, override_reason="Test: erken kapatma.")


def test_s11c_kapali_dosyada_yeniden_derleme_reddedilir_bilgi_kalir() -> None:
    _sid, prior, later = _scenario()
    _close(later.case)
    _overturn(prior)  # itiraz sonucu kapanış kilidine tabi değildir
    later.refresh_from_db()
    with pytest.raises(ValueError, match="Dosya kapalı"):
        services.recompile_prior_penalties(later)
    later.refresh_from_db()
    assert "Kınama" in later.prior_penalties_summary  # kapanış dayanağı değişmedi
    assert _stale(later) is True  # yalnız bilgi


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------
def _url(decision: DisciplineDecision) -> str:
    return (
        f"/api/v1/discipline/cases/{decision.case_id}/decisions/{decision.pk}"
        "/recompile-prior-penalties/"
    )


def test_s11c_api_yeniden_derle_guncel_karari_doner(client: APIClient) -> None:
    _sid, prior, later = _scenario()
    _overturn(prior)
    listing = client.get(f"/api/v1/discipline/cases/{later.case_id}/decisions/").json()
    assert listing["decisions"][0]["prior_penalties_stale"] is True

    resp = client.post(_url(later), {}, format="json")

    assert resp.status_code == 200, resp.content
    body = resp.json()
    assert body["id"] == later.pk
    assert body["prior_penalties_summary"] == ""
    assert body["prior_penalties_stale"] is False
    assert "prior_penalties_compiled" not in body  # iç iz alanı yanıtta yer almaz


def test_s11c_api_kapali_dosyada_turkce_ret(client: APIClient) -> None:
    _sid, prior, later = _scenario()
    _close(later.case)
    _overturn(prior)
    resp = client.post(_url(later), {}, format="json")
    assert resp.status_code == 400, resp.content
    assert "Dosya kapalı" in resp.json()["message"]


def test_s11c_api_baska_dosyanin_karari_bulunamaz(client: APIClient) -> None:
    _sid, prior, later = _scenario()
    resp = client.post(
        f"/api/v1/discipline/cases/{prior.case_id}/decisions/{later.pk}/recompile-prior-penalties/",
        {},
        format="json",
    )
    assert resp.status_code == 404


def test_s11c_anlati_ucu_derleme_izini_degistiremez(client: APIClient) -> None:
    """`prior_penalties_compiled` istemciden yazılamaz (yoksa uyarı susturulabilirdi)."""
    _sid, _prior, later = _scenario()
    before = later.prior_penalties_compiled
    resp = client.post(
        f"/api/v1/discipline/cases/{later.case_id}/decisions/{later.pk}/narrative/",
        {"prior_penalties_summary": "Elle.", "prior_penalties_compiled": "sahte"},
        format="json",
    )
    assert resp.status_code == 200, resp.content
    later.refresh_from_db()
    assert later.prior_penalties_summary == "Elle."
    assert later.prior_penalties_compiled == before


# =============================================================================
# Göç — eski şema → göç → doğrula (dolu tablo, soft-delete, geri alma)
# =============================================================================
_BEFORE = [("disiplin", "0015_decision_board_penalty_first_return")]
_AFTER = [("disiplin", "0016_decision_prior_penalties_compiled")]


@pytest.fixture
def old_schema() -> Iterator[Any]:
    """Veritabanını S11c öncesi şemaya indirir; test bitince en güncel şemaya çıkarır."""
    executor = MigrationExecutor(connection)
    executor.migrate(_BEFORE)
    try:
        yield executor.loader.project_state(_BEFORE).apps
    finally:
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())


def _migrate(target: list[tuple[str, str]]) -> Any:
    executor = MigrationExecutor(connection)
    executor.migrate(target)
    return executor.loader.project_state(target).apps


@pytest.mark.django_db(transaction=True)
def test_s11c_goc_derleme_izini_mevcut_kopyanin_otomatik_satirlarindan_doldurur(
    old_schema: Any,
) -> None:
    student_model = old_schema.get_model("okul", "Student")
    case_model = old_schema.get_model("disiplin", "DisciplineCase")
    decision_model = old_schema.get_model("disiplin", "DisciplineDecision")

    def legacy(
        no: int, summary: str, *, deleted: bool = False, student: Any = None, **fields: Any
    ) -> int:
        case = case_model.objects.create(
            case_no=f"2025-2026-{no:04d}",
            petition_date=date(2026, 3, 2),
            petitioner_name="İdare",
            petitioner_role="IDARE",
            summary="Eski sürümden kalan dosya.",
        )
        row = decision_model.objects.create(
            case=case,
            student=student or student_model.objects.create(first_name="EMRE", last_name=str(no)),
            penalty_type="REPRIMAND",
            approval_authority="PRINCIPAL",
            prior_penalties_summary=summary,
            deleted_at=timezone.now() if deleted else None,
            **{"decision_date": date(2026, 3, 10), **fields},
        )
        return int(row.pk)

    auto = "22.05.2025 — Kınama (karar no 2024-2025/0003)\n10.11.2025 — Okul değiştirme"
    empty = legacy(1, "")
    untouched = legacy(2, auto)
    # Kullanıcı otomatik satırların altına "genel durum" eklemiş.
    appended = legacy(3, auto + "\nGenel durumu iyidir; derslerine devam etmektedir.")
    # Kullanıcı özeti tümüyle kendi cümlesiyle yazmış: otomatik satır yok. Derleme anı
    # bilinemez → iz, göç anındaki yürürlükteki önceki cezalarla dolar (bayat sayılmaz).
    repeat = student_model.objects.create(first_name="DENİZ", last_name="ÖRNEK")
    in_force: dict[str, Any] = {"approval_status": "APPROVED", "approved_at": date(2026, 2, 12)}
    legacy(7, "", student=repeat, decision_date=date(2026, 2, 10), decision_no="K-1", **in_force)
    legacy(  # md. 171/2 ile kaldırılmış: yazılmaz
        8,
        "",
        student=repeat,
        decision_date=date(2026, 2, 11),
        penalty_removed_on=date(2026, 3, 1),
        **in_force,
    )
    legacy(9, "", student=repeat, decision_date=date(2026, 2, 12))  # onaysız: yazılmaz
    legacy(10, "", student=repeat, decision_date=date(2026, 4, 1), **in_force)  # sonraki tarih
    legacy(11, "", student=repeat, decision_date=date(2026, 2, 13), deleted=True, **in_force)
    rewritten = legacy(4, "Daha önce bir kez kınama cezası almıştır.", student=repeat)
    rewritten_no_prior = legacy(12, "Daha önce ceza almamıştır.")
    soft_deleted = legacy(5, auto, deleted=True)
    windows_newlines = legacy(6, auto.replace("\n", "\r\n") + "\r\nGenel durumu iyidir.")
    # Kullanıcının TARİHLE başlayan kendi cümlesi otomatik derleme satırı DEĞİLDİR
    # (ceza etiketiyle bitmiyor): öğrencinin önceki cezası yok → iz boş, bayat sayılmaz.
    dated_sentence = legacy(13, "12.03.2026 — veliyle görüşüldü, uyarıldı.")
    # Otomatik satır yerinde düzeltilmiş (sonuna not eklenmiş): artık kullanıcı metnidir →
    # iz göç anındaki derlemeden gelir (bugün güncel kabul edilir).
    edited_line = legacy(14, "10.02.2026 — Kınama (3 gün ders dışı)", student=repeat)
    # Eski derleme tarih süzgeci kullanmıyordu: geriye tarihli girilen kararın özetinde
    # KARAR TARİHİNDEN SONRAKİ ceza satırı olabilir. O satır ize alınmaz — yoksa hiç
    # dokunulmamış özet yeni ölçüte göre (yalnız karar tarihine kadar) bayat görünürdü.
    later_line = legacy(
        15,
        "10.02.2026 — Kınama (karar no K-1)\n01.04.2026 — Kınama",
        student=repeat,
        decision_date=date(2026, 3, 5),
    )
    only_later_line = legacy(16, "01.04.2026 — Kınama", decision_date=date(2026, 3, 5))

    apps = _migrate(_AFTER)

    rows = {r.pk: r for r in apps.get_model("disiplin", "DisciplineDecision").objects.all()}
    # İz karar NO'SUZ imzadır (tarih + ceza türü): numara sonradan atanınca bayatlamaz.
    signature = "22.05.2025 — Kınama\n10.11.2025 — Okul değiştirme"
    assert rows[empty].prior_penalties_compiled == ""
    assert rows[untouched].prior_penalties_compiled == signature
    assert rows[appended].prior_penalties_compiled == signature
    assert rows[rewritten].prior_penalties_compiled == "10.02.2026 — Kınama"
    assert rows[rewritten_no_prior].prior_penalties_compiled == ""
    assert rows[soft_deleted].prior_penalties_compiled == signature
    assert rows[windows_newlines].prior_penalties_compiled == signature
    assert rows[dated_sentence].prior_penalties_compiled == ""
    assert rows[edited_line].prior_penalties_compiled == "10.02.2026 — Kınama"
    assert rows[later_line].prior_penalties_compiled == "10.02.2026 — Kınama"
    assert rows[only_later_line].prior_penalties_compiled == ""
    # Göçten sonra gerçek denetim: bu dört kayıt bayat GÖRÜNMEZ. Canlı model GÜNCEL şemayı
    # ister (0018 karara yeni sütun ekledi): önce uca çıkılır; geri alma aşağıda uçtan iner.
    leaf_executor = MigrationExecutor(connection)
    leaf_executor.migrate(leaf_executor.loader.graph.leaf_nodes())
    for pk in (dated_sentence, edited_line, later_line, only_later_line):
        live = DisciplineDecision.objects.get(pk=pk)
        assert selectors.prior_penalties_summary_is_stale(live) is False, pk
    assert rows[dated_sentence].prior_penalties_summary == (
        "12.03.2026 — veliyle görüşüldü, uyarıldı."
    )
    # Kullanıcının metni göçte değişmez.
    assert rows[appended].prior_penalties_summary.endswith("devam etmektedir.")
    assert rows[rewritten].prior_penalties_summary == "Daha önce bir kez kınama cezası almıştır."
    assert rows[untouched].penalty_type == "REPRIMAND"

    # Geri alınabilir: sütun düşer, özet metinleri yerinde durur.
    apps = _migrate(_BEFORE)
    old_rows = {r.pk: r for r in apps.get_model("disiplin", "DisciplineDecision").objects.all()}
    assert old_rows[appended].prior_penalties_summary.startswith(auto)
    with connection.cursor() as cursor:
        columns = {
            c.name
            for c in connection.introspection.get_table_description(
                cursor, "disiplin_disciplinedecision"
            )
        }
    assert "prior_penalties_compiled" not in columns


@pytest.mark.django_db(transaction=True)
def test_s11c_goc_sonrasi_eski_kayitta_bayatlik_gercek_servisle_dogru_hesaplanir() -> None:
    """Eski sürümde derlenmiş, önceki cezası ARTIK yürürlükte olmayan karar göçten sonra
    bayat görünür; önceki cezası aynen duran ve yalnız "genel durum" eklenmiş karar görünmez."""
    SchoolYearFactory()
    sid_a, sid_b = StudentFactory().pk, StudentFactory().pk
    prior_a = _prior_penalty(sid_a)
    _prior_penalty(sid_b)
    later_a, later_b = _later_decision(sid_a), _later_decision(sid_b)
    line = later_a.prior_penalties_summary
    assert line and later_b.prior_penalties_summary
    DisciplineDecision.objects.filter(pk=later_b.pk).update(
        prior_penalties_summary=later_b.prior_penalties_summary + "\nGenel durumu iyidir."
    )
    _overturn(prior_a)

    # Eski sürüm → yeni sürüm: sütunu düşürüp göçü yeniden uygula.
    _migrate(_BEFORE)
    _migrate(_AFTER)
    # Şemayı uca geri getir: `_BEFORE` 0017'yi de geri alır, `_AFTER` 0016'da bırakır. Sonraki
    # testler güncel şemayı (toplantı vekâlet alanları) bekler — S8'den beri karar toplantıya
    # bağlı girildiği için bu sızıntı görünür oldu.
    leaf_executor = MigrationExecutor(connection)
    leaf_executor.migrate(leaf_executor.loader.graph.leaf_nodes())

    later_a.refresh_from_db()
    later_b.refresh_from_db()
    assert line.startswith("22.05.2026 — Kınama (karar no ")
    assert later_a.prior_penalties_compiled == "22.05.2026 — Kınama"  # karar no'suz imza
    assert selectors.prior_penalties_summary_is_stale(later_a) is True
    assert selectors.prior_penalties_summary_is_stale(later_b) is False


# =============================================================================
# Göç — KİLİTLİ kip (uygulama parolası kurulu, anahtar bellekte yok)
# =============================================================================
_S11_ONCESI = [("disiplin", "0013_appeal_previous_suspension_days")]
_PAROLA = "Deneme-Parola-1"


@pytest.fixture
def kilitli_kip(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """`apps/okul/tests/test_app_password.py::guvenlik_ortami` kalıbı: test kendi güvenlik
    dosyası + yedek diziniyle, ucuz Argon2 profiliyle koşar; anahtar sıfırlanır."""
    monkeypatch.setenv(app_password.ENV_SECURITY_DIR, str(tmp_path / "veri"))
    monkeypatch.setenv(app_password.ENV_BACKUP_DIR, str(tmp_path / "yedek"))
    (tmp_path / "veri").mkdir()
    monkeypatch.setattr(
        crypto, "DEFAULT_KDF", crypto.KdfParams(time_cost=1, memory_cost=8, parallelism=1)
    )
    monkeypatch.setattr(app_password, "FAILURE_DELAYS", (0.0,))
    crypto.unload_key()
    yield
    crypto.unload_key()


def _raw_tckn(student_id: int) -> str:
    """ORM'i atlayarak sütunu olduğu gibi okur (şifre çözülmez)."""
    with connection.cursor() as cursor:
        cursor.execute("SELECT tckn FROM okul_student WHERE id = %s", [student_id])
        return str(cursor.fetchone()[0])


@pytest.mark.django_db(transaction=True)
def test_s11_gocleri_kilitli_kipte_sifreli_alana_dokunmadan_kosar(kilitli_kip: None) -> None:
    """Program açılışta `migrate --no-input` koşarken parola kuruluysa anahtar HENÜZ
    yoktur. 0014-0016 yalnız düz sütun okur: kilitliyken eski şemaya inip yeniden
    çıkmak hata vermez, şifreli sütunun ham değeri değişmez, veri göçleri dolar."""
    year = SchoolYearFactory()
    sid = StudentFactory(tckn=str(TCKN_OGRENCI_1)).pk
    _prior_penalty(sid)
    later = _later_decision(sid)
    assert later.prior_penalties_summary.startswith("22.05.2026 — Kınama")

    app_password.enable(password=_PAROLA)
    app_password.lock()
    assert crypto.is_unlocked() is False
    raw_before = _raw_tckn(sid)
    assert raw_before.startswith("gAAAA")  # gerçekten şifreli
    assert str(TCKN_OGRENCI_1) not in raw_before

    try:
        _migrate(_S11_ONCESI)  # ters göç de kilitliyken koşar
        assert "disiplin_casenumbercounter" not in connection.introspection.table_names()
        assert _raw_tckn(sid) == raw_before
    finally:
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())  # ileri göç (0014 → 0016)

    assert crypto.is_unlocked() is False
    assert _raw_tckn(sid) == raw_before
    assert CaseNumberCounter.objects.get(school_year=year).last_seq == 2  # 0014
    later.refresh_from_db()
    assert later.prior_penalties_compiled == "22.05.2026 — Kınama"  # 0016
    assert selectors.prior_penalties_summary_is_stale(later) is False
    assert services.generate_case_no().endswith("-0003")  # kilitliyken numara verilir
