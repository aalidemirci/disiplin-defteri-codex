"""Yedekten geri yükleme — yedeği doğrular ve bir sonraki açılış için bekletir.

Akış (ayrıntı `desktop/restore.py` başlığında):

    yedek (.sqlite3 | .ddbak) ──► çöz ──► doğrula ──► veri dizininde BEKLET
                                                          │ program yeniden açılınca
                                                          ▼
                                    eski veri `backups/geri-yukleme-oncesi-*` altına
                                    taşınır, bekleyen dosya `db.sqlite3` olur

Program açıkken veritabanı DEĞİŞTİRİLMEZ: bekletme yalnız dosya yazar, geri
alınabilir (`cancel_pending`) ve kullanıcı programı yeniden başlatana dek hiçbir
kaydı etkilemez.

HANGİ GÜVENLİK DOSYASI GEÇERLİ OLUR? Şifreli yedek (`.ddbak`) kendi güvenlik
başlığını taşır (parola KDF'i + sarmalanmış veri anahtarı); bu sayede alındığı
günkü parola ya da kurtarma anahtarıyla BAŞKA bir bilgisayarda da açılır. Başlığın
`guvenlik.json` olarak bekletilmesi ise veri anahtarına bağlıdır:

* Yedeğin veri anahtarı bu kurulumunkiyle AYNI (olağan durum: aynı kurulumun eski
  bir günü) → başlık bekletilmez, bugünkü `guvenlik.json` kalır. Parola
  değiştirildikten sonra eski bir yedeğe dönmek parolayı ESKİSİNE döndürmez.
* Veri anahtarı FARKLI (başka kurulum, boş kurulum, parola kaldırılıp yeniden
  kurulmuş) → başlık bekletilir; geri yüklenen alanlar ancak o anahtarla okunur.
  Açılıştan sonra geçerli parola yedeğin parolasıdır; kullanıcı bunu uyarı olarak görür.
* Alanları şifreli DÜZ dosya (ör. `geri-yukleme-oncesi-*/db.sqlite3`) yalnız bu
  kurulumun anahtarıyla şifreliyse kabul edilir; aksi hâlde açılamayacak bir
  kurulum üretmemek için reddedilir (elle dönüş kılavuzda: docs/kurulum.md §5.1).

Uçlar kilit kapısından muaftır (`/api/v1/security/…`): kilit açılamıyorken ya da
kurulum sihirbazı tamamlanmamışken de yedekten dönülebilmelidir. Yanıtlar kişisel
veri içermez (dosya adı, tarih, boyut).
"""

from __future__ import annotations

import json
import logging
import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Any

from desktop.backup import BACKUP_SUFFIXES, list_backups
from desktop.backup_crypto import MAGIC, decrypt_bytes, embedded_recovery_metadata
from desktop.restore import (
    PENDING_DB_NAME,
    PENDING_STATE_NAME,
    discard_pending_restore,
    has_pending_restore,
)
from django.db import DatabaseError
from django.db.migrations.loader import MigrationLoader

from apps.okul.models import SchoolConfig
from apps.okul.services import app_password
from shared import crypto

logger = logging.getLogger("disiplin_defteri.restore")

SQLITE_MAGIC = b"SQLite format 3\x00"
_OWN_APPS = ("okul", "disiplin")

# Yedek belleğe okunur (çözme + doğrulama); okul verisi bunun çok altındadır.
MAX_RESTORE_BYTES = 1024 * 1024 * 1024

# Yedeğin güvenlik başlığı doğrulanmamış girdidir: aşırı Argon2 maliyeti süreci
# düşürebilir. Üretim profili 64 MiB / t=3 / p=4; sınırlar bunun çok üstündedir.
_MAX_KDF_MEMORY_KIB = 1024 * 1024
_MAX_KDF_TIME_COST = 20
_MAX_KDF_PARALLELISM = 16

