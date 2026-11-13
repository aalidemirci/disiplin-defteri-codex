"""Yedekten geri yükleme — bekletilen yedeğin AÇILIŞTA uygulanması.

Geri yükleme iki adımdır:

1. **Bekletme** (program açıkken, `apps/okul/services/restore_backup.py`): seçilen
   yedek çözülür, doğrulanır ve veri dizinine `geri-yukleme-bekliyor.sqlite3`
   adıyla yazılır. Yedeğin veri anahtarı bu kurulumunkinden farklıysa yedeğin
   kendi güvenlik başlığı da `geri-yukleme-bekliyor.guvenlik.json` olarak bekletilir.
2. **Uygulama** (bu modül, bir sonraki açılışta): çalışan veritabanı yedek
   dizinindeki `geri-yukleme-oncesi-<zaman>/` klasörüne TAŞINIR, bekleyen dosya
   `db.sqlite3` olur.

Neden iki adım: program açıkken Django bağlantıları ve WAL dosyası canlıdır;
`db.sqlite3` dosyasını o anda değiştirmek tutarsız veri üretir. Açılışta ise
tek-instance kilidi alınmış, henüz hiçbir bağlantı açılmamıştır.

Geri dönüş: eski veritabanı SİLİNMEZ. Yanlış yedek seçildiyse
`geri-yukleme-oncesi-*` klasöründeki dosyalar veri klasörüne geri kopyalanır
(docs/kurulum.md §5.1). Bu klasörler günlük yedeklerle aynı sürede (14 gün)
rotasyonla silinir (`desktop/backup.py::rotate_backups`).

Hata hâli: eski dosyalar taşınamazsa (Windows'ta başka bir süreç tutuyorsa)
taşınanlar GERİ konur, yarım klasör silinir ve `OSError` yükseltilir; bekleyen
yedek yerinde kalır, canlı veri değişmez. `desktop/main.py` bunu anlaşılır bir
açılış hatasına çevirir.
"""

from __future__ import annotations

import logging
import shutil
import sqlite3
import time
from contextlib import closing
from datetime import datetime
from pathlib import Path

from desktop.backup import PREVIOUS_PREFIX, STATE_FILE_NAME
from desktop.backup_crypto import CONFIG_FILE_NAME

PENDING_DB_NAME = "geri-yukleme-bekliyor.sqlite3"
PENDING_STATE_NAME = "geri-yukleme-bekliyor.guvenlik.json"

_SIDE_SUFFIXES = ("", "-wal", "-shm")
# Windows'ta az önce kapanan süreç ya da antivirüs dosyayı kısa süre tutabilir.
_MOVE_ATTEMPTS = 5
_MOVE_WAIT_SECONDS = 0.4

logger = logging.getLogger("disiplin_defteri.restore")


def sqlite_is_healthy(path: Path) -> bool:
    """Dosya açılabilen ve hızlı bütünlük denetiminden geçen bir SQLite veritabanı mı?"""
    try:
        with closing(sqlite3.connect(path)) as connection:
            rows = connection.execute("PRAGMA integrity_check(1)").fetchall()
    except sqlite3.Error:
        return False
    return bool(rows) and str(rows[0][0]) == "ok"


def has_pending_restore(data_dir: Path) -> bool:
    return (data_dir / PENDING_DB_NAME).is_file()


def discard_pending_restore(data_dir: Path) -> bool:
    """Bekleyen geri yüklemeyi iptal eder; bir şey silindiyse True.

    Önce veritabanı silinir: bekleyen veritabanı "uygula" işaretidir; o yokken
    kalan güvenlik başlığı zararsız artıktır.
    """
    removed = False
    for name in (PENDING_DB_NAME, PENDING_STATE_NAME):
        path = data_dir / name
        if path.is_file():
            path.unlink()
            removed = True
    return removed


def _previous_dir(backup_dir: Path, now: datetime) -> Path:
    base = f"{PREVIOUS_PREFIX}-{now.strftime('%Y-%m-%d-%H%M%S')}"
    candidate = backup_dir / base
    counter = 2
    while candidate.exists():
        candidate = backup_dir / f"{base}-{counter}"
        counter += 1
    return candidate


