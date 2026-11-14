"""Otomatik yedekleme — SQLite çevrimiçi görüntü + 14 gün rotasyonu.

**Dosya kopyalama YAPILMAZ.** WAL kipinde işlenmiş sayfaların bir bölümü hâlâ
`-wal` dosyasındadır; `db.sqlite3`'ü tek başına kopyalamak tutarsız (hatta bozuk)
bir yedek üretir. `Connection.backup()` ise SQLite'ın kendi çevrimiçi yedek API'sini
kullanır: kaynak veritabanını sayfa sayfa RAM'e okur, WAL dahil tutarlı bir görüntü
çıkarır.

Yedeğin biçimi uygulama parolasına bağlıdır:

* **Parola kurulu** (`guvenlik.json` var): görüntü diske yalnız `.ddbak` şifreli
  kapsayıcısı olarak yazılır. Açık yedek anahtarı henüz hazır değilse (yükseltme
  sonrası ilk açılış; anahtar ilk kilit açılışında yazılır) yedek ATLANIR — şifreli
  alanları olan veriyi düz yazmak yerine bir açılış beklemek seçildi.
* **Parola kurulu değil** (varsayılan kurulum): görüntü düz `.sqlite3` olarak
  yazılır. Veritabanının kendisi aynı diskte zaten düz durur; düz yedek buna yeni
  bir risk eklemez. 13.11.2026 öncesinde bu kipte HİÇ yedek alınmıyordu (anahtar
  yoktu, yedek sessizce atlanıyordu) — kılavuzun vaat ettiği günlük yedek ancak
  böyle gerçek olur. Parola sonradan kurulursa `encrypt_legacy_backups` bu düz
  yedekleri `.ddbak` biçimine çevirir.

Yedek adları tarihlidir ve deterministiktir: aynı gün ikinci kez açılan program o
günün yedeğini yeniden ÜRETMEZ (sabah alınan yedek, akşam bozulan veriyle ezilmez).
"""

from __future__ import annotations

import logging
import os
import re
import secrets
import shutil
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

from desktop.backup_crypto import (
    BACKUP_SUFFIX,
    BackupCryptoError,
    encrypt_to_path,
    load_public_key,
    recovery_metadata,
)

DAILY_PREFIX = "gunluk"
PRE_MIGRATE_PREFIX = "pre-migrate"
TRANSITION_PREFIX = "pre-parola"
# Geri yükleme sırasında yerinden alınan eski verinin klasörü (desktop/restore.py).
PREVIOUS_PREFIX = "geri-yukleme-oncesi"

# Parolasız kipte yazılan düz yedeğin uzantısı.
PLAIN_SUFFIX = ".sqlite3"
BACKUP_SUFFIXES = (BACKUP_SUFFIX, PLAIN_SUFFIX)
# `apps/okul/services/app_password.py::STATE_FILE_NAME` ile aynı dosya; masaüstü
# kabuğu Django ayağa kalkmadan önce çalıştığı için adı burada yinelenir.
STATE_FILE_NAME = "guvenlik.json"

DEFAULT_KEEP_DAYS = 14
DEFAULT_KEEP_PRE_MIGRATE = 5

_DATE_RE = re.compile(r"(\d{4}-\d{2}-\d{2})")
# Dosya adında güvenli olmayan her şey alt çizgiye döner (sürüm etiketi "1.0/rc:1" olabilir).
_UNSAFE_RE = re.compile(r"[^A-Za-z0-9._-]+")

logger = logging.getLogger("disiplin_defteri.backup")

_LEGACY_PATTERNS = (
    f"{DAILY_PREFIX}-*.sqlite3",
    f"{PRE_MIGRATE_PREFIX}-*.sqlite3",
    f"{TRANSITION_PREFIX}-*.sqlite3",
)


def password_configured(data_dir: Path) -> bool:
    """Uygulama parolası kurulu mu? (`guvenlik.json` veri dizininde duruyor mu?)"""
    return (data_dir / STATE_FILE_NAME).is_file()