RESTART_MESSAGE = (
    "Yedek doğrulandı ve hazırlandı. Geri yükleme, programı kapatıp yeniden "
    "açtığınızda uygulanır; şu anki kayıtlar yedekler klasöründe "
    "'geri-yukleme-oncesi-…' adıyla saklanır."
)
_KEY_CHANGES_WARNING = (
    "Bu yedek farklı bir güvenlik anahtarıyla alınmış. Geri yüklemeden sonra geçerli "
    "uygulama parolası ve kurtarma anahtarı, yedeğin alındığı tarihteki parola ve "
    "kurtarma anahtarı olur."
)
_PLAIN_FIELDS_WARNING = (
    "Bu yedekteki kimlik ve veli alanları şifresiz. Uygulama parolanız geçerli kalır; "
    "geri yüklemeden sonraki ilk kilit açılışında alanlar yeniden şifrelenir."
)


class RestoreError(ValueError):
    """Kullanıcıya gösterilecek Türkçe geri yükleme hatası (view 400'e çevirir)."""


def _data_dir() -> Path:
    return app_password.state_path().parent


def _current_fingerprint() -> str:
    """Bu kurulumun `guvenlik.json` dosyasının açtığı veri anahtarının parmak izi.

    Parola kurulu değilse, güvenlik dosyası okunamıyorsa ya da veritabanı henüz
    yoksa (boş kurulum) boş döner — "bu kurulumun anahtarı yok/bilinmiyor".
    """
    try:
        if app_password.read_state() is None:
            return ""
        return str(SchoolConfig.load().app_password_hash or "")
    except (app_password.AppPasswordError, DatabaseError):
        return ""


# ---------------------------------------------------------------------------
# Durum
# ---------------------------------------------------------------------------
def overview() -> dict[str, Any]:
    """Yedek dizininin özeti: son günlük yedek, liste, bekleyen geri yükleme."""
    backups = list_backups(app_password.backup_dir())
    last_daily = next((b for b in backups if b.kind == "daily"), None)
    return {
        "backup_dir": str(app_password.backup_dir()),
        "last_daily_on": (
            last_daily.taken_on.isoformat() if last_daily and last_daily.taken_on else None
        ),
        "pending_restore": has_pending_restore(_data_dir()),
        "backups": [
            {
                "name": b.name,
                "kind": b.kind,
                "taken_on": b.taken_on.isoformat() if b.taken_on else None,
                "size": b.size,
                "encrypted": b.encrypted,
            }
            for b in backups
        ],
    }


def cancel_pending() -> dict[str, Any]:
    """Bekleyen geri yüklemeden vazgeçer (program yeniden açılmadan önce)."""
    discard_pending_restore(_data_dir())
    return overview()


# ---------------------------------------------------------------------------
# Çözme
# ---------------------------------------------------------------------------
def _parse_state(metadata: bytes) -> dict[str, Any]:
    """Yedeğin güvenlik başlığını ayrıştırır ve KDF maliyetini sınırlar."""
    try:
        state: Any = json.loads(metadata)
    except ValueError as exc:
        raise RestoreError("Yedeğin güvenlik başlığı okunamadı; dosya bozuk olabilir.") from exc
    kdf = state.get("kdf") if isinstance(state, dict) else None
    if not isinstance(kdf, dict):
        raise RestoreError("Yedeğin güvenlik başlığı beklenen biçimde değil.")
    limits = (
        ("memory_cost", _MAX_KDF_MEMORY_KIB),
        ("time_cost", _MAX_KDF_TIME_COST),
        ("parallelism", _MAX_KDF_PARALLELISM),
    )
    for key, limit in limits:
        value = kdf.get(key)
        if type(value) is not int or not 1 <= value <= limit:
            raise RestoreError("Yedeğin güvenlik başlığı geçersiz; bu yedek açılamaz.")
    return dict(state)


