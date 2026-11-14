"""Bekleyen geri yüklemenin açılışta uygulanması (desktop/restore.py)."""

from __future__ import annotations

import sqlite3
from datetime import date, datetime
from pathlib import Path

import pytest

from desktop import main as main_mod
from desktop.backup import daily_backup
from desktop.errors import EXIT_RESTORE_FAILED, RestoreFailedError
from desktop.integrity import check_database_integrity
from desktop.paths import ENV_APP_HOME, resolve_app_paths
from desktop.restore import (
    PENDING_DB_NAME,
    PENDING_STATE_NAME,
    apply_pending_restore,
    discard_pending_restore,
    has_pending_restore,
)

_ZAMAN = datetime(2026, 11, 13, 9, 30, 0)


def _db(path: Path, deger: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    try:
        conn.execute("CREATE TABLE kayit (deger TEXT)")
        conn.execute("INSERT INTO kayit VALUES (?)", (deger,))
        conn.commit()
    finally:
        conn.close()


def _deger(path: Path) -> str:
    conn = sqlite3.connect(path)
    try:
        return str(conn.execute("SELECT deger FROM kayit").fetchone()[0])
    finally:
        conn.close()


def test_bekleyen_yedek_yoksa_hicbir_seye_dokunulmaz(tmp_path: Path) -> None:
    db = tmp_path / "data" / "db.sqlite3"
    _db(db, "canli")

    assert apply_pending_restore(db, tmp_path / "backups") is None
    assert _deger(db) == "canli"
    assert not (tmp_path / "backups").exists()


def test_bekleyen_yedek_yerine_konur_eski_veri_saklanir(tmp_path: Path) -> None:
    veri = tmp_path / "data"
    db = veri / "db.sqlite3"
    _db(db, "canli")
    (veri / "db.sqlite3-wal").write_bytes(b"wal")
    _db(veri / PENDING_DB_NAME, "yedek")

    onceki = apply_pending_restore(db, tmp_path / "backups", now=_ZAMAN)

    assert onceki == tmp_path / "backups" / "geri-yukleme-oncesi-2026-11-13-093000"
    assert _deger(db) == "yedek"
    assert (onceki / "db.sqlite3").is_file()
    assert (onceki / "db.sqlite3-wal").read_bytes() == b"wal"
    # Eski WAL yeni veritabanının yanında KALMAZ (SQLite onu yeni dosyaya uygulardı).
    assert not (veri / "db.sqlite3-wal").exists()
    assert not has_pending_restore(veri)


def test_bozuk_veritabani_bekleyen_yedekle_degistirilir(tmp_path: Path) -> None:
    veri = tmp_path / "data"
    db = veri / "db.sqlite3"
    veri.mkdir()
    db.write_bytes(b"bozuk dosya, sqlite degil" * 50)
    _db(veri / PENDING_DB_NAME, "yedek")

    onceki = apply_pending_restore(db, tmp_path / "backups", now=_ZAMAN)

    assert onceki is not None
    check_database_integrity(db)  # hata yükseltmez
    assert _deger(db) == "yedek"
    assert (onceki / "db.sqlite3").read_bytes().startswith(b"bozuk dosya")


def test_veritabani_hic_yokken_bekleyen_yedek_yerine_konur(tmp_path: Path) -> None:
    """Yarıda kesilmiş uygulama: eski veri taşınmış, yenisi henüz konmamış."""
    veri = tmp_path / "data"
    _db(veri / PENDING_DB_NAME, "yedek")

    apply_pending_restore(veri / "db.sqlite3", tmp_path / "backups", now=_ZAMAN)

    assert _deger(veri / "db.sqlite3") == "yedek"


def test_bozuk_bekleyen_dosya_atilir_canli_veri_korunur(tmp_path: Path) -> None:
    veri = tmp_path / "data"
    db = veri / "db.sqlite3"
    _db(db, "canli")
    (veri / PENDING_DB_NAME).write_bytes(b"yarim yazilmis")
    (veri / PENDING_STATE_NAME).write_text("{}", encoding="utf-8")

    assert apply_pending_restore(db, tmp_path / "backups", now=_ZAMAN) is None
    assert _deger(db) == "canli"
    assert not (veri / PENDING_DB_NAME).exists()
    assert not (veri / PENDING_STATE_NAME).exists()


def test_guvenlik_dosyasi_yedekle_birlikte_degisir_eski_anahtar_ayari_silinir(
    tmp_path: Path,
) -> None:
    veri = tmp_path / "data"
    db = veri / "db.sqlite3"
    _db(db, "canli")
    (veri / "guvenlik.json").write_text('{"eski": 1}', encoding="utf-8")
    (veri / "yedekleme.json").write_text('{"acik_anahtar": "eski"}', encoding="utf-8")
    _db(veri / PENDING_DB_NAME, "yedek")
    (veri / PENDING_STATE_NAME).write_text('{"yedek": 1}', encoding="utf-8")

    onceki = apply_pending_restore(db, tmp_path / "backups", now=_ZAMAN)

    assert onceki is not None
    assert (veri / "guvenlik.json").read_text(encoding="utf-8") == '{"yedek": 1}'
    assert (onceki / "guvenlik.json").read_text(encoding="utf-8") == '{"eski": 1}'
    # Eski veri anahtarının açık yedek anahtarı kalsaydı kilit açılırken
    # "anahtar eşleşmiyor" hatası çıkardı; ilk kilit açılışında yeniden üretilir.
    assert not (veri / "yedekleme.json").exists()
    assert not (veri / PENDING_STATE_NAME).exists()


def test_guvenlik_basligi_bekletilmemisse_guvenlik_dosyalarina_dokunulmaz(
    tmp_path: Path,
) -> None:
    """Aynı veri anahtarlı yedek: bekletme başlık yazmaz, bugünkü parola geçerli kalır."""
    veri = tmp_path / "data"
    db = veri / "db.sqlite3"
    _db(db, "canli")
    (veri / "guvenlik.json").write_text('{"bugun": 1}', encoding="utf-8")
    (veri / "yedekleme.json").write_text("{}", encoding="utf-8")
    _db(veri / PENDING_DB_NAME, "yedek")

    onceki = apply_pending_restore(db, tmp_path / "backups", now=_ZAMAN)

    assert onceki is not None
    assert (veri / "guvenlik.json").read_text(encoding="utf-8") == '{"bugun": 1}'
    assert (veri / "yedekleme.json").exists()
    assert not (onceki / "guvenlik.json").exists()


def test_acik_yedek_anahtari_guvenlik_dosyasindan_once_silinir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Kesinti sırası: bayat yedekleme.json ASLA yeni guvenlik.json ile yan yana kalmaz.

    Kalırsa sonraki yedekler başlığındaki parolayla açılamayan bir anahtarla
    şifrelenir ve kilit açılışı "anahtar eşleşmiyor" hatası verir.
    """
    veri = tmp_path / "data"
    db = veri / "db.sqlite3"
    _db(db, "canli")
    (veri / "guvenlik.json").write_text('{"eski": 1}', encoding="utf-8")
    (veri / "yedekleme.json").write_text("{}", encoding="utf-8")
    _db(veri / PENDING_DB_NAME, "yedek")
    (veri / PENDING_STATE_NAME).write_text('{"yedek": 1}', encoding="utf-8")
    asil = Path.replace

    def kesilen(self: Path, target: Path) -> Path:
        if self.name == PENDING_STATE_NAME:
            raise KeyboardInterrupt  # elektrik kesintisi: güvenlik dosyası yerine konamadan
        return asil(self, target)

    monkeypatch.setattr(Path, "replace", kesilen)
    with pytest.raises(KeyboardInterrupt):
        apply_pending_restore(db, tmp_path / "backups", now=_ZAMAN)
    monkeypatch.undo()

    assert not (veri / "yedekleme.json").exists()
    assert (veri / "guvenlik.json").read_text(encoding="utf-8") == '{"eski": 1}'
    # Sonraki açılış işi tamamlar.
    apply_pending_restore(db, tmp_path / "backups", now=_ZAMAN)
    assert _deger(db) == "yedek"
    assert (veri / "guvenlik.json").read_text(encoding="utf-8") == '{"yedek": 1}'


def test_tasinamayan_dosyada_geri_sarilir_canli_veri_yerinde_kalir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Windows: WAL başka bir süreçte açıkken taşıma yarıda kalmaz, iz bırakmaz."""
    veri = tmp_path / "data"
    db = veri / "db.sqlite3"
    _db(db, "canli")
    (veri / "db.sqlite3-wal").write_bytes(b"wal")
    _db(veri / PENDING_DB_NAME, "yedek")
    asil = Path.replace

    def kilitli(self: Path, target: Path) -> Path:
        if self.name == "db.sqlite3-wal" and self.parent == veri:
            raise PermissionError(13, "dosya kullanımda")
        return asil(self, target)

    monkeypatch.setattr(Path, "replace", kilitli)
    with pytest.raises(PermissionError):
        apply_pending_restore(db, tmp_path / "backups", now=_ZAMAN, retry_wait=0)
    monkeypatch.undo()

    # WAL önce denetlenir: sahte WAL, veritabanı açılınca SQLite tarafından atılır.
    assert (veri / "db.sqlite3-wal").read_bytes() == b"wal"
    assert _deger(db) == "canli"
    assert has_pending_restore(veri)  # yedek yerinde: yeniden denenebilir ya da vazgeçilebilir
    assert list((tmp_path / "backups").glob("geri-yukleme-oncesi-*")) == []


def test_gecici_kilit_yeniden_denemeyle_asilir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    veri = tmp_path / "data"
    db = veri / "db.sqlite3"
    _db(db, "canli")
    _db(veri / PENDING_DB_NAME, "yedek")
    asil = Path.replace
    denemeler = {"sayi": 0}

    def bir_kez_kilitli(self: Path, target: Path) -> Path:
        if self == db and denemeler["sayi"] == 0:
            denemeler["sayi"] += 1
            raise PermissionError(13, "dosya kullanımda")
        return asil(self, target)

    monkeypatch.setattr(Path, "replace", bir_kez_kilitli)

    assert apply_pending_restore(db, tmp_path / "backups", now=_ZAMAN, retry_wait=0) is not None
    assert _deger(db) == "yedek"


def test_acilis_uygulanamayan_geri_yuklemeyi_anlasilir_hataya_cevirir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths = resolve_app_paths(environ={ENV_APP_HOME: str(tmp_path)})
    paths.ensure()

    def patla(*args: object, **kwargs: object) -> None:
        raise PermissionError(13, "dosya kullanımda")

    monkeypatch.setattr(main_mod, "apply_pending_restore", patla)

    with pytest.raises(RestoreFailedError) as hata:
        main_mod.prepare_data(paths, "2026.10.0")

    assert hata.value.exit_code == EXIT_RESTORE_FAILED
    assert "değişmedi" in hata.value.message
    assert PENDING_DB_NAME in hata.value.hint  # vazgeçmenin elle yolu


def test_veritabani_olmadan_bekleyen_guvenlik_dosyasi_uygulanmaz(tmp_path: Path) -> None:
    veri = tmp_path / "data"
    db = veri / "db.sqlite3"
    _db(db, "canli")
    (veri / "guvenlik.json").write_text('{"eski": 1}', encoding="utf-8")
    (veri / PENDING_STATE_NAME).write_text('{"artik": 1}', encoding="utf-8")

    assert apply_pending_restore(db, tmp_path / "backups") is None
    assert (veri / "guvenlik.json").read_text(encoding="utf-8") == '{"eski": 1}'
    assert not (veri / PENDING_STATE_NAME).exists()


def test_ayni_saniyede_ikinci_geri_yukleme_oncekini_ezmez(tmp_path: Path) -> None:
    veri = tmp_path / "data"
    db = veri / "db.sqlite3"
    _db(db, "bir")
    _db(veri / PENDING_DB_NAME, "iki")
    ilk = apply_pending_restore(db, tmp_path / "backups", now=_ZAMAN)
    _db(veri / PENDING_DB_NAME, "uc")

    ikinci = apply_pending_restore(db, tmp_path / "backups", now=_ZAMAN)

    assert ilk is not None and ikinci is not None and ilk != ikinci
    assert _deger(ilk / "db.sqlite3") == "bir"
    assert _deger(ikinci / "db.sqlite3") == "iki"
    assert _deger(db) == "uc"


def test_vazgecme_bekleyen_dosyalari_siler(tmp_path: Path) -> None:
    _db(tmp_path / PENDING_DB_NAME, "yedek")
    (tmp_path / PENDING_STATE_NAME).write_text("{}", encoding="utf-8")

    assert discard_pending_restore(tmp_path) is True
    assert discard_pending_restore(tmp_path) is False
    assert not has_pending_restore(tmp_path)


def test_duz_gunluk_yedek_geri_yuklenebilir(tmp_path: Path) -> None:
    """Uçtan uca (parolasız): günlük yedek → veri değişir → yedek geri yüklenir."""
    veri = tmp_path / "data"
    db = veri / "db.sqlite3"
    _db(db, "sabah")
    yedek = daily_backup(db, tmp_path / "backups", today=date(2026, 11, 13))
    assert yedek is not None
    conn = sqlite3.connect(db)
    conn.execute("UPDATE kayit SET deger = ?", ("aksam-hatali",))
    conn.commit()
    conn.close()

    (veri / PENDING_DB_NAME).write_bytes(yedek.read_bytes())
    apply_pending_restore(db, tmp_path / "backups", now=_ZAMAN)

    assert _deger(db) == "sabah"


def test_acilis_bekleyen_yedegi_butunluk_denetiminden_once_uygular(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Bozuk veritabanı + bekleyen yedek: açılış "veritabanı bozuk" diye DURMAZ."""
    paths = resolve_app_paths(environ={ENV_APP_HOME: str(tmp_path)})
    paths.ensure()
    paths.db_path.write_bytes(b"bozuk" * 100)
    _db(paths.data / PENDING_DB_NAME, "yedek")
    for ad in ("prepare_django", "run_migrations", "write_version_stamp"):
        monkeypatch.setattr(main_mod, ad, lambda *a, **k: None)
    monkeypatch.setattr(main_mod, "has_pending_migrations", lambda: False)

    main_mod.prepare_data(paths, "2026.10.0")

    assert _deger(paths.db_path) == "yedek"
    # Parolasız kurulum: geri yüklenen verinin günlük yedeği de alınır.
    assert (paths.backups / f"gunluk-{date.today().isoformat()}.sqlite3").is_file()