def _serialize_supported() -> bool:
    """`sqlite3.Connection.serialize` var mı?

    Yöntem yalnız SQLite kitaplığı serileştirme desteğiyle derlenmişse bulunur. Debian 11'in
    SQLite'ında (3.34) YOKTUR: Linux paketi orada derlendiği için paketlenmiş programda
    `serialize` çağrısı AttributeError verip açılışı durduruyordu (14.11.2026, paketleme
    kapısının `--autotest` adımı yakaladı).
    """
    return hasattr(sqlite3.Connection, "serialize")


def _snapshot_via_file(source: sqlite3.Connection, data_dir: Path) -> bytes:
    """`serialize` yokken görüntüyü geçici dosya üzerinden üretir.

    Geçici dosya veritabanının KENDİ dizinine yazılır (canlı veritabanıyla aynı disk ve aynı
    erişim izinleri; yedek dizinine ya da sistem geçici dizinine düz kopya sızmaz) ve her
    durumda silinir. Parola kuruluyken de bu yol kullanılır: geçici kopya, yanında duran
    canlı `db.sqlite3`'ten daha açık değildir.
    """
    temp = data_dir / f".yedek-goruntu-{os.getpid()}-{secrets.token_hex(4)}.tmp"
    try:
        with closing(sqlite3.connect(temp)) as target:
            source.backup(target)
        return temp.read_bytes()
    finally:
        temp.unlink(missing_ok=True)


def database_snapshot(source_path: Path) -> bytes:
    """WAL dahil tutarlı SQLite görüntüsünü üretir.

    Olağan yol RAM'dedir (düz ara kopya diske yazılmaz). SQLite kitaplığı serileştirmeyi
    desteklemiyorsa (`_serialize_supported`) görüntü veri dizinindeki geçici dosyadan okunur.
    """
    with closing(sqlite3.connect(source_path)) as source:
        if not _serialize_supported():
            return _snapshot_via_file(source, source_path.parent)
        with closing(sqlite3.connect(":memory:")) as target:
            source.backup(target)
            return bytes(target.serialize())


def _write_plain(snapshot: bytes, target: Path) -> None:
    """Düz SQLite görüntüsünü atomik yazar (yarım dosya "sağlam" adıyla kalmaz)."""
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_name(target.name + ".tmp")
    temp.unlink(missing_ok=True)
    try:
        temp.write_bytes(snapshot)
        temp.replace(target)
    finally:
        temp.unlink(missing_ok=True)


def _existing_backup(backup_dir: Path, stem: str) -> Path | None:
    """Aynı adlı yedek (şifreli ya da düz) zaten varsa onu döndürür."""
    for suffix in BACKUP_SUFFIXES:
        candidate = backup_dir / f"{stem}{suffix}"
        if candidate.exists():
            return candidate
    return None


def _copy_database(source_path: Path, backup_dir: Path, stem: str) -> Path:
    """Tutarlı SQLite görüntüsünü yedek dizinine yazar; yazılan dosyayı döndürür.

    Parola kuruluysa şifreli kapsayıcı (anahtar hazır değilse `BackupCryptoError`),
    değilse düz `.sqlite3` — gerekçe dosya başlığında.
    """
    data_dir = source_path.parent
    if password_configured(data_dir):
        target = backup_dir / f"{stem}{BACKUP_SUFFIX}"
        public_key = load_public_key(data_dir)
        encrypt_to_path(
            database_snapshot(source_path),
            target,
            public_key,
            recovery_header=recovery_metadata(data_dir),
        )
        return target
    target = backup_dir / f"{stem}{PLAIN_SUFFIX}"
    _write_plain(database_snapshot(source_path), target)
    return target


