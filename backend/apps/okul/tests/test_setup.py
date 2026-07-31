"""`apps.okul.services.setup` — kurum yapılandırması + antet kimliği (F1-T3).

OYS `core.services.school_config` ikamesi: env fallback YOK (tek kaynak DB),
`get_letterhead_identity` sihirbazda girilen kurum bilgisini döner ve
`shared.letterhead.letterhead_context`'e parametre olarak beslenir.
"""

from __future__ import annotations

import pytest

from apps.okul.models import SchoolConfig
from apps.okul.services import setup as setup_service
from shared.letterhead import letterhead_context


@pytest.mark.django_db
class TestUpdateSchoolConfig:
    def test_satir_yoksa_olusturur(self) -> None:
        config = setup_service.update_school_config(
            fields={"school_name": "Deneme Anadolu Lisesi", "district": "Menteşe"}
        )
        assert config.pk == SchoolConfig.SINGLETON_PK
        assert SchoolConfig.objects.count() == 1
        assert config.school_name == "Deneme Anadolu Lisesi"

    def test_whitelist_disi_alan_yazilmaz(self) -> None:
        setup_service.update_school_config(
            fields={"school_name": "Deneme", "setup_completed": True}
        )
        # setup_completed sihirbaz tamamlama servisiyle değişir; düz update ile DEĞİL.
        assert SchoolConfig.load().setup_completed is False

    def test_mevcut_satiri_gunceller(self) -> None:
        setup_service.update_school_config(fields={"school_name": "Eski Ad"})
        setup_service.update_school_config(fields={"school_name": "Yeni Ad"})
        assert SchoolConfig.objects.count() == 1
        assert SchoolConfig.load().school_name == "Yeni Ad"


@pytest.mark.django_db
class TestLetterheadIdentity:
    def test_kurulmamis_okulda_yer_tutucular(self) -> None:
        identity = setup_service.get_letterhead_identity()
        assert identity["school_name"] == "Okul"
        assert identity["district"] == ""
        assert identity["principal_name"] == ""

    def test_yapilandirilmis_okul_bilgisi_doner(self) -> None:
        setup_service.update_school_config(
            fields={
                "school_name": "Deneme Anadolu Lisesi",
                "province": "Muğla",
                "district": "Menteşe",
                "principal_name": "ALİ ÖRNEK",
            }
        )
        identity = setup_service.get_letterhead_identity()
        assert identity == {
            "school_name": "Deneme Anadolu Lisesi",
            "province": "Muğla",
            "district": "Menteşe",
            "principal_name": "ALİ ÖRNEK",
        }

    def test_shared_letterhead_ile_uctan_uca(self) -> None:
        """Kimlik → `shared.letterhead` antet bağlamı (evrak motoru sözleşmesi)."""
        setup_service.update_school_config(
            fields={
                "school_name": "Deneme Anadolu Lisesi",
                "district": "Menteşe",
                "principal_name": "ALİ ÖRNEK",
            }
        )
        identity = setup_service.get_letterhead_identity()
        context = letterhead_context(
            school_name=identity["school_name"],
            district=identity["district"],
            principal_name=identity["principal_name"],
        )
        assert context["authority"] == "Menteşe KAYMAKAMLIĞI"
        assert context["principal_name"] == "ALİ ÖRNEK"


@pytest.mark.django_db
class TestSetupCompletion:
    def test_kurulum_tamamlama(self) -> None:
        setup_service.update_school_config(fields={"school_name": "Deneme"})
        setup_service.mark_setup_completed()
        assert SchoolConfig.load().setup_completed is True

    def test_kurulum_tamamlama_satir_yoksa_da_calisir(self) -> None:
        setup_service.mark_setup_completed()
        assert SchoolConfig.load().setup_completed is True

    def test_kurulum_tamamlama_idempotent(self) -> None:
        setup_service.mark_setup_completed()
        setup_service.mark_setup_completed()
        assert SchoolConfig.objects.count() == 1
        assert SchoolConfig.load().setup_completed is True
