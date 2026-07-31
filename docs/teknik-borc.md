# Teknik Borç Kütüğü

Bilinen, kabul edilmiş eksikler. Her satır: **ne**, **neden bırakıldı**, **ne
zaman kapanmalı**. Kapanan kalem silinmez, "KAPANDI (tarih/commit)" işaretlenir.

Son güncelleme: 26.07.2026.

---

## Doğrulanamayan (ortam kısıtı — kod yazıldı, koşulmadı)

| # | Kalem | Neden | Ne zaman kapanır |
|---|---|---|---|
| D3 | **Qt penceresi hiç açılmadı** (ekran yok) — Wayland oturumunda `QT_QPA_PLATFORM=xcb` gereği | Konteynerde görüntü sunucusu yok | Pardus saha provasında |
| D4 | **Paketlenmiş ikili üzerinden gerçek evrak üretimi** — duman testi yalnız WeasyPrint+font zincirini izole ediyor, `documents.py` + 25 şablon zinciri paket içinde koşmadı | DB + fixture gerekiyordu | Saha provasında bir dosya açıp EK-1 üretilerek |
| D5 | **`.deb` yükseltme yolu** (eski sürüm üstüne kurulum) | Yalnız temiz kurulum + kaldırma sınandı | İkinci sürüm çıkarken |
| D6 | **Windows başlatıcı yolları** (`msvcrt.locking`, `winreg`, `MessageBoxW`) | CI'da `--autotest` geçiyor ama tek-instance kilidinin İKİNCİ kopyayla çakışması ve WebView2 yokluğu senaryosu ayrıca koşulmadı | Saha provasında |
| D7 | **Argon2 cffi ikilisinin paket içinde toplanması** | Spec'e `hiddenimports` sigortası kondu; CI `--autotest`'i parola KURULU değilken koşuyor, yani Argon2 yolu hiç çalışmıyor | `--autotest`'e parola kurma/açma adımı eklenerek |
| D8 | **Paketlenmiş pencerede gerçek dosya indirme** (XLSX + PDF + TXT) | pywebview indirme izni ve Blob yaşam döngüsü kod/test düzeyinde düzeltildi; başsız CI işletim sistemi “Kaydet” akışını doğrulamaz | Windows ve Pardus saha provasında üç dosya türü indirilerek |

## Kabul edilmiş tasarım bedelleri

| # | Kalem | Gerekçe |
|---|---|---|
| K1 | **`uq_student_tckn_alive` şifreli kipte etkisiz** — Fernet aynı metni farklı token'a çevirir | Blind index alınmadı (tasarım §10.2: yerel ölçek ≤1000 kayıt). Tekillik servis katmanında: `selectors.find_student_by_tckn` |
| K2 | **Dosya ekleri (MEDIA_ROOT) şifrelenmiyor** | Yalnız alan şifrelemesi seçildi; UI metni bunu açıkça söylüyor. Tam koruma için BitLocker/LUKS |
| K3 | **Boşta-kalma otomatik kilidi yok** | Tek kullanıcılı yerel program; kilit = kapatma ya da "Şimdi kilitle" |
| K4 | **FE'de global 423 yakalayıcı yok** (`lib/api.ts`) | Kilit yalnız açılışta ve "Şimdi kilitle" ile ekrana yansır; süreç ömrü boyunca anahtar bellekte olduğundan pratikte 423 ancak başka bir pencereden kilitlenirse görülür |
| K5 | **Gerekçeler saklanmıyor** (aşama geri alma, erken kapatma) | Tasarım AuditLog'u bilinçli kaldırdı ("tek kullanıcı; evrak kütüğü yeter"). UI artık saklandığı yönünde vaat VERMİYOR; kalıcı iz isteyen kullanıcı evrak kütüğüne manuel kayıt ekler |
| K6 | **12. sınıflar `LEFT` ("Ayrıldı") olarak işaretlenir**, `GRADUATED` durumu yok | Şemada mezuniyet durumu yok; `LEFT` doğru davranışı veriyor (kayıt silinmez, `only_active` seçicilerde önerilmez). İleride küçük bir migration ile netleşebilir |
| K7 | **`backend/` pakete kaynak ağaç olarak girer** (donmuş arşive değil) | `desktop/paths.py::resolve_backend_dir()` gerçek `settings.py` dosyası arıyor. Bedeli: backend'in üçüncü taraf import'ları spec'te elle `hiddenimports` sayılmalı — yeni bağımlılık eklenirse spec de güncellenmeli |
| K8 | **npm üretim denetiminde React Router için 2 orta seviye bildirim** | Düzeltme React Router 7'ye kırıcı yükseltme gerektiriyor. Uygulama SSR kullanmaz, yalnız sabit yerel rotalarda ve `127.0.0.1` içinde çalışır; yükseltme ayrı uyumluluk çalışması olarak yapılacak |

## Kapanmış

| Kalem | Kapanış |
|---|---|
| SPA hiç servis edilmiyordu (`GET /` → 404; paket açılmazdı) | KAPANDI 24.07.2026 · `5d4c175` |
| Erişim logu PII sızdırıyordu (`?search=<öğrenci adı>`) | KAPANDI 24.07.2026 · `bbbca99` (ayrıca `django.setup()` susturmayı siliyordu) |
| 18 form varsayılan tarihi UTC'den türüyordu (TR'de gece bir gün geriye) | KAPANDI 24.07.2026 · `c16ee0f` + kaynak tarama kapısı |
| Tailwind `rounded-shape-full` ve `/8`–`/12` opaklıkları sessizce üretilmiyordu | KAPANDI 24.07.2026 · `c16ee0f` + derlenmiş CSS guard testi |
| **Windows paketleme yolu doğrulanmamıştı** (eski D1) | KAPANDI 24.07.2026 — CI'da uçtan uca yeşil: setup.exe + portable.zip üretiliyor, Türkçe PDF duman testi gömülü DejaVu ile geçiyor, `--autotest` çıkış 0 |
| **CI hiç koşmamıştı** (eski D2) | KAPANDI 24.07.2026 — depo açıldı, 6 koşuda 3 gerçek kusur bulundu ve kapatıldı (BOM, MSYS2 python gölgelemesi, fontconfig) |
| pywebview dosya indirmelerini varsayılan ayarla sessizce engelliyordu | KAPANDI 26.07.2026 — `ALLOW_DOWNLOADS` pencere oluşturulmadan açıldı; masaüstü koruma testi eklendi |
| Blob URL'si WebView isteği devralmadan aynı çağrı yığınında bırakılıyordu | KAPANDI 26.07.2026 — URL temizliği geciktirildi ve sahte zamanlayıcılı frontend testi eklendi |