def encrypt_legacy_backups(backup_dir: Path, data_dir: Path) -> list[Path]:
    """Düz SQLite yedeklerini atomik olarak şifreli `.ddbak` biçimine çevirir.

    Yalnız parola KURULUYKEN çalışır. Parola kaldırıldıktan sonra `yedekleme.json`
    diskte kalır; o anahtarla şifrelemeyi sürdürmek, parolasız kipte alınan düz
    yedekleri yalnız ESKİ parolayla açılabilir hâle getirirdi.
    """
    if not backup_dir.is_dir() or not password_configured(data_dir):
        return []
    try:
        public_key = load_public_key(data_dir)
    except BackupCryptoError:
        return []
    encrypted: list[Path] = []
    for pattern in _LEGACY_PATTERNS:
        for source in sorted(backup_dir.glob(pattern)):
            target = source.with_suffix(BACKUP_SUFFIX)
            encrypt_to_path(
                source.read_bytes(),
                target,
                public_key,
                recovery_header=recovery_metadata(data_dir),
            )
            source.unlink()
            encrypted.append(target)
    if encrypted:
        logger.info("%d eski düz yedek şifreli biçime dönüştürüldü.", len(encrypted))
    return encrypted


def _safe_name(value: str) -> str:
    return _UNSAFE_RE.sub("_", value).strip("_") or "bilinmeyen"


def _parse_date(path: Path) -> date | None:
    match = _DATE_RE.search(path.stem)
    if match is None:
        return None
    try:
        return date.fromisoformat(match.group(1))
    except ValueError:
        return None


def _glob_backups(backup_dir: Path, prefix: str) -> list[Path]:
    """Bir önekin şifreli ve düz bütün yedekleri."""
    return [path for suffix in BACKUP_SUFFIXES for path in backup_dir.glob(f"{prefix}-*{suffix}")]


@dataclass(frozen=True)
class BackupInfo:
    """Yedek dizinindeki bir dosyanın arayüzde gösterilecek özeti (kişisel veri içermez)."""

    name: str
    kind: str
    taken_on: date | None
    size: int
    encrypted: bool


_KINDS = (
    (DAILY_PREFIX, "daily"),
    (PRE_MIGRATE_PREFIX, "pre_migrate"),
    (TRANSITION_PREFIX, "transition"),
)


def list_backups(backup_dir: Path) -> list[BackupInfo]:
    """Programın ürettiği yedekleri en yeniden eskiye listeler.

    Adı program desenlerine uymayan dosyalar (elle konmuş kopyalar) listelenmez;
    onlar arayüzden "dosya seç" ile geri yüklenir.
    """
    if not backup_dir.is_dir():
        return []
    found: list[tuple[float, BackupInfo]] = []
    for prefix, kind in _KINDS:
        for path in _glob_backups(backup_dir, prefix):
            try:
                stat = path.stat()
            except OSError:
                continue
            info = BackupInfo(
                name=path.name,
                kind=kind,
                taken_on=_parse_date(path),
                size=stat.st_size,
                encrypted=path.suffix == BACKUP_SUFFIX,
            )
            found.append((stat.st_mtime, info))
    found.sort(key=lambda item: (item[1].taken_on or date.min, item[0]), reverse=True)
    return [info for _, info in found]


def daily_backup(db_path: Path, backup_dir: Path, *, today: date | None = None) -> Path | None:
    """Günün yedeğini alır. Veritabanı yoksa veya yedek zaten varsa yeniden üretmez."""
    if not db_path.exists():
        return None
    day = today or date.today()
    stem = f"{DAILY_PREFIX}-{day.isoformat()}"
    existing = _existing_backup(backup_dir, stem)
    if existing is not None:
        return existing
    try:
        target = _copy_database(db_path, backup_dir, stem)
    except BackupCryptoError:
        logger.warning("Şifreli yedekleme anahtarı hazır değil; günlük yedek atlandı.")
        return None
    except OSError as exc:
        # Disk dolu / klasör yazılamıyor / antivirüs dosyayı tutuyor: günlük yedek
        # programın açılmasını ENGELLEMEZ. Eksiklik arayüzde görünür (Güvenlik
        # ekranı "bugünün yedeği alınamadı" der); göç öncesi yedek ise ayrı ve katıdır.
        logger.error("Günlük yedek yazılamadı (%s).", exc.__class__.__name__)
        return None
    logger.info("Günlük yedek alındı: %s", target.name)
    return target


