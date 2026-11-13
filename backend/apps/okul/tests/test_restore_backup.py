"""Yedekten geri yükleme — doğrulama ve bekletme (apps/okul/services/restore_backup.py).

Bekletilen yedeğin açılışta yerine konması `desktop/tests/test_restore.py` içinde
sınanır; burada "hangi dosya bekletilir, hangisi reddedilir" kuralları ve uç yüzeyi
vardır. Sahte veritabanları ham `sqlite3` ile kurulur: servis de yedeği Django
bağlantısıyla değil ham dosya olarak inceler.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from pathlib import Path

import pytest
from desktop.backup_crypto import encrypt_bytes, ensure_public_config, load_public_key
from desktop.restore import PENDING_DB_NAME, PENDING_STATE_NAME, apply_pending_restore
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APIClient

from apps.okul.services import app_password, restore_backup
from shared import crypto

PAROLA = "Deneme-Parola-1"
URL = "/api/v1/security/backups/"


@pytest.fixture(autouse=True)
def ortam(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv(app_password.ENV_SECURITY_DIR, str(tmp_path / "veri"))
    monkeypatch.setenv(app_password.ENV_BACKUP_DIR, str(tmp_path / "yedek"))
    (tmp_path / "veri").mkdir()
    (tmp_path / "yedek").mkdir()
    monkeypatch.setattr(
        crypto, "DEFAULT_KDF", crypto.KdfParams(time_cost=1, memory_cost=8, parallelism=1)
    )
    monkeypatch.setattr(app_password, "FAILURE_DELAYS", (0.0,))
    crypto.unload_key()
    yield
    crypto.unload_key()


def _sahte_db(
    path: Path,
    *,
    parmak_izi: str = "",
    gocler: tuple[tuple[str, str], ...] = (("okul", "0001_initial"),),
    okul_adi: str = "Deneme Lisesi",
) -> bytes:
    """Disiplin Defteri veritabanına benzeyen en küçük SQLite dosyası."""
    conn = sqlite3.connect(path)
    try:
        conn.execute("CREATE TABLE django_migrations (app TEXT, name TEXT)")
        conn.executemany("INSERT INTO django_migrations VALUES (?, ?)", gocler)
        conn.execute("CREATE TABLE okul_schoolconfig (school_name TEXT, app_password_hash TEXT)")
        conn.execute("INSERT INTO okul_schoolconfig VALUES (?, ?)", (okul_adi, parmak_izi))
        conn.commit()
    finally:
        conn.close()
    icerik = path.read_bytes()
    path.unlink()
    return icerik


class _Yedek:
    """Parolalı kurulumun `.ddbak` yedeği ve onu açan sırlar."""

    def __init__(self, tmp_path: Path, *, sifreli_alanlar: bool = True) -> None:
        self.anahtar = crypto.new_data_key()
        self.kurtarma = app_password.generate_recovery_key()
        durum = app_password._build_state(self.anahtar, password=PAROLA, recovery_key=self.kurtarma)
        self.baslik = json.dumps(durum).encode("utf-8")
        kaynak = tmp_path / "kaynak"
        kaynak.mkdir(exist_ok=True)
        ensure_public_config(kaynak, self.anahtar, replace=True)
        duz = _sahte_db(
            tmp_path / "sahte.sqlite3",
            parmak_izi=crypto.key_fingerprint(self.anahtar) if sifreli_alanlar else "",
        )
        self.kapsayici = encrypt_bytes(duz, load_public_key(kaynak), recovery_header=self.baslik)


def _okul_adi(path: Path) -> str:
    conn = sqlite3.connect(path)
    try:
        return str(conn.execute("SELECT school_name FROM okul_schoolconfig").fetchone()[0])
    finally:
        conn.close()


# ----------------------------------------------------------------- düz yedek


def test_duz_yedek_dogrulanir_ve_bekletilir(tmp_path: Path) -> None:
    icerik = _sahte_db(tmp_path / "y.sqlite3")

    sonuc = restore_backup.stage_restore(icerik)

    veri = tmp_path / "veri"
    assert sonuc["pending_restore"] is True
    assert "yeniden" in sonuc["message"]
    assert sonuc["warning"] == ""
    assert (veri / PENDING_DB_NAME).read_bytes() == icerik
    assert not (veri / PENDING_STATE_NAME).exists()
    assert list(veri.glob("*.tmp")) == []


def test_bekletme_calisan_veritabanina_dokunmaz(tmp_path: Path) -> None:
    canli = tmp_path / "veri" / "db.sqlite3"
    canli.write_bytes(b"canli veri")

    restore_backup.stage_restore(_sahte_db(tmp_path / "y.sqlite3"))

    assert canli.read_bytes() == b"canli veri"


@pytest.mark.parametrize(
    ("icerik", "mesaj"),
    [
        (b"PK\x03\x04 bir excel dosyasi", "tanınmadı"),
        (b"", "tanınmadı"),
        (b"SQLite format 3\x00" + b"\x00" * 200, "açılamadı|bozuk"),
    ],
)
def test_taninmayan_ya_da_bozuk_dosya_reddedilir(tmp_path: Path, icerik: bytes, mesaj: str) -> None:
    with pytest.raises(restore_backup.RestoreError, match=mesaj):
        restore_backup.stage_restore(icerik)

    assert not (tmp_path / "veri" / PENDING_DB_NAME).exists()
    assert list((tmp_path / "veri").glob("*.tmp")) == []


def test_baska_programin_sqlite_dosyasi_reddedilir(tmp_path: Path) -> None:
    yol = tmp_path / "baska.sqlite3"
    conn = sqlite3.connect(yol)
    conn.execute("CREATE TABLE notlar (metin TEXT)")
    conn.commit()
    conn.close()

    with pytest.raises(restore_backup.RestoreError, match="veritabanı yedeği değil"):
        restore_backup.stage_restore(yol.read_bytes())


def test_daha_yeni_surumun_yedegi_reddedilir(tmp_path: Path) -> None:
    icerik = _sahte_db(
        tmp_path / "y.sqlite3",
        gocler=(("okul", "0001_initial"), ("disiplin", "9999_gelecekten_gelen_goc")),
    )

    with pytest.raises(restore_backup.RestoreError, match="daha yeni bir sürümüyle"):
        restore_backup.stage_restore(icerik)


def test_baska_anahtarla_sifreli_duz_dosya_reddedilir(tmp_path: Path) -> None:
    """Açılamayacak bir kurulum üretilmez: anahtarı bu kurulumda olmayan düz dosya."""
    icerik = _sahte_db(tmp_path / "y.sqlite3", parmak_izi="abc123")

    with pytest.raises(restore_backup.RestoreError, match="bulunmayan bir güvenlik anahtarıyla"):
        restore_backup.stage_restore(icerik)

    assert not (tmp_path / "veri" / PENDING_DB_NAME).exists()


def test_bu_kurulumun_anahtariyla_sifreli_duz_dosya_kabul_edilir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """geri-yukleme-oncesi/db.sqlite3 gibi: anahtar bu kurulumun guvenlik.json dosyasında."""
    monkeypatch.setattr(restore_backup, "_current_fingerprint", lambda: "abc123")
    icerik = _sahte_db(tmp_path / "y.sqlite3", parmak_izi="abc123")

    sonuc = restore_backup.stage_restore(icerik)

    assert sonuc["pending_restore"] is True
    assert sonuc["warning"] == ""
    assert not (tmp_path / "veri" / PENDING_STATE_NAME).exists()


@pytest.mark.django_db
def test_parola_kuruluyken_alanlari_duz_yedek_parolayi_korur_ve_bunu_soyler(
    tmp_path: Path,
) -> None:
    (tmp_path / "veri" / "guvenlik.json").write_text("{}", encoding="utf-8")

    sonuc = restore_backup.stage_restore(_sahte_db(tmp_path / "y.sqlite3"))

    assert "yeniden şifrelenir" in sonuc["warning"]
    assert not (tmp_path / "veri" / PENDING_STATE_NAME).exists()


# -------------------------------------------------------------- şifreli yedek


def test_sifreli_yedek_parolayla_acilir_guvenlik_basligi_da_bekletilir(tmp_path: Path) -> None:
    yedek = _Yedek(tmp_path)

    sonuc = restore_backup.stage_restore(yedek.kapsayici, password=PAROLA)

    veri = tmp_path / "veri"
    assert sonuc["pending_restore"] is True
    assert (veri / PENDING_DB_NAME).read_bytes().startswith(b"SQLite format 3")
    assert (veri / PENDING_STATE_NAME).read_bytes() == yedek.baslik
    # Farklı anahtar (burada: boş kurulum) → parola yedeğinkine döner; kullanıcı bilmeli.
    assert "yedeğin alındığı tarihteki parola" in sonuc["warning"]


def test_ayni_veri_anahtarli_eski_yedek_parolayi_eskiye_dondurmez(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Parola değiştirildikten sonra eski yedeğe dönmek: bugünkü guvenlik.json KALIR.

    13.11.2026 incelemesi: başlık her zaman bekletiliyordu; kullanıcı yeniden açılışta
    unuttuğu/ifşa olmuş eski parolaya mahkûm kalıyordu, uyarı da yoktu.
    """
    yedek = _Yedek(tmp_path)
    monkeypatch.setattr(
        restore_backup, "_current_fingerprint", lambda: crypto.key_fingerprint(yedek.anahtar)
    )

    sonuc = restore_backup.stage_restore(yedek.kapsayici, password=PAROLA)

    assert sonuc["pending_restore"] is True
    assert sonuc["warning"] == ""
    assert not (tmp_path / "veri" / PENDING_STATE_NAME).exists()