def _rename(source: Path, target: Path, *, wait: float) -> None:
    """Aynı sürücüde atomik yeniden adlandırma; geçici kilitlere karşı yeniden dener.

    `shutil.move` KULLANILMAZ: yeniden adlandırma başarısız olunca kopyala+sil
    yoluna düşer ve silme de başarısızsa dosyanın iki kopyası kalır.
    """
    for attempt in range(_MOVE_ATTEMPTS):
        try:
            source.replace(target)
            return
        except PermissionError:
            if attempt == _MOVE_ATTEMPTS - 1:
                raise
            time.sleep(wait)


def _move_current_database(db_path: Path, previous: Path, *, wait: float) -> None:
    """Çalışan veritabanını (WAL/SHM ile) `previous` altına taşır — ya hep ya hiç."""
    previous.mkdir(parents=True)
    moved: list[tuple[Path, Path]] = []
    try:
        for suffix in _SIDE_SUFFIXES:
            source = db_path.with_name(db_path.name + suffix)
            if source.exists():
                target = previous / source.name
                _rename(source, target, wait=wait)
                moved.append((source, target))
    except OSError:
        for source, target in reversed(moved):
            try:
                target.replace(source)
            except OSError:  # pragma: no cover — geri sarma da başarısız; kopya klasörde kalır
                logger.error("Geri sarma başarısız: %s yerine konamadı.", source.name)
        shutil.rmtree(previous, ignore_errors=True)
        raise


def apply_pending_restore(
    db_path: Path,
    backup_dir: Path,
    *,
    now: datetime | None = None,
    retry_wait: float = _MOVE_WAIT_SECONDS,
) -> Path | None:
    """Bekleyen yedeği yerine koyar; eski verinin taşındığı klasörü döndürür.

    Bekleyen yedek yoksa ya da bozuksa hiçbir şeye dokunmadan None döner — bozuk
    bir bekleyen dosya programın açılmasını ENGELLEMEZ, yalnız atılır.

    Adım sırası kesintiye dayanıklıdır; her adımdan sonra süreç ölse de bir sonraki
    açılış işi tamamlar ve hiçbir aşamada veri anahtarıyla uyuşmayan bir dosya
    kalıcı olmaz:

        1. eski veritabanı taşınır ........ kesilirse: bekleyen duruyor, yeniden uygulanır
        2. `yedekleme.json` silinir ........ güvenlik dosyası değişecekse; bayat açık
                                             anahtar ASLA yeni güvenlik dosyasıyla yan
                                             yana kalmaz (ilk kilit açılışında yeniden üretilir)
        3. güvenlik dosyası yerine konur
        4. bekleyen veritabanı yerine konur (işaret dosyası; en son)
    """
    data_dir = db_path.parent
    pending_db = data_dir / PENDING_DB_NAME
    pending_state = data_dir / PENDING_STATE_NAME
    if not pending_db.is_file():
        # Veritabanı olmadan güvenlik dosyası uygulanmaz (yarım bekletme artığı).
        pending_state.unlink(missing_ok=True)
        return None
    if not sqlite_is_healthy(pending_db):
        logger.error("Bekleyen geri yükleme dosyası bozuk; geri yükleme yapılmadı.")
        discard_pending_restore(data_dir)
        return None

    previous = _previous_dir(backup_dir, now or datetime.now())
    _move_current_database(db_path, previous, wait=retry_wait)

    if pending_state.is_file():
        current_state = data_dir / STATE_FILE_NAME
        if current_state.is_file():
            shutil.copy2(current_state, previous / STATE_FILE_NAME)
        (data_dir / CONFIG_FILE_NAME).unlink(missing_ok=True)
        pending_state.replace(current_state)

    pending_db.replace(db_path)
    logger.info("Yedekten geri yüklendi; önceki veri %s klasörüne taşındı.", previous.name)
    return previous