def pre_migrate_backup(
    db_path: Path,
    backup_dir: Path,
    app_version: str,
    *,
    today: date | None = None,
) -> Path | None:
    """Şema güncellemesinden ÖNCE ayrı bir kopya alır (yükseltme geri alınabilsin)."""
    if not db_path.exists():
        return None
    day = today or date.today()
    stem = f"{PRE_MIGRATE_PREFIX}-{_safe_name(app_version)}-{day.isoformat()}"
    existing = _existing_backup(backup_dir, stem)
    if existing is not None:
        return existing
    try:
        target = _copy_database(db_path, backup_dir, stem)
    except BackupCryptoError:
        logger.warning("Şifreli yedekleme anahtarı hazır değil; güncelleme yedeği atlandı.")
        return None
    logger.info("Güncelleme öncesi yedek alındı: %s", target.name)
    return target


def rotate_backups(
    backup_dir: Path,
    *,
    keep_days: int = DEFAULT_KEEP_DAYS,
    keep_pre_migrate: int = DEFAULT_KEEP_PRE_MIGRATE,
    today: date | None = None,
) -> list[Path]:
    """Eskimiş yedekleri siler; sildiklerini döndürür.

    Günlük yedekler GÜN (varsayılan 14), güncelleme öncesi yedekler ADET
    (varsayılan son 5) ile sınırlanır — ikincisi haftalar sonra fark edilen bir
    yükseltme sorununda hâlâ elde olmalıdır. Program dışı/elle konmuş dosyalara
    (adı desenlerimize uymayan her şey) DOKUNULMAZ.

    Geri yükleme öncesi veri klasörleri (`geri-yukleme-oncesi-*`) de günlük
    yedeklerle aynı sürede silinir: içlerinde veritabanının ham kopyası durur ve
    imha edilmiş kayıtların (md. 157/7) süresiz saklanması istenmez.
    """
    if not backup_dir.is_dir():
        return []
    day = today or date.today()
    removed: list[Path] = []

    cutoff = day - timedelta(days=keep_days)
    # Yarıda kalmış yazımların artıkları (yalnız kendi öneklerimiz).
    for prefix in (DAILY_PREFIX, PRE_MIGRATE_PREFIX, TRANSITION_PREFIX):
        for path in backup_dir.glob(f"{prefix}-*.tmp"):
            path.unlink(missing_ok=True)
    for path in sorted(backup_dir.glob(f"{PREVIOUS_PREFIX}-*")):
        taken = _parse_date(path)
        if path.is_dir() and taken is not None and taken < cutoff:
            shutil.rmtree(path, ignore_errors=True)
            removed.append(path)
    for path in sorted(_glob_backups(backup_dir, DAILY_PREFIX)):
        taken = _parse_date(path)
        if taken is not None and taken < cutoff:
            path.unlink(missing_ok=True)
            removed.append(path)

    pre_migrate = [
        path
        for path in _glob_backups(backup_dir, PRE_MIGRATE_PREFIX)
        if _parse_date(path) is not None
    ]
    # En yeni tarih başta; aynı gün birden fazlaysa ad sırası belirleyicidir.
    pre_migrate.sort(key=lambda p: (_parse_date(p) or date.min, p.name), reverse=True)
    for path in pre_migrate[keep_pre_migrate:]:
        path.unlink(missing_ok=True)
        removed.append(path)

    if removed:
        logger.info("Eskimiş %d yedek silindi.", len(removed))
    return removed
