"""`apps.disiplin` API testleri (F2-T5) — OYS yüzeyi, authsuz.

Uçtan uca yaşam döngüsü: dosya aç → sevk → karar → tebliğ → itiraz → kapat;
kurul/onur/karar-defteri uçları + yaklaşan süreler paneli + hata sözleşmesi.
"""

from __future__ import annotations

from datetime import date
from typing import Any

import pytest
from rest_framework.test import APIClient

from apps.disiplin import services
from apps.disiplin.models import CaseStage, DisciplineCase, PrincipalDecision
from apps.disiplin.tests.factories import (
    DisciplineDecisionTypeFactory,
    PersonnelFactory,
    SchoolYearFactory,
    StudentFactory,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def client() -> APIClient:
    return APIClient()


def _case_via_api(client: APIClient, student_id: int) -> dict[str, Any]:
    resp = client.post(
        "/api/v1/discipline/cases/",
        {
            "petition_date": "2026-05-18",
            "petitioner_name": "İdare",
            "petitioner_role": "IDARE",
            "summary": "Sınıfta uygunsuz davranış.",
            "student_ids": [student_id],
        },
        format="json",
    )
    assert resp.status_code == 201, resp.content
    data: dict[str, Any] = resp.json()
    return data


def _refer_to_committee(client: APIClient, case_id: int) -> None:
    resp = client.post(
        f"/api/v1/discipline/cases/{case_id}/events/",
        {
            "stage": CaseStage.DECIDED,
            "event_date": "2026-05-19",
            "override": True,
            "override_reason": "Rehberlik gerekmedi.",
            "principal_decisions": [PrincipalDecision.DISCIPLINE_COMMITTEE],
        },
        format="json",
    )
    assert resp.status_code == 201, resp.content


class TestCaseLifecycleApi:
    def test_uctan_uca_dosya_yasam_dongusu(self, client: APIClient) -> None:
        SchoolYearFactory()
        student = StudentFactory()
        case = _case_via_api(client, student.pk)
        case_id = case["id"]
        assert str(case["case_no"]).endswith("-0001")

        # Liste + filtre + öğrenci filtresi
        assert client.get("/api/v1/discipline/cases/").json()["count"] == 1
        assert client.get("/api/v1/discipline/cases/", {"student": student.pk}).json()["count"] == 1

        # Kurula sevk + karar
        _refer_to_committee(client, case_id)
        resp = client.post(
            f"/api/v1/discipline/cases/{case_id}/decisions/",
            {"student": student.pk, "penalty_type": "REPRIMAND", "decision_date": "2026-05-22"},
            format="json",
        )
        assert resp.status_code == 201
        decision = resp.json()
        assert decision["behavior_point_deduction"] == 10  # otomatik türetildi
        did = decision["id"]

        # Tebliğ → itiraz son günü snapshot
        resp = client.post(
            f"/api/v1/discipline/cases/{case_id}/decisions/{did}/notify/",
            {"notified_on": "2026-05-22"},
            format="json",
        )
        assert resp.json()["appeal_deadline"] == "2026-05-29"

        # İtiraz + sonuç (bozma → puan iadesi decision REJECTED)
        resp = client.post(
            f"/api/v1/discipline/cases/{case_id}/decisions/{did}/appeals/",
            {"filed_on": "2026-05-25", "filed_by_role": "PARENT", "filed_by_name": "Veli"},
            format="json",
        )
        assert resp.status_code == 201
        appeal_id = resp.json()["id"]
        resp = client.post(
            f"/api/v1/discipline/cases/{case_id}/appeals/{appeal_id}/resolve/",
            {"result": "OVERTURNED", "resulted_on": "2026-06-05"},
            format="json",
        )
        assert resp.status_code == 200
        assert resp.json()["result"] == "OVERTURNED"

        # Kapanış uygunluğu + kapat (itiraz kesinleşti → uygun)
        assert (
            client.get(f"/api/v1/discipline/cases/{case_id}/close-eligibility/").json()["eligible"]
            is True
        )
        resp = client.post(f"/api/v1/discipline/cases/{case_id}/close/", {}, format="json")
        assert resp.status_code == 200
        assert resp.json()["current_stage"] == "CLOSED"

    def test_gecersiz_gecis_sozlesmeli_400(self, client: APIClient) -> None:
        SchoolYearFactory()
        student = StudentFactory()
        case = _case_via_api(client, student.pk)
        resp = client.post(
            f"/api/v1/discipline/cases/{case['id']}/events/",
            {"stage": CaseStage.COMMITTEE_DONE, "event_date": "2026-05-19"},
            format="json",
        )
        assert resp.status_code == 400
        body = resp.json()
        assert body["code"] == "validation_error"
        assert "geçersiz" in body["message"].lower()

    def test_var_olmayan_dosya_404(self, client: APIClient) -> None:
        resp = client.get("/api/v1/discipline/cases/9999/")
        assert resp.status_code == 404
        assert resp.json()["code"] == "not_found"

    def test_triaj_onerisi(self, client: APIClient) -> None:
        SchoolYearFactory()
        student = StudentFactory()
        case1 = _case_via_api(client, student.pk)
        # İlk dosyada uyarı ver → ikinci dosyada triaj kurula yönlendirmeli.
        resp = client.post(
            f"/api/v1/discipline/cases/{case1['id']}/warnings/",
            {"student": student.pk, "warning_date": "2026-05-19", "summary": "İlk uyarı."},
            format="json",
        )
        assert resp.status_code == 201
        case2 = _case_via_api(client, student.pk)
        oneri = client.get(f"/api/v1/discipline/cases/{case2['id']}/triage-suggestion/").json()
        assert oneri[0]["should_route_to_committee"] is True
        assert oneri[0]["warning_count"] == 1


class TestParticipantAndPrecautionApi:
    def test_katilimci_ekle_sil(self, client: APIClient) -> None:
        SchoolYearFactory()
        student = StudentFactory()
        case = _case_via_api(client, student.pk)
        tanik = StudentFactory()
        resp = client.post(
            f"/api/v1/discipline/cases/{case['id']}/participants/",
            {"role": "WITNESS", "person_type": "STUDENT", "person_id": tanik.pk},
            format="json",
        )
        assert resp.status_code == 201
        pid = resp.json()["id"]
        listed = client.get(f"/api/v1/discipline/cases/{case['id']}/participants/").json()
        assert len(listed) == 2  # ACCUSED (otomatik) + WITNESS
        assert (
            client.delete(f"/api/v1/discipline/cases/{case['id']}/participants/{pid}/").status_code
            == 204
        )

    def test_tedbir_olustur_ve_kaldir(self, client: APIClient) -> None:
        SchoolYearFactory()
        student = StudentFactory()
        case = _case_via_api(client, student.pk)
        resp = client.post(
            f"/api/v1/discipline/cases/{case['id']}/precautions/",
            {"student": student.pk, "start_date": "2026-05-20", "requested_days": 5},
            format="json",
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["end_date"] == "2026-05-26"
        resp = client.post(
            f"/api/v1/discipline/cases/{case['id']}/precautions/{body['id']}/lift/",
            {"lifted_on": "2026-05-25"},
            format="json",
        )
        assert resp.json()["status"] == "LIFTED"

    def test_uzatma_kurula_sevkli_dosyada(self, client: APIClient) -> None:
        SchoolYearFactory()
        student = StudentFactory()
        case = _case_via_api(client, student.pk)
        _refer_to_committee(client, case["id"])
        resp = client.post(
            f"/api/v1/discipline/cases/{case['id']}/extensions/",
            {"requested_days": 5, "reason": "İfade gecikmesi", "decided_on": "2026-05-25"},
            format="json",
        )
        assert resp.status_code == 201
        ext = resp.json()
        assert ext["new_deadline"] == "2026-06-09"
        resp = client.post(
            f"/api/v1/discipline/cases/{case['id']}/extensions/{ext['id']}/approve/",
            {"approved_on": "2026-05-26"},
            format="json",
        )
        assert resp.json()["approved_by_principal"] is True


class TestCommitteeAndCouncilApi:
    def test_kurul_tanimi_ve_uyeler(self, client: APIClient) -> None:
        year = SchoolYearFactory()
        chair = PersonnelFactory()
        assert client.get("/api/v1/discipline/committee/").status_code == 204
        resp = client.post(
            "/api/v1/discipline/committee/",
            {"school_year": year.pk, "chair": chair.pk},
            format="json",
        )
        assert resp.status_code == 201
        resp = client.post(
            "/api/v1/discipline/committee/members/",
            {"member_type": "PARENT", "member_name": "HASAN VELİ"},
            format="json",
        )
        assert resp.status_code == 201
        body = client.get("/api/v1/discipline/committee/").json()
        assert len(body["members"]) == 1
        member_id = body["members"][0]["id"]
        assert (
            client.delete(f"/api/v1/discipline/committee/members/{member_id}/").status_code == 204
        )

    def test_uye_ekleme_yaniti_yeni_uyeyi_icerir(self, client: APIClient) -> None:
        """POST yanıtı üye eklendikten SONRAKİ listeyi taşımalı (bayat prefetch değil).

        FE listeyi doğrudan bu yanıtla tazeliyor; bayat gövde ilk üyeyi hiç
        göstermez, sonrakileri bir tur geriden gösterir.
        """
        year = SchoolYearFactory()
        chair = PersonnelFactory()
        client.post(
            "/api/v1/discipline/committee/",
            {"school_year": year.pk, "chair": chair.pk},
            format="json",
        )
        resp = client.post(
            "/api/v1/discipline/committee/members/",
            {"member_type": "PARENT", "member_name": "HASAN VELİ"},
            format="json",
        )
        assert resp.status_code == 201, resp.content
        assert [m["member_name"] for m in resp.json()["members"]] == ["HASAN VELİ"]

        resp = client.post(
            "/api/v1/discipline/committee/members/",
            {"member_type": "PARENT", "member_name": "FATMA VELİ"},
            format="json",
        )
        assert resp.status_code == 201, resp.content
        assert {m["member_name"] for m in resp.json()["members"]} == {"HASAN VELİ", "FATMA VELİ"}

    def test_karar_defteri_akisi(self, client: APIClient) -> None:
        year = SchoolYearFactory()
        attendees = [
            {"person_name": "BAŞKAN", "attendee_role": "VOTING_MEMBER", "is_chair": True},
            {"person_name": "ÜYE", "attendee_role": "VOTING_MEMBER", "is_chair": False},
        ]
        resp = client.post(
            "/api/v1/council/meetings/",
            {
                "school_year": year.pk,
                "council_type": "DISCIPLINE",
                "meeting_date": "2026-05-25",
                "attendees": attendees,
                "decision_text": "Gündem görüşüldü.",
            },
            format="json",
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["meeting_no_display"] == "T001"
        assert len(body["attendees"]) == 2
        # prefill boş kurulda boş liste döner
        assert (
            client.get("/api/v1/council/meetings/prefill/", {"council_type": "HONOR"}).json() == []
        )


class TestHonorApi:
    def test_onur_akisi(self, client: APIClient) -> None:
        year = SchoolYearFactory()
        chair = PersonnelFactory()
        client.post(
            "/api/v1/honor/board/", {"school_year": year.pk, "chair": chair.pk}, format="json"
        )
        student = StudentFactory()
        resp = client.post(
            "/api/v1/honor/certificates/",
            {
                "student": student.pk,
                "proposer_role": "TEACHER",
                "criteria": ["MANNERS"],
                "justification": "Görgü örnekliği.",
                "proposer_name": "AYŞE ÖĞRETMEN",
            },
            format="json",
        )
        assert resp.status_code == 201
        cid = resp.json()["id"]
        resp = client.post(
            f"/api/v1/honor/certificates/{cid}/recommend/",
            {"recommended_on": "2026-05-25"},
            format="json",
        )
        assert resp.json()["status"] == "HONOR_BOARD_RECOMMENDED"
        resp = client.post(
            f"/api/v1/honor/certificates/{cid}/award/", {"awarded_on": "2026-06-01"}, format="json"
        )
        assert resp.json()["status"] == "AWARDED"

    def test_kurul_uye_ekleme_yaniti_yeni_uyeyi_icerir(self, client: APIClient) -> None:
        """Onur kurulu üye ekleme yanıtı da güncel listeyi taşımalı (FE bununla tazeler)."""
        year = SchoolYearFactory()
        chair = PersonnelFactory()
        client.post(
            "/api/v1/honor/board/", {"school_year": year.pk, "chair": chair.pk}, format="json"
        )
        first = StudentFactory(class_level=9, class_section="A")
        second = StudentFactory(class_level=10, class_section="A")
        first_assembly = services.add_general_assembly_member(
            school_year_id=year.pk,
            student_id=first.pk,
            effective_from=year.start_date,
        )
        second_assembly = services.add_general_assembly_member(
            school_year_id=year.pk,
            student_id=second.pk,
            effective_from=year.start_date,
        )
        resp = client.post(
            "/api/v1/honor/board/members/",
            {
                "student": first.pk,
                "grade_level": 9,
                "assembly_member": first_assembly.pk,
            },
            format="json",
        )
        assert resp.status_code == 201, resp.content
        assert [m["member_student"] for m in resp.json()["members"]] == [first.pk]

        resp = client.post(
            "/api/v1/honor/board/members/",
            {
                "student": second.pk,
                "grade_level": 10,
                "assembly_member": second_assembly.pk,
            },
            format="json",
        )
        assert resp.status_code == 201, resp.content
        assert {m["member_student"] for m in resp.json()["members"]} == {first.pk, second.pk}

    def test_iki_kriter_kabul_edilir(self, client: APIClient) -> None:
        SchoolYearFactory()
        student = StudentFactory()
        resp = client.post(
            "/api/v1/honor/certificates/",
            {"student": student.pk, "proposer_role": "TEACHER", "criteria": ["MANNERS", "IT"]},
            format="json",
        )
        assert resp.status_code == 201
        assert resp.json()["criteria"] == ["MANNERS", "IT"]


class TestDecisionTypeAndDeadlinesApi:
    def test_karar_tipi_crud(self, client: APIClient) -> None:
        resp = client.post(
            "/api/v1/discipline/decision-types/",
            {"code": "KINAMA", "name": "Kınama", "sort_order": 10},
            format="json",
        )
        assert resp.status_code == 201
        assert client.get("/api/v1/discipline/decision-types/").json()["count"] == 1

    def test_pasif_karar_tipi_okunur_ve_yeniden_aktiflestirilir(self, client: APIClient) -> None:
        """Pasifleştirme tek yönlü kapan olmamalı: detay/PATCH pasifi de görür."""
        resp = client.post(
            "/api/v1/discipline/decision-types/",
            {"code": "UZAKLASTIRMA", "name": "Uzaklaştırma", "sort_order": 20},
            format="json",
        )
        assert resp.status_code == 201
        type_id = resp.json()["id"]
        url = f"/api/v1/discipline/decision-types/{type_id}/"
        assert client.patch(url, {"is_active": False}, format="json").status_code == 200

        # Liste varsayılanı pasifi gizler; `?all=1` hepsini verir.
        assert client.get("/api/v1/discipline/decision-types/").json()["count"] == 0
        assert client.get("/api/v1/discipline/decision-types/", {"all": "1"}).json()["count"] == 1

        # Detay ve güncelleme HER ZAMAN tüm kayıtlara erişir → geri açılabilir.
        assert client.get(url).status_code == 200
        resp = client.patch(url, {"is_active": True}, format="json")
        assert resp.status_code == 200, resp.content
        assert resp.json()["is_active"] is True

    def test_yaklasan_sureler_paneli(self, client: APIClient) -> None:
        SchoolYearFactory()
        student = StudentFactory()
        case = services.create_case(
            petition_date=date(2026, 5, 18),
            petitioner_name="A",
            petitioner_role="IDARE",
            summary="x",
            student_ids=[student.pk],
        )
        services.add_event(
            case,
            CaseStage.DECIDED,
            date(2026, 5, 19),
            override=True,
            override_reason="atla",
            principal_decisions=[PrincipalDecision.DISCIPLINE_COMMITTEE],
        )
        services.record_decision(
            case, student_id=student.pk, penalty_type="REPRIMAND", decision_date=date(2026, 5, 22)
        )
        items = client.get("/api/v1/disiplin/yaklasan-sureler/").json()
        assert any("tebliğ bekliyor" in i["title"] for i in items)
        assert all(
            {"severity", "case_no", "title", "due_date", "statute_ref", "link"} <= set(i)
            for i in items
        )


class TestAttachmentApi:
    PDF_BYTES = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF\n"

    def test_ek_yukle_indir_sil(
        self, client: APIClient, tmp_path: object, settings: object
    ) -> None:
        settings.MEDIA_ROOT = tmp_path  # type: ignore[attr-defined]
        SchoolYearFactory()
        student = StudentFactory()
        case = _case_via_api(client, student.pk)
        from io import BytesIO

        upload = BytesIO(self.PDF_BYTES)
        upload.name = "dilekce.pdf"
        resp = client.post(
            f"/api/v1/discipline/cases/{case['id']}/attachments/",
            {"file": upload, "file_type": "PETITION_SCAN"},
            format="multipart",
        )
        assert resp.status_code == 201
        aid = resp.json()["id"]
        assert resp.json()["is_duplicate"] is False

        download = client.get(f"/api/v1/discipline/cases/{case['id']}/attachments/{aid}/download/")
        assert download.status_code == 200
        assert b"".join(download.streaming_content) == self.PDF_BYTES  # type: ignore[attr-defined]

        assert (
            client.delete(f"/api/v1/discipline/cases/{case['id']}/attachments/{aid}/").status_code
            == 204
        )

    def test_gecersiz_tur_sozlesmeli_400(self, client: APIClient) -> None:
        SchoolYearFactory()
        student = StudentFactory()
        case = _case_via_api(client, student.pk)
        from io import BytesIO

        upload = BytesIO(b"duz metin")
        upload.name = "a.txt"
        resp = client.post(
            f"/api/v1/discipline/cases/{case['id']}/attachments/",
            {"file": upload},
            format="multipart",
        )
        assert resp.status_code == 400
        assert "PDF" in resp.json()["message"]


class TestKurulKarariEventApi:
    def test_kurul_karari_olayi_karar_tipiyle(self, client: APIClient) -> None:
        SchoolYearFactory()
        student = StudentFactory()
        case_data = _case_via_api(client, student.pk)
        case_id = case_data["id"]
        _refer_to_committee(client, case_id)
        dtype = DisciplineDecisionTypeFactory(code="KINAMA", name="Kınama")
        resp = client.post(
            f"/api/v1/discipline/cases/{case_id}/events/",
            {
                "stage": CaseStage.COMMITTEE_DONE,
                "event_date": "2026-05-26",
                "committee_decision_type": dtype.pk,
                "committee_decision_text": "Kınama verildi.",
            },
            format="json",
        )
        assert resp.status_code == 201, resp.content
        assert resp.json()["committee_decision_type_name"] == "Kınama"
        case = DisciplineCase.objects.get(pk=case_id)
        assert case.current_stage == CaseStage.COMMITTEE_DONE  # otomatik kapanmaz


class TestOysZarfParitesiApi:
    """F4 FE paritesi: decisions/extensions GET zarfları OYS ile birebir.

    OYS FE `disiplin/api.ts` DecisionsResponse `{decisions, behavior_points}`
    (md. 170 davranış puanı) ve ExtensionsResponse `{extensions,
    committee_referred_on, committee_decision_deadline}` (md. 192/3 izleme)
    bekler; karar satırında `is_final` (Form-16/17 kilidi UI ipucu) +
    `student_birth_date` (EK-1 anlatı prefill) bulunur.
    """

    def test_decisions_get_zarfi_ve_is_final(self, client: APIClient) -> None:
        SchoolYearFactory()
        student = StudentFactory(birth_date=date(2010, 3, 15))
        case = _case_via_api(client, student.pk)
        _refer_to_committee(client, case["id"])
        resp = client.post(
            f"/api/v1/discipline/cases/{case['id']}/decisions/",
            {"student": student.pk, "penalty_type": "REPRIMAND", "decision_date": "2026-05-22"},
            format="json",
        )
        assert resp.status_code == 201, resp.content

        body = client.get(f"/api/v1/discipline/cases/{case['id']}/decisions/").json()
        assert set(body.keys()) == {"decisions", "behavior_points"}
        assert len(body["decisions"]) == 1
        decision = body["decisions"][0]
        assert decision["is_final"] is False  # tebliğ yok → kesin değil
        assert decision["student_birth_date"] == "2010-03-15"
        # OYS semantiği (md. 170/171): bozulmamış her karar düşer (PENDING dahil);
        # yalnız itirazla BOZULAN karar puan iadesiyle hariç tutulur. Kınama = 10.
        assert body["behavior_points"] == {str(student.pk): 90}

    def test_extensions_get_zarfi(self, client: APIClient) -> None:
        SchoolYearFactory()
        student = StudentFactory()
        case = _case_via_api(client, student.pk)
        _refer_to_committee(client, case["id"])
        resp = client.post(
            f"/api/v1/discipline/cases/{case['id']}/extensions/",
            {"requested_days": 5, "reason": "İfade gecikmesi", "decided_on": "2026-05-25"},
            format="json",
        )
        assert resp.status_code == 201, resp.content

        body = client.get(f"/api/v1/discipline/cases/{case['id']}/extensions/").json()
        assert set(body.keys()) == {
            "extensions",
            "committee_referred_on",
            "committee_decision_deadline",
        }
        assert len(body["extensions"]) == 1
        assert body["committee_referred_on"] == "2026-05-19"
        # Onaylı uzatma yok → son gün ham 10 iş günü hesabından gelir (dolu olmalı).
        assert body["committee_decision_deadline"] is not None


class TestErrorContract:
    """`{code, message(TÜRKÇE), fields}` sözleşmesi — 404 dahil (tasarım §4.3)."""

    def test_router_404_turkce_ve_not_found_kodlu(self, client: APIClient) -> None:
        # ModelViewSet lookup'ı Http404 fırlatır: DRF varsayılanı İngilizce
        # ("No … matches the given query.") ve kodsuzdur; sözleşmeye çevrilmeli.
        resp = client.get("/api/v1/discipline/decision-types/9999/")
        assert resp.status_code == 404
        body = resp.json()
        assert body["code"] == "not_found"
        assert body["fields"] == {}
        assert body["message"] == "Kayıt bulunamadı."

    def test_view_detayi_korunur(self, client: APIClient) -> None:
        resp = client.get("/api/v1/discipline/cases/9999/")
        assert resp.status_code == 404
        assert resp.json() == {
            "code": "not_found",
            "message": "Disiplin dosyası bulunamadı.",
            "fields": {},
        }