def _decrypt(content: bytes, *, password: str, recovery_key: str) -> tuple[bytes, bytes, bytes]:
    """Şifreli kapsayıcıyı açar → (düz veritabanı, veri anahtarı, güvenlik başlığı)."""
    metadata = embedded_recovery_metadata(content)
    if not password and not recovery_key:
        # Kilit açıksa ve yedek bu kurulumun anahtarıyla alınmışsa parola yeniden sorulmaz.
        active = crypto.active_key()
        if active is not None:
            try:
                return decrypt_bytes(content, active), active, metadata
            except ValueError:
                pass
        raise RestoreError(
            "Bu yedek şifreli. Yedeğin alındığı tarihteki uygulama parolasını ya da "
            "kurtarma anahtarını girin."
        )
    if not metadata:
        raise RestoreError(
            "Bu şifreli yedek kendi güvenlik bilgisini taşımıyor; parolayla açılamaz."
        )
    state = _parse_state(metadata)
    try:
        data_key = app_password.data_key_from_state(
            state, password=password, recovery_key=recovery_key
        )
    except app_password.AppPasswordError:
        raise  # Türkçe iletili: yanlış parola / eksik sarmal
    except Exception as exc:  # noqa: BLE001 — bozuk başlık (base64, tür, KDF) tek iletiye çıkar
        raise RestoreError("Yedeğin güvenlik başlığı geçersiz; bu yedek açılamaz.") from exc
    return decrypt_bytes(content, data_key), data_key, metadata


# ---------------------------------------------------------------------------
# Doğrulama
# ---------------------------------------------------------------------------
def _inspect(path: Path) -> str:
    """Dosyanın sağlam bir Disiplin Defteri veritabanı olduğunu doğrular.

    Veritabanındaki anahtar parmak izini döndürür (alanlar şifreli değilse "").
    """
    config_table = SchoolConfig._meta.db_table
    try:
        with closing(sqlite3.connect(path)) as connection:
            rows = connection.execute("PRAGMA integrity_check(1)").fetchall()
            if not rows or str(rows[0][0]) != "ok":
                raise RestoreError("Yedek dosyası bozuk (bütünlük denetimi başarısız).")
            tables = {
                str(row[0])
                for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
            }
            if "django_migrations" not in tables or config_table not in tables:
                raise RestoreError("Bu dosya bir Disiplin Defteri veritabanı yedeği değil.")
            placeholders = ",".join("?" for _ in _OWN_APPS)
            applied = {
                (str(app), str(name))
                for app, name in connection.execute(
                    f"SELECT app, name FROM django_migrations WHERE app IN ({placeholders})",  # noqa: S608 — yer tutucular sabit
                    _OWN_APPS,
                )
            }
            columns = {
                str(row[1]) for row in connection.execute(f"PRAGMA table_info({config_table})")
            }
            fingerprint = ""
            if "app_password_hash" in columns:
                row = connection.execute(
                    f"SELECT app_password_hash FROM {config_table} LIMIT 1"  # noqa: S608 — tablo adı modelden
                ).fetchone()
                fingerprint = str(row[0] or "") if row else ""
    except sqlite3.Error as exc:
        raise RestoreError("Yedek dosyası bir SQLite veritabanı olarak açılamadı.") from exc

    known = set(MigrationLoader(None, ignore_no_migrations=True).disk_migrations)
    if applied - known:
        raise RestoreError(
            "Bu yedek programın daha yeni bir sürümüyle alınmış. Önce programı güncelleyin, "
            "sonra yedeği geri yükleyin."
        )
    return fingerprint


def _security_plan(fingerprint: str, data_key: bytes | None, metadata: bytes) -> tuple[bool, str]:
    """Güvenlik başlığı bekletilecek mi, kullanıcıya ne söylenecek? (dosya başlığı)"""
    current = _current_fingerprint()
    if not fingerprint:
        warning = _PLAIN_FIELDS_WARNING if app_password.is_password_set() else ""
        return False, warning
    if data_key is None:
        # Düz dosya, alanları şifreli: anahtarı ancak bu kurulumun güvenlik dosyası olabilir.
        if fingerprint != current:
            raise RestoreError(
                "Bu yedekteki kimlik ve veli alanları, bu kurulumda bulunmayan bir güvenlik "
                "anahtarıyla şifreli; geri yüklenirse kayıtlar açılamaz. Yedeğin yanındaki "
                "guvenlik.json dosyasıyla birlikte elle geri dönün (kılavuz §5.1)."
            )
        return False, ""
    if crypto.key_fingerprint(data_key) != fingerprint:
        raise RestoreError(
            "Yedeğin anahtarı içindeki kayıtlarla eşleşmiyor; bu yedek geri yüklenemez."
        )
    if fingerprint == current:
        return False, ""  # aynı veri anahtarı: bugünkü parola geçerli kalır
    if not metadata:
        raise RestoreError(
            "Yedekteki alanlar şifreli ama yedek güvenlik bilgisini taşımıyor; "
            "geri yüklenirse kayıtlar okunamaz."
        )
    return True, _KEY_CHANGES_WARNING


