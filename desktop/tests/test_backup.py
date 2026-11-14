"""Otomatik yedek testleri (tasarım §5.3 — `Connection.backup()`, 14 gün rotasyon)."""

from __future__ import annotations

import sqlite3
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from desktop import backup as backup_mod
from desktop.backup import (
    daily_backup,
    encrypt_legacy_backups,
    list_backups,
    pre_migrate_backup,
    rotate_backups,
)
from desktop.backup_crypto import (
    BackupCryptoError,
    decrypt_bytes,
    embedded_recovery_metadata,
    ensure_public_config,
)

_TEST_KEY = b"k" * 32


def _db_olustur(path: Path, satir_sayisi: int = 3, *, parola: bool = True) -> None:
    """Deneme veritabanı.

    `parola=True` uygulama parolası kurulu kurulumu taklit eder (`guvenlik.json` +
    açık yedek anahtarı); False varsayılan, parolasız kurulumdur.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    if parola:
        ensure_public_config(path.parent, _TEST_KEY)
        (path.parent / "guvenlik.json").write_text("{}", encoding="utf-8")
    conn = sqlite3.connect(path)
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("CREATE TABLE ogrenci (id INTEGER PRIMARY KEY, ad TEXT)")
        conn.executemany(
            "INSERT INTO ogrenci (ad) VALUES (?)",
            [(f"Öğrenci {i}",) for i in range(satir_sayisi)],
        )
        conn.commit()
    finally:
        conn.close()


def _satir_sayisi(path: Path) -> int:
    restored = path.with_name(path.name + ".restored.sqlite3")
    restored.write_bytes(
        decrypt_bytes(path.read_bytes(), _TEST_KEY)
        if path.suffix == ".ddbak"
        else path.read_bytes()
    )
    conn = sqlite3.connect(restored)
    try:
        return int(conn.execute("SELECT COUNT(*) FROM ogrenci").fetchone()[0])
    finally:
        conn.close()
        restored.unlink(missing_ok=True)


def test_gunluk_yedek_tarihli_deterministik_ad_alir(tmp_path: Path) -> None:
    db = tmp_path / "db.sqlite3"
    _db_olustur(db)
    yedekler = tmp_path / "backups"

    sonuc = daily_backup(db, yedekler, today=date(2026, 7, 24))

    assert sonuc == yedekler / "gunluk-2026-07-24.ddbak"
    assert sonuc is not None and sonuc.is_file()
    assert _satir_sayisi(sonuc) == 3


def test_yedek_kurtarma_basligini_tasir_ve_baslik_dogrulanir(tmp_path: Path) -> None:
    db = tmp_path / "db.sqlite3"
    _db_olustur(db)
    guvenlik = b'{"kdf":{"time_cost":3},"parola":{"sarmal":"ornek"}}'
    (tmp_path / "guvenlik.json").write_bytes(guvenlik)

    sonuc = daily_backup(db, tmp_path / "backups", today=date(2026, 7, 24))

    assert sonuc is not None
    container = sonuc.read_bytes()
    assert embedded_recovery_metadata(container) == guvenlik
    bozuk = bytearray(container)
    bozuk[-1] ^= 1
    with pytest.raises(BackupCryptoError, match="bütünlüğü"):
        decrypt_bytes(bytes(bozuk), _TEST_KEY)


def test_gunluk_yedek_ayni_gun_yeniden_uretilmez(tmp_path: Path) -> None:
    """Gün içinde ikinci açılış, o günün (daha eski, daha değerli) yedeğini EZMEZ."""
    db = tmp_path / "db.sqlite3"
    _db_olustur(db, satir_sayisi=3)
    yedekler = tmp_path / "backups"
    ilk = daily_backup(db, yedekler, today=date(2026, 7, 24))
    assert ilk is not None

    conn = sqlite3.connect(db)
    conn.execute("INSERT INTO ogrenci (ad) VALUES ('sonradan')")
    conn.commit()
    conn.close()
    ikinci = daily_backup(db, yedekler, today=date(2026, 7, 24))

    assert ikinci == ilk
    assert _satir_sayisi(ilk) == 3


class _IzlenenBaglanti:
    """`sqlite3.Connection` sarmalayıcısı — `backup()` çağrısını kaydeder.

    `sqlite3.Connection` C tarafında değiştirilemez bir tip olduğu için doğrudan
    yamalanamaz; bu yüzden `sqlite3.connect` sarılır.
    """

    calls: list[str] = []
    patla: bool = False

    def __init__(self, real: sqlite3.Connection) -> None:
        self._real = real

    def backup(self, target: object, **kwargs: object) -> None:
        _IzlenenBaglanti.calls.append("backup")
        if _IzlenenBaglanti.patla:
            raise sqlite3.OperationalError("disk dolu")
        gercek = target._real if isinstance(target, _IzlenenBaglanti) else target
        self._real.backup(gercek, **kwargs)  # type: ignore[arg-type]

    def close(self) -> None:
        self._real.close()

    def __getattr__(self, name: str) -> Any:
        # Sarmalanmayan her şey gerçek bağlantıya gider (execute/commit/…).
        return getattr(self._real, name)


@pytest.fixture
def izlenen_connect(monkeypatch: pytest.MonkeyPatch) -> type[_IzlenenBaglanti]:
    _IzlenenBaglanti.calls = []
    _IzlenenBaglanti.patla = False
    gercek_connect: Any = sqlite3.connect

    def sarmala(*args: Any, **kwargs: Any) -> _IzlenenBaglanti:
        return _IzlenenBaglanti(gercek_connect(*args, **kwargs))

    # `desktop.backup` de aynı modül nesnesini kullanır (`import sqlite3`).
    monkeypatch.setattr(sqlite3, "connect", sarmala)
    return _IzlenenBaglanti


def test_yedek_sqlite_backup_api_ile_alinir(
    tmp_path: Path, izlenen_connect: type[_IzlenenBaglanti]
) -> None:
    """Yedek `Connection.backup()` ile alınır (dosya kopyalama değil)."""
    db = tmp_path / "db.sqlite3"
    _db_olustur(db)

    daily_backup(db, tmp_path / "backups", today=date(2026, 7, 24))

    assert izlenen_connect.calls == ["backup"]


def test_yedek_wal_de_bekleyen_sayfalari_da_icerir(tmp_path: Path) -> None:
    """Dosya kopyalama DEĞİL kanıtı: WAL'daki satırlar yedekte OLMALI.

    WAL kipinde işlenen satırların bir bölümü hâlâ `-wal` dosyasındadır;
    `db.sqlite3` tek başına kopyalansaydı bu satırlar yedeğe girmezdi.
    """
    db = tmp_path / "db.sqlite3"
    ensure_public_config(db.parent, _TEST_KEY)
    conn = sqlite3.connect(db)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("CREATE TABLE ogrenci (id INTEGER PRIMARY KEY, ad TEXT)")
    conn.executemany("INSERT INTO ogrenci (ad) VALUES (?)", [(f"Öğrenci {i}",) for i in range(3)])
    conn.commit()
    try:  # bağlantı AÇIK kalır → checkpoint yok, satırlar WAL'da
        assert db.with_name(db.name + "-wal").stat().st_size > 0

        yedek = daily_backup(db, tmp_path / "backups", today=date(2026, 7, 24))
        assert yedek is not None

        # Ham dosya kopyası (yanlış yöntem) satırları GÖREMEZ...
        ham = tmp_path / "ham.sqlite3"
        ham.write_bytes(db.read_bytes())
        ham_conn = sqlite3.connect(ham)
        try:
            ham_satir = ham_conn.execute(
                "SELECT COUNT(*) FROM sqlite_master WHERE name='ogrenci'"
            ).fetchone()[0]
        finally:
            ham_conn.close()
        assert ham_satir == 0
    finally:
        conn.close()

    # ...ama `Connection.backup()` ile alınan yedek tam veriyi taşır.
    assert _satir_sayisi(yedek) == 3


def test_veritabani_yoksa_yedek_alinmaz(tmp_path: Path) -> None:
    assert daily_backup(tmp_path / "yok.sqlite3", tmp_path / "backups") is None


def test_yarim_kalan_yedek_dosyasi_birakilmaz(
    tmp_path: Path, izlenen_connect: type[_IzlenenBaglanti]
) -> None:
    """Kopyalama ortasında hata olursa bozuk yedek "sağlam" adıyla kalmamalı."""
    db = tmp_path / "db.sqlite3"
    _db_olustur(db)
    yedekler = tmp_path / "backups"
    izlenen_connect.patla = True

    with pytest.raises(sqlite3.Error):
        daily_backup(db, yedekler, today=date(2026, 7, 24))

    assert list(yedekler.glob("gunluk-*.ddbak")) == []
    assert list(yedekler.glob("*.tmp")) == []


def test_rotasyon_14_gunden_eskileri_siler_yenileri_korur(tmp_path: Path) -> None:
    yedekler = tmp_path / "backups"
    yedekler.mkdir()
    for gun in ("2026-07-24", "2026-07-11", "2026-07-10", "2026-07-09"):
        (yedekler / f"gunluk-{gun}.ddbak").write_bytes(b"x")

    silinen = rotate_backups(yedekler, today=date(2026, 7, 24))

    kalanlar = sorted(p.name for p in yedekler.glob("gunluk-*.ddbak"))
    # 14 gün: 10 Temmuz sınırda (korunur), 9 Temmuz düşer.
    assert kalanlar == [
        "gunluk-2026-07-10.ddbak",
        "gunluk-2026-07-11.ddbak",
        "gunluk-2026-07-24.ddbak",
    ]
    assert [p.name for p in silinen] == ["gunluk-2026-07-09.ddbak"]


def test_rotasyon_yabanci_dosyalara_dokunmaz(tmp_path: Path) -> None:
    yedekler = tmp_path / "backups"
    yedekler.mkdir()
    (yedekler / "elle-alinan-yedek.sqlite3").write_bytes(b"x")
    (yedekler / "gunluk-bozukad.sqlite3").write_bytes(b"x")
    (yedekler / "notlar.txt").write_bytes(b"x")

    rotate_backups(yedekler, today=date(2026, 7, 24))

    assert (yedekler / "elle-alinan-yedek.sqlite3").exists()
    assert (yedekler / "gunluk-bozukad.sqlite3").exists()
    assert (yedekler / "notlar.txt").exists()


def test_eski_duz_yedek_sifrelenir_ve_duz_kopya_silinir(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    ensure_public_config(data_dir, _TEST_KEY)
    (data_dir / "guvenlik.json").write_text("{}", encoding="utf-8")
    yedekler = tmp_path / "backups"
    yedekler.mkdir()
    legacy = yedekler / "gunluk-2026-07-20.sqlite3"
    _db_olustur(legacy, parola=False)

    encrypted = encrypt_legacy_backups(yedekler, data_dir)

    target = yedekler / "gunluk-2026-07-20.ddbak"
    assert encrypted == [target]
    assert not legacy.exists()
    assert b"SQLite format 3" not in target.read_bytes()
    assert _satir_sayisi(target) == 3


def test_rotasyon_olmayan_dizinde_patlamaz(tmp_path: Path) -> None:
    assert rotate_backups(tmp_path / "yok", today=date(2026, 7, 24)) == []


def test_migrate_oncesi_yedek_surum_adiyla_alinir(tmp_path: Path) -> None:
    db = tmp_path / "db.sqlite3"
    _db_olustur(db)
    yedekler = tmp_path / "backups"

    sonuc = pre_migrate_backup(db, yedekler, "0.2.0", today=date(2026, 7, 24))

    assert sonuc == yedekler / "pre-migrate-0.2.0-2026-07-24.ddbak"
    assert sonuc is not None and _satir_sayisi(sonuc) == 3


def test_migrate_oncesi_yedek_dosya_adini_temizler(tmp_path: Path) -> None:
    db = tmp_path / "db.sqlite3"
    _db_olustur(db)

    sonuc = pre_migrate_backup(db, tmp_path / "backups", "1.0/rc:1", today=date(2026, 7, 24))

    assert sonuc is not None
    assert sonuc.name == "pre-migrate-1.0_rc_1-2026-07-24.ddbak"


def test_migrate_oncesi_yedek_var_olani_ezmez(tmp_path: Path) -> None:
    db = tmp_path / "db.sqlite3"
    _db_olustur(db, satir_sayisi=2)
    yedekler = tmp_path / "backups"
    ilk = pre_migrate_backup(db, yedekler, "0.2.0", today=date(2026, 7, 24))
    assert ilk is not None

    conn = sqlite3.connect(db)
    conn.execute("INSERT INTO ogrenci (ad) VALUES ('sonradan')")
    conn.commit()
    conn.close()
    ikinci = pre_migrate_backup(db, yedekler, "0.2.0", today=date(2026, 7, 24))

    assert ikinci == ilk
    assert _satir_sayisi(ilk) == 2


def test_rotasyon_migrate_oncesi_yedeklerin_son_besini_tutar(tmp_path: Path) -> None:
    """Yükseltme öncesi kopyalar gün değil ADET ile sınırlanır (14 günden uzun yaşayabilir)."""
    yedekler = tmp_path / "backups"
    yedekler.mkdir()
    for i in range(1, 8):
        (yedekler / f"pre-migrate-0.{i}.0-2020-01-0{i}.ddbak").write_bytes(b"x")

    rotate_backups(yedekler, today=date(2026, 7, 24), keep_pre_migrate=5)

    kalanlar = sorted(p.name for p in yedekler.glob("pre-migrate-*.ddbak"))
    assert len(kalanlar) == 5
    assert "pre-migrate-0.7.0-2020-01-07.ddbak" in kalanlar
    assert "pre-migrate-0.1.0-2020-01-01.ddbak" not in kalanlar


def test_yedek_dizini_yoksa_olusturulur(tmp_path: Path) -> None:
    db = tmp_path / "db.sqlite3"
    _db_olustur(db)

    daily_backup(db, tmp_path / "a" / "b" / "backups", today=date(2026, 7, 24))

    assert (tmp_path / "a" / "b" / "backups").is_dir()


def test_varsayilan_saklama_suresi_14_gun(tmp_path: Path) -> None:
    assert backup_mod.DEFAULT_KEEP_DAYS == 14


# ------------------------------------------------- parolasız (varsayılan) kurulum


def test_parolasiz_kurulumda_gunluk_yedek_duz_sqlite_olarak_alinir(tmp_path: Path) -> None:
    """13.11.2026 denetimi: parola kurulmamışken yedek sessizce ATLANIYORDU."""
    db = tmp_path / "db.sqlite3"
    _db_olustur(db, parola=False)
    yedekler = tmp_path / "backups"

    sonuc = daily_backup(db, yedekler, today=date(2026, 11, 13))

    assert sonuc == yedekler / "gunluk-2026-11-13.sqlite3"
    assert sonuc is not None and sonuc.read_bytes().startswith(b"SQLite format 3")
    assert _satir_sayisi(sonuc) == 3
    assert list(yedekler.glob("*.tmp")) == []


def test_parolasiz_kurulumda_goc_oncesi_yedek_de_alinir(tmp_path: Path) -> None:
    db = tmp_path / "db.sqlite3"
    _db_olustur(db, parola=False)

    sonuc = pre_migrate_backup(
        db, tmp_path / "backups", "2026.10.0-beta.2", today=date(2026, 11, 13)
    )

    assert sonuc is not None
    assert sonuc.name == "pre-migrate-2026.10.0-beta.2-2026-11-13.sqlite3"
    assert _satir_sayisi(sonuc) == 3


def test_parolasiz_yedek_wal_bekleyen_sayfalari_da_icerir(tmp_path: Path) -> None:
    db = tmp_path / "db.sqlite3"
    _db_olustur(db, parola=False)
    acik = sqlite3.connect(db)
    try:
        acik.execute("INSERT INTO ogrenci (ad) VALUES (?)", ("wal",))
        acik.commit()
        sonuc = daily_backup(db, tmp_path / "backups", today=date(2026, 11, 13))
    finally:
        acik.close()

    assert sonuc is not None and _satir_sayisi(sonuc) == 4


def test_parola_kurulu_ama_anahtar_hazir_degilse_duz_yedek_yazilmaz(tmp_path: Path) -> None:
    """Şifreli alanları olan veri düz yazılmaz; bir açılış beklenir (dosya başlığı)."""
    db = tmp_path / "db.sqlite3"
    _db_olustur(db, parola=False)
    (tmp_path / "guvenlik.json").write_text("{}", encoding="utf-8")
    yedekler = tmp_path / "backups"

    assert daily_backup(db, yedekler, today=date(2026, 11, 13)) is None
    assert not yedekler.exists() or list(yedekler.iterdir()) == []


def test_parola_kaldirildiktan_sonra_yedek_eski_anahtarla_sifrelenmez(tmp_path: Path) -> None:
    """Parola kaldırılınca yedekleme.json diskte kalır; yeni yedekler yine de düzdür."""
    db = tmp_path / "db.sqlite3"
    _db_olustur(db, parola=True)
    (tmp_path / "guvenlik.json").unlink()  # disable(): dosya arşive taşınır
    yedekler = tmp_path / "backups"

    sonuc = daily_backup(db, yedekler, today=date(2026, 11, 13))

    assert sonuc is not None and sonuc.suffix == ".sqlite3"
    assert encrypt_legacy_backups(yedekler, tmp_path) == []
    assert sonuc.is_file()


def test_ayni_gun_duz_yedek_varken_sifreli_ikinci_yedek_uretilmez(tmp_path: Path) -> None:
    db = tmp_path / "db.sqlite3"
    _db_olustur(db, parola=False)
    yedekler = tmp_path / "backups"
    ilk = daily_backup(db, yedekler, today=date(2026, 11, 13))
    ensure_public_config(tmp_path, _TEST_KEY)
    (tmp_path / "guvenlik.json").write_text("{}", encoding="utf-8")

    ikinci = daily_backup(db, yedekler, today=date(2026, 11, 13))

    assert ikinci == ilk
    assert [p.name for p in yedekler.iterdir()] == ["gunluk-2026-11-13.sqlite3"]


def test_parola_kurulunca_duz_yedekler_sifrelenir(tmp_path: Path) -> None:
    db = tmp_path / "db.sqlite3"
    _db_olustur(db, parola=False)
    yedekler = tmp_path / "backups"
    daily_backup(db, yedekler, today=date(2026, 11, 13))
    ensure_public_config(tmp_path, _TEST_KEY)
    (tmp_path / "guvenlik.json").write_text("{}", encoding="utf-8")

    cevrilen = encrypt_legacy_backups(yedekler, tmp_path)

    assert [p.name for p in cevrilen] == ["gunluk-2026-11-13.ddbak"]
    assert [p.name for p in yedekler.iterdir()] == ["gunluk-2026-11-13.ddbak"]
    assert _satir_sayisi(cevrilen[0]) == 3


def test_rotasyon_duz_yedekleri_de_kapsar(tmp_path: Path) -> None:
    yedekler = tmp_path / "backups"
    yedekler.mkdir()
    eski = yedekler / "gunluk-2026-10-01.sqlite3"
    yeni = yedekler / "gunluk-2026-11-12.sqlite3"
    for dosya in (eski, yeni):
        dosya.write_bytes(b"x")
    for gun in range(1, 8):
        (yedekler / f"pre-migrate-1.0-2026-09-0{gun}.sqlite3").write_bytes(b"x")

    silinen = rotate_backups(yedekler, today=date(2026, 11, 13))

    assert eski in silinen and not eski.exists()
    assert yeni.exists()
    assert len(list(yedekler.glob("pre-migrate-*.sqlite3"))) == 5


def test_yedek_listesi_en_yeniden_eskiye_ve_turuyle_doner(tmp_path: Path) -> None:
    yedekler = tmp_path / "backups"
    yedekler.mkdir()
    (yedekler / "gunluk-2026-11-12.sqlite3").write_bytes(b"12345")
    (yedekler / "gunluk-2026-11-13.ddbak").write_bytes(b"1")
    (yedekler / "pre-migrate-2026.10.0-2026-11-01.ddbak").write_bytes(b"1")
    (yedekler / "elle-kopya.sqlite3").write_bytes(b"1")

    liste = list_backups(yedekler)

    assert [(b.name, b.kind, b.encrypted) for b in liste] == [
        ("gunluk-2026-11-13.ddbak", "daily", True),
        ("gunluk-2026-11-12.sqlite3", "daily", False),
        ("pre-migrate-2026.10.0-2026-11-01.ddbak", "pre_migrate", True),
    ]
    assert liste[1].size == 5 and liste[1].taken_on == date(2026, 11, 12)
    assert list_backups(tmp_path / "yok") == []


# ------------------------------------------------ yazma hatası ve artık temizliği


def test_gunluk_yedek_yazilamazsa_acilis_durmaz(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Disk dolu / klasör yazılamıyor: günlük yedek atlanır, istisna yayılmaz."""
    db = tmp_path / "db.sqlite3"
    _db_olustur(db, parola=False)

    def dolu(self: Path, data: bytes) -> int:
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(Path, "write_bytes", dolu)

    assert daily_backup(db, tmp_path / "backups", today=date(2026, 11, 13)) is None


