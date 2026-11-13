"""Açılış hataları — Türkçe mesaj + çözüm ipucu + süreç çıkış kodu.

Her hata tipinin kendi çıkış kodu vardır; `--autotest` kipi ve paket kurulum
testleri (CI) bu kodlara bakar. Mesajlar doğrudan kullanıcıya gösterilir
(`dialogs.show_error`), bu yüzden teknik terim değil eylem içerirler.
"""

from __future__ import annotations

# Süreç çıkış kodları (0 = başarılı).
EXIT_OK = 0
EXIT_UNEXPECTED = 1
EXIT_ALREADY_RUNNING = 2
EXIT_DATABASE_CORRUPT = 3
EXIT_SCHEMA_TOO_NEW = 4
EXIT_MIGRATION_FAILED = 5
EXIT_SERVER_FAILED = 6
EXIT_WEBVIEW_UNAVAILABLE = 7
# Paket teşhis kipi (`--pdf-duman`): Türkçe PDF üretimi/font zinciri bozuk.
EXIT_PDF_SMOKE_FAILED = 8
# Paket teşhis kipi (`--kripto-duman`): parola zinciri (Argon2id/Fernet) bozuk.
EXIT_CRYPTO_SMOKE_FAILED = 9
# Arayüzden hazırlanan yedek açılışta yerine konamadı (desktop/restore.py).
EXIT_RESTORE_FAILED = 10

# Yedekten ELLE dönüş adımları — "veritabanı bozuk" ve "güncellenemedi" iletileri
# ile docs/kurulum.md §5.1 aynı yolu anlatır; metin tek yerde durur.
MANUAL_RESTORE_STEPS = (
    "1) Veri klasöründeki 'db.sqlite3' dosyasını (varsa 'db.sqlite3-wal' ve "
    "'db.sqlite3-shm' ile birlikte) SİLMEDEN başka bir klasöre taşıyın.\n"
    "2) Yedekler klasöründeki en son yedeğin uzantısı '.sqlite3' ise: onu veri "
    "klasörüne 'db.sqlite3' adıyla kopyalayıp programı yeniden açın.\n"
    "3) Uzantısı '.ddbak' ise (şifreli yedek) adını değiştirerek kopyalamak İŞE YARAMAZ: "
    "programı açın; açılan ekrandaki (kilit ekranı ya da kurulum sihirbazı) "
    "'Yedekten geri yükle' bölümünden yedeği seçip yedeğin parolasını girin, "
    "sonra programı kapatıp yeniden açın."
)


class StartupError(Exception):
    """Program açılışını durduran hata (pencere AÇILMAZ)."""

    exit_code: int = EXIT_UNEXPECTED
    title: str = "Disiplin Defteri açılamadı"

    def __init__(self, message: str, *, hint: str = "") -> None:
        super().__init__(message)
        self.message = message
        self.hint = hint

    @property
    def full_message(self) -> str:
        """Kullanıcıya gösterilecek tam metin (mesaj + varsa ipucu)."""
        return f"{self.message}\n\n{self.hint}" if self.hint else self.message


class AlreadyRunningError(StartupError):
    """Program zaten açık — ikinci kopya pencere açmaz."""

    exit_code = EXIT_ALREADY_RUNNING
    title = "Disiplin Defteri zaten çalışıyor"


class DatabaseCorruptError(StartupError):
    """SQLite bütünlük denetimi başarısız — veri dosyası bozuk."""

    exit_code = EXIT_DATABASE_CORRUPT
    title = "Veritabanı bozuk"


class SchemaTooNewError(StartupError):
    """Veri, programın daha yeni bir sürümüyle yazılmış — eski sürüm açamaz."""

    exit_code = EXIT_SCHEMA_TOO_NEW
    title = "Program sürümü eski"


class MigrationError(StartupError):
    """`migrate --no-input` başarısız — pencere açılmaz, yedekten dönüş önerilir."""

    exit_code = EXIT_MIGRATION_FAILED
    title = "Veritabanı güncellenemedi"


class ServerStartError(StartupError):
    """Gömülü sunucu (waitress) ayağa kalkmadı."""

    exit_code = EXIT_SERVER_FAILED
    title = "Program başlatılamadı"


class RestoreFailedError(StartupError):
    """Bekleyen geri yükleme uygulanamadı — veri eski hâliyle yerinde bırakıldı."""

    exit_code = EXIT_RESTORE_FAILED
    title = "Yedekten geri yükleme tamamlanamadı"


class WebViewUnavailableError(StartupError):
    """Pencere motoru yok (Windows'ta WebView2 kurulu değil)."""

    exit_code = EXIT_WEBVIEW_UNAVAILABLE
    title = "Pencere açılamadı"