# ---------------------------------------------------------------------------
# Bekletme
# ---------------------------------------------------------------------------
def stage_restore(content: bytes, *, password: str = "", recovery_key: str = "") -> dict[str, Any]:
    """Yedek içeriğini çözer, doğrular ve bir sonraki açılış için bekletir."""
    if len(content) > MAX_RESTORE_BYTES:
        raise RestoreError("Yedek dosyası beklenenden büyük (1 GB üstü); geri yüklenemez.")
    encrypted = content.startswith(MAGIC)
    data_key: bytes | None = None
    metadata = b""
    if encrypted:
        plain, data_key, metadata = _decrypt(content, password=password, recovery_key=recovery_key)
    elif content.startswith(SQLITE_MAGIC):
        plain = content
    else:
        raise RestoreError(
            "Dosya tanınmadı. Programın ürettiği '.sqlite3' ya da '.ddbak' uzantılı bir "
            "yedek seçin."
        )
    if not plain.startswith(SQLITE_MAGIC):
        raise RestoreError("Yedeğin içeriği bir SQLite veritabanı değil.")

    data_dir = _data_dir()
    data_dir.mkdir(parents=True, exist_ok=True)
    pending_db = data_dir / PENDING_DB_NAME
    pending_state = data_dir / PENDING_STATE_NAME
    temp = pending_db.with_name(pending_db.name + ".tmp")
    state_temp = pending_state.with_name(pending_state.name + ".tmp")
    try:
        temp.unlink(missing_ok=True)
        temp.write_bytes(plain)
        stage_state, warning = _security_plan(_inspect(temp), data_key, metadata)

        # Sıra kesintiye dayanıklı: bekleyen VERİTABANI "uygula" işaretidir. Önce
        # önceki bekletme tümüyle kaldırılır (işaret yok → hiçbir şey uygulanmaz),
        # sonra güvenlik başlığı, EN SON veritabanı yerine konur. Hiçbir kesinti
        # noktasında bir veritabanı başka bir yedeğin güvenlik başlığıyla kalmaz.
        discard_pending_restore(data_dir)
        if stage_state:
            state_temp.write_bytes(metadata)
            state_temp.replace(pending_state)
        temp.replace(pending_db)
    except OSError as exc:
        logger.error("Yedek bekletilemedi (%s).", exc.__class__.__name__)
        raise RestoreError(
            "Yedek veri klasörüne yazılamadı (disk dolu ya da dosya başka bir program "
            "tarafından kullanılıyor olabilir). Yeniden deneyin."
        ) from exc
    finally:
        temp.unlink(missing_ok=True)
        state_temp.unlink(missing_ok=True)

    logger.info("Yedek geri yükleme için bekletildi (şifreli=%s).", encrypted)
    return {**overview(), "message": RESTART_MESSAGE, "warning": warning}


def stage_local_backup(name: str, *, password: str = "", recovery_key: str = "") -> dict[str, Any]:
    """Yedekler klasöründeki bir dosyayı (adıyla) geri yükleme için bekletir.

    Yalnız programın listelediği yedekler seçilebilir: ad, `list_backups` çıktısında
    BİREBİR bulunmalıdır. Serbest ad kabul edilmez — yol bileşeni, sürücü harfi ya
    da Windows'a özgü ad biçimleriyle dizin dışına çıkış bu yüzden mümkün değildir.
    """
    clean = name.strip()
    directory = app_password.backup_dir()
    if not clean.endswith(BACKUP_SUFFIXES) or clean not in {
        b.name for b in list_backups(directory)
    }:
        raise RestoreError("Seçilen yedek yedekler klasöründe bulunamadı.")
    try:
        content = (directory / clean).read_bytes()
    except OSError as exc:
        raise RestoreError("Yedek dosyası okunamadı.") from exc
    return stage_restore(content, password=password, recovery_key=recovery_key)