def test_goc_oncesi_yedek_yazilamazsa_hata_yayilir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Yedeği alınamayan veri göç ettirilmez: çağıran (main) açılışı durdurur."""
    db = tmp_path / "db.sqlite3"
    _db_olustur(db, parola=False)

    def dolu(self: Path, data: bytes) -> int:
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(Path, "write_bytes", dolu)

    with pytest.raises(OSError, match="No space"):
        pre_migrate_backup(db, tmp_path / "backups", "1.0", today=date(2026, 11, 13))


def test_rotasyon_yarim_kalan_tmp_artiklarini_siler(tmp_path: Path) -> None:
    yedekler = tmp_path / "backups"
    yedekler.mkdir()
    artik = yedekler / "gunluk-2026-11-12.sqlite3.tmp"
    yabanci = yedekler / "notlarim.tmp"
    artik.write_bytes(b"x")
    yabanci.write_bytes(b"x")

    rotate_backups(yedekler, today=date(2026, 11, 13))

    assert not artik.exists()
    assert yabanci.exists()


def test_rotasyon_eski_geri_yukleme_oncesi_klasorlerini_siler(tmp_path: Path) -> None:
    """İçlerinde veritabanının ham kopyası durur; günlük yedeklerle aynı sürede silinir."""
    yedekler = tmp_path / "backups"
    eski = yedekler / "geri-yukleme-oncesi-2026-10-01-093000"
    yeni = yedekler / "geri-yukleme-oncesi-2026-11-10-093000"
    for klasor in (eski, yeni):
        klasor.mkdir(parents=True)
        (klasor / "db.sqlite3").write_bytes(b"x")

    silinen = rotate_backups(yedekler, today=date(2026, 11, 13))

    assert eski in silinen and not eski.exists()
    assert (yeni / "db.sqlite3").exists()


@pytest.mark.parametrize("parola", [False, True], ids=["parolasiz", "parola_kurulu"])
def test_serialize_desteklenmeyen_sqlite_ile_de_yedek_alinir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, parola: bool
) -> None:
    # Debian 11'in SQLite'ında `Connection.serialize` yoktur; Linux paketi açılışta
    # AttributeError ile duruyordu (14.11.2026 paketleme kapısı). Görüntü geçici dosyadan
    # alınır, içerik aynıdır ve geçici dosya geride kalmaz.
    db = tmp_path / "data" / "db.sqlite3"
    db.parent.mkdir()
    _db_olustur(db, satir_sayisi=7, parola=parola)
    beklenen = backup_mod.database_snapshot(db)
    monkeypatch.setattr(backup_mod, "_serialize_supported", lambda: False)

    goruntu = backup_mod.database_snapshot(db)

    kopya = tmp_path / "kopya.sqlite3"
    kopya.write_bytes(goruntu)
    assert _satir_sayisi(kopya) == 7
    assert len(goruntu) == len(beklenen)
    assert [p.name for p in db.parent.iterdir() if p.name.endswith(".tmp")] == []

    sonuc = daily_backup(db, tmp_path / "backups", today=date(2026, 11, 14))
    assert sonuc is not None and sonuc.exists()
    assert [p.name for p in db.parent.iterdir() if p.name.endswith(".tmp")] == []


def test_serialize_yolu_hata_verirse_gecici_goruntu_dosyasi_silinir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db = tmp_path / "data" / "db.sqlite3"
    db.parent.mkdir()
    _db_olustur(db, parola=False)
    monkeypatch.setattr(backup_mod, "_serialize_supported", lambda: False)

    def _patla(self: Path) -> bytes:
        raise OSError("disk okunamadı")

    monkeypatch.setattr(Path, "read_bytes", _patla)
    with pytest.raises(OSError, match="disk okunamadı"):
        backup_mod.database_snapshot(db)
    assert [p.name for p in db.parent.iterdir() if p.name.endswith(".tmp")] == []