def test_bu_kurulumun_parmak_izi_guvenlik_dosyasi_yokken_bostur(tmp_path: Path) -> None:
    assert restore_backup._current_fingerprint() == ""


@pytest.mark.django_db
def test_bu_kurulumun_parmak_izi_veritabanindan_okunur(tmp_path: Path) -> None:
    from apps.okul.models import SchoolConfig

    (tmp_path / "veri" / "guvenlik.json").write_text("{}", encoding="utf-8")
    config = SchoolConfig.load()
    config.app_password_hash = "parmak-izi"
    config.save()

    assert restore_backup._current_fingerprint() == "parmak-izi"


@pytest.mark.parametrize(
    "kdf",
    [
        {"time_cost": 1, "memory_cost": 8 * 1024 * 1024 * 1024, "parallelism": 1},
        {"time_cost": 10_000, "memory_cost": 8, "parallelism": 1},
        {"time_cost": "3", "memory_cost": 8, "parallelism": 1},
        {"time_cost": True, "memory_cost": 8, "parallelism": 1},
        {},
    ],
)
def test_asiri_ya_da_bozuk_kdf_parametreli_baslik_kdf_kosulmadan_reddedilir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, kdf: dict[str, object]
) -> None:
    """Yedeğin başlığı doğrulanmamış girdidir: 8 GiB Argon2 süreci düşürmemeli."""
    yedek = _Yedek(tmp_path)
    durum = json.loads(yedek.baslik)
    durum["kdf"] = kdf
    kaynak = tmp_path / "kaynak"
    kapsayici = encrypt_bytes(
        b"SQLite format 3\x00", load_public_key(kaynak), recovery_header=json.dumps(durum).encode()
    )
    monkeypatch.setattr(
        app_password, "data_key_from_state", lambda *a, **k: pytest.fail("KDF koşmamalıydı")
    )

    with pytest.raises(restore_backup.RestoreError, match="güvenlik başlığı"):
        restore_backup.stage_restore(kapsayici, password=PAROLA)


def test_bozuk_sarmalli_baslik_turkce_hataya_cikar(tmp_path: Path) -> None:
    yedek = _Yedek(tmp_path)
    durum = json.loads(yedek.baslik)
    durum["parola"]["salt"] = "base64 değil!!"
    kapsayici = encrypt_bytes(
        b"SQLite format 3\x00",
        load_public_key(tmp_path / "kaynak"),
        recovery_header=json.dumps(durum).encode(),
    )

    with pytest.raises(restore_backup.RestoreError, match="güvenlik başlığı geçersiz"):
        restore_backup.stage_restore(kapsayici, password=PAROLA)


def test_cok_buyuk_yedek_reddedilir(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(restore_backup, "MAX_RESTORE_BYTES", 10)

    with pytest.raises(restore_backup.RestoreError, match="beklenenden büyük"):
        restore_backup.stage_restore(b"SQLite format 3\x00" + b"x" * 100)


def test_bekletme_yazilamazsa_turkce_hata_ve_onceki_bekletme_kalmaz(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Yarıda kalan ikinci bekletme, birincinin veritabanını ikincinin başlığıyla bırakmaz."""
    restore_backup.stage_restore(_sahte_db(tmp_path / "a.sqlite3", okul_adi="A"))
    yedek = _Yedek(tmp_path)
    asil = Path.replace

    def kilitli(self: Path, target: Path) -> Path:
        if target.name == PENDING_DB_NAME:
            raise PermissionError(13, "dosya kullanımda")
        return asil(self, target)

    monkeypatch.setattr(Path, "replace", kilitli)

    with pytest.raises(restore_backup.RestoreError, match="yazılamadı"):
        restore_backup.stage_restore(yedek.kapsayici, password=PAROLA)

    veri = tmp_path / "veri"
    # "Uygula" işareti (bekleyen veritabanı) yok → açılışta hiçbir şey uygulanmaz;
    # kalan başlık artığını apply_pending_restore temizler.
    assert not (veri / PENDING_DB_NAME).exists()
    assert list(veri.glob("*.tmp")) == []
    monkeypatch.undo()
    assert apply_pending_restore(veri / "db.sqlite3", tmp_path / "yedek") is None
    assert not (veri / PENDING_STATE_NAME).exists()


def test_sifreli_yedek_kurtarma_anahtariyla_acilir(tmp_path: Path) -> None:
    yedek = _Yedek(tmp_path)

    sonuc = restore_backup.stage_restore(yedek.kapsayici, recovery_key=yedek.kurtarma.lower())

    assert sonuc["pending_restore"] is True


def test_sifreli_yedek_yanlis_parolayla_acilmaz(tmp_path: Path) -> None:
    yedek = _Yedek(tmp_path)

    with pytest.raises(app_password.AppPasswordError, match="Parola hatalı"):
        restore_backup.stage_restore(yedek.kapsayici, password="yanlis-parola")

    assert not (tmp_path / "veri" / PENDING_DB_NAME).exists()


def test_sifreli_yedek_parolasiz_istekte_parola_ister(tmp_path: Path) -> None:
    yedek = _Yedek(tmp_path)

    with pytest.raises(restore_backup.RestoreError, match="Bu yedek şifreli"):
        restore_backup.stage_restore(yedek.kapsayici)


def test_kilit_acikken_bugunku_anahtarla_alinan_yedek_parola_sormaz(tmp_path: Path) -> None:
    yedek = _Yedek(tmp_path)
    crypto.load_key(yedek.anahtar)

    sonuc = restore_backup.stage_restore(yedek.kapsayici)

    assert sonuc["pending_restore"] is True
    assert (tmp_path / "veri" / PENDING_STATE_NAME).is_file()


def test_bozulmus_sifreli_yedek_reddedilir(tmp_path: Path) -> None:
    bozuk = bytearray(_Yedek(tmp_path).kapsayici)
    bozuk[-1] ^= 1

    with pytest.raises(ValueError, match="bütünlüğü"):
        restore_backup.stage_restore(bytes(bozuk), password=PAROLA)


def test_alanlari_duz_sifreli_yedekte_guvenlik_basligi_bekletilmez(tmp_path: Path) -> None:
    """Parola kaldırıldıktan sonra indirilen `.ddbak`: alanlar düzdür; veritabanına
    eski parolanın güvenlik dosyası dayatılmaz."""
    yedek = _Yedek(tmp_path, sifreli_alanlar=False)

    restore_backup.stage_restore(yedek.kapsayici, password=PAROLA)

    assert (tmp_path / "veri" / PENDING_DB_NAME).is_file()
    assert not (tmp_path / "veri" / PENDING_STATE_NAME).exists()


def test_ikinci_bekletme_oncekinin_guvenlik_basligini_temizler(tmp_path: Path) -> None:
    restore_backup.stage_restore(_Yedek(tmp_path).kapsayici, password=PAROLA)

    restore_backup.stage_restore(_sahte_db(tmp_path / "duz.sqlite3", okul_adi="Düz Yedek"))

    veri = tmp_path / "veri"
    assert _okul_adi(veri / PENDING_DB_NAME) == "Düz Yedek"
    assert not (veri / PENDING_STATE_NAME).exists()


def test_sifreli_yedek_bos_kurulumda_uctan_uca_geri_yuklenir(tmp_path: Path) -> None:
    """Yeni bilgisayar senaryosu: yedek + parola yeter; güvenlik dosyası yedekten gelir."""
    yedek = _Yedek(tmp_path)
    veri = tmp_path / "veri"

    restore_backup.stage_restore(yedek.kapsayici, password=PAROLA)
    onceki = apply_pending_restore(veri / "db.sqlite3", tmp_path / "yedek")

    assert onceki is not None
    assert _okul_adi(veri / "db.sqlite3") == "Deneme Lisesi"
    assert (veri / "guvenlik.json").read_bytes() == yedek.baslik
    # Geri gelen güvenlik dosyası yedeğin parolasıyla aynı veri anahtarını açar.
    durum = app_password.read_state()
    assert durum is not None
    assert app_password.data_key_from_state(durum, password=PAROLA) == yedek.anahtar


# ----------------------------------------------------- yedekler klasöründen seçim


def test_yedekler_klasorundeki_dosya_adiyla_bekletilir(tmp_path: Path) -> None:
    (tmp_path / "yedek" / "gunluk-2026-11-12.sqlite3").write_bytes(
        _sahte_db(tmp_path / "y.sqlite3", okul_adi="Dünkü")
    )

    sonuc = restore_backup.stage_local_backup("gunluk-2026-11-12.sqlite3")

    assert sonuc["pending_restore"] is True
    assert _okul_adi(tmp_path / "veri" / PENDING_DB_NAME) == "Dünkü"


@pytest.mark.parametrize(
    "ad",
    ["", "  ", "../veri/db.sqlite3", "alt/gunluk.sqlite3", "..", "gunluk.txt", "C:\\x.sqlite3"],
)
def test_yedek_adi_dizin_disina_cikamaz(tmp_path: Path, ad: str) -> None:
    (tmp_path / "veri" / "db.sqlite3").write_bytes(_sahte_db(tmp_path / "y.sqlite3"))

    with pytest.raises(restore_backup.RestoreError):
        restore_backup.stage_local_backup(ad)

    assert not (tmp_path / "veri" / PENDING_DB_NAME).exists()


def test_olmayan_yedek_adi_reddedilir() -> None:
    with pytest.raises(restore_backup.RestoreError, match="bulunamadı"):
        restore_backup.stage_local_backup("gunluk-2020-01-01.sqlite3")


# ------------------------------------------------------------------ özet + uç


def test_ozet_son_gunluk_yedegi_ve_bekleyen_durumu_verir(tmp_path: Path) -> None:
    yedek = tmp_path / "yedek"
    (yedek / "gunluk-2026-11-12.sqlite3").write_bytes(b"x")
    (yedek / "gunluk-2026-11-13.ddbak").write_bytes(b"x")
    (yedek / "pre-migrate-2026.10.0-2026-11-14.ddbak").write_bytes(b"x")

    ozet = restore_backup.overview()

    assert ozet["last_daily_on"] == "2026-11-13"
    assert ozet["pending_restore"] is False
    assert ozet["backups"][0]["name"] == "pre-migrate-2026.10.0-2026-11-14.ddbak"
    assert {b["kind"] for b in ozet["backups"]} == {"daily", "pre_migrate"}


def test_hic_yedek_yokken_ozet_bos_doner() -> None:
    ozet = restore_backup.overview()

    assert ozet["last_daily_on"] is None
    assert ozet["backups"] == []


def test_vazgecme_bekleyen_dosyalari_siler(tmp_path: Path) -> None:
    restore_backup.stage_restore(_Yedek(tmp_path).kapsayici, password=PAROLA)

    ozet = restore_backup.cancel_pending()

    assert ozet["pending_restore"] is False
    assert not (tmp_path / "veri" / PENDING_DB_NAME).exists()
    assert not (tmp_path / "veri" / PENDING_STATE_NAME).exists()


def test_uc_dosya_yuklemesiyle_bekletir_ve_vazgecer(tmp_path: Path) -> None:
    istemci = APIClient()
    dosya = SimpleUploadedFile("yedek.sqlite3", _sahte_db(tmp_path / "y.sqlite3"))

    yanit = istemci.post(URL, {"file": dosya}, format="multipart")

    assert yanit.status_code == 200, yanit.content
    assert yanit.json()["pending_restore"] is True
    assert istemci.get(URL).json()["pending_restore"] is True
    assert istemci.delete(URL).json()["pending_restore"] is False


def test_uc_sifreli_yedekte_parola_eksikse_400_ve_turkce_ileti(tmp_path: Path) -> None:
    yedek = _Yedek(tmp_path)
    istemci = APIClient()

    yanit = istemci.post(
        URL, {"file": SimpleUploadedFile("y.ddbak", yedek.kapsayici)}, format="multipart"
    )

    assert yanit.status_code == 400
    assert "şifreli" in json.dumps(yanit.json(), ensure_ascii=False)

    yanit = istemci.post(
        URL,
        {"file": SimpleUploadedFile("y.ddbak", yedek.kapsayici), "password": PAROLA},
        format="multipart",
    )
    assert yanit.status_code == 200, yanit.content


def test_uc_dosya_ve_ad_birlikte_ya_da_ikisi_de_yokken_400() -> None:
    istemci = APIClient()

    bos = istemci.post(URL, {}, format="json")
    ikisi = istemci.post(
        URL,
        {"file": SimpleUploadedFile("y.sqlite3", b"x"), "name": "gunluk-2026-11-12.sqlite3"},
        format="multipart",
    )

    for yanit in (bos, ikisi):
        assert yanit.status_code == 400
        # Arayüz yalnız `message` alanını gösterir; açıklama orada olmalı.
        assert "Bir yedek seçin" in json.dumps(yanit.json(), ensure_ascii=False)


def test_uc_cok_buyuk_yuklemeyi_okumadan_reddeder(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(restore_backup, "MAX_RESTORE_BYTES", 10)

    yanit = APIClient().post(
        URL, {"file": SimpleUploadedFile("y.sqlite3", b"x" * 100)}, format="multipart"
    )

    assert yanit.status_code == 400
    assert "beklenenden büyük" in json.dumps(yanit.json(), ensure_ascii=False)


def test_uc_kilitliyken_de_calisir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Kilit açılamıyorken yedekten dönülebilmeli: uç kilit kapısından muaf ön ekte."""
    monkeypatch.setattr(app_password, "is_locked", lambda: True)
    istemci = APIClient()

    assert istemci.get("/api/v1/students/").status_code == 423
    assert istemci.get(URL).status_code == 200
    yanit = istemci.post(
        URL,
        {"file": SimpleUploadedFile("y.sqlite3", _sahte_db(tmp_path / "y.sqlite3"))},
        format="multipart",
    )
    assert yanit.status_code == 200, yanit.content
