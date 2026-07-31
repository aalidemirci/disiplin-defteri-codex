# Disiplin Defteri — Genel Tasarım

> Bu proje OYS'den (ayrı bir okul yönetim sistemi) kod kopyalanarak türetilmiştir;
> OYS'ye çalışma-zamanı bağımlılığı yoktur.

## 1. Bağlam ve Amaç

OYS (Okul Yönetim Sistemi) içindeki disiplin modülü, Ortaöğretim Kurumları Yönetmeliği
md. 157-206'yı eksiksiz koda döken olgun bir alt sistem: durum makinesi, iş-günü tabanlı
yasal süre motoru, 16 üretilebilir belge + dizi pusulası + karar defteri + 3 onur/ödül
PDF'i, kurul/karar/itiraz/tedbir/müdür-uyarısı modelleri.

**Amaç:** Bu modülü baz alarak, OYS'den bağımsız, **tek kullanıcılı, girişsiz/şifresiz**
bir masaüstü program üretmek. Öğrenci listesi e-Okul/Excel'den, öğretmen bilgileri
Excel'den veya yapıştırarak gelecek; roller (Müdür, Disiplin Kurulu Başkanı vb.) personel
yüklendikten sonra tanımlanacak. Program **ders yılı bazlı** disiplin kayıtlarını (müdür
uyarıları dahil) tutacak; bütün **evrak üretimi ve tarih/süre işleri** buradan yürüyecek.
Windows + Pardus hedefi.

Kod ve mevzuat korpusu OYS'den **kopyalanarak** temel alınmıştır (bkz. `docs/mevzuat/`);
bu depo kendi başına derlenir, çalışır ve test edilir.

## 2. Kesinleşen Kararlar (kullanıcıyla teyitli)

| # | Karar | Seçim |
|---|---|---|
| 1 | Dağıtım kapsamı | **Genel araç** — her lise kullanabilsin; ilk açılışta kurulum sihirbazı (okul adı, il/ilçe, müdür adı → antet; ders yılı; tatil takvimi) |
| 2 | Veri koruma | **Opsiyonel açılış parolası** — varsayılan şifresiz; ayarlardan parola konursa DB o parolayla şifrelenir (fizibilite §6'da) |
| 3 | Mimari | **Yerel Django + SQLite + DRF (authsuz, yalnız 127.0.0.1) + React M3 UI (OYS'den uyarlama) + pywebview penceresi; WeasyPrint aynen** |
| 4 | Evrak kapsamı | 16 disiplin belge türü + dizi pusulası + karar defteri + müdür uyarısı (Form-01/02) + **3 onur/ödül PDF'i** |
| 5 | Rehberlik aşaması | **Korunur** (md. 192) — sinyalsiz, elle tarih + dönüş özeti girilir |

Gerekçe (mimari): evrak şablonları `@page` + `@bottom-center` (sayfa numarası) kullanıyor;
bu CSS margin-box'ını Chromium yazdırma desteklemez, WeasyPrint destekler → şablonları
birebir korumak Python'u zorunlu kılar. İş kuralları (durum makinesi + süre motoru) zaten
saf Python; React disiplin ekranları zaten yazılmış → iki katman da maksimum yeniden kullanım.

## 3. Keşif Bulguları (doğrulanmış)

### 3.1 Aynen taşınabilir saf katmanlar
- `backend/apps/ogrenci_isleri/state_machine.py` — durum makinesi (PETITION→{GUIDANCE_REFERRED,DECIDED}; …→CLOSED; rehberlik atlama yalnız gerekçeli override)
- `backend/apps/ogrenci_isleri/discipline_periods.py` — TÜM yasal süreler iş günü + `is_working_day` predicate enjeksiyonu (itiraz tebliğ+5, sevk+5, kurul 10+1 uzatma, tedbir ≤10/2 uzatma/başlama+3, uzaklaştırma 1-5 gün, kapanış tamponu+5; puan indirimleri 10/20/40/80)
- `backend/shared/working_days.py` — iş günü aritmetiği
- Parser'lar (DB'siz, saf): e-Okul "Veli İletişim Bilgileri" xlsx (`excel_veli`), personel xlsx (`excel_personel`), `normalize` (TCKN checksum, telefon, sınıf/şube, ad-soyad; fuzzy başlık tespiti `COLUMN_SYNONYMS`)

### 3.2 Evrak motoru
- `documents.py` (1163 satır) + `honor_documents.py` + 24 HTML şablon + ortak `backend/templates/documents/base.html` + `templates/print/_design.css`
- Kritik desenler: `@page` A4 + `@bottom-center` sayfa no; DejaVu Sans; `text-transform:uppercase` YASAK (Türkçe i→I sorunu); Dal A/B kısıtı (kurula sevksiz dosyada yalnız uyarı+tedbir+dizi pusulası); antet birimi dala göre; evrak İÇERİĞİ saklanmaz — yalnız `GeneratedDocument` kütüğü (canonical_order ×10); ifade/savunma gövdeleri "no-trace"
- Tebliğ kâğıt esaslı (tebellüğ imza satırı basılı); Form-16/17 yalnız kesinleşmiş kararda

### 3.3 İş kuralları (testlerle sabitlenmiş)
- Müdür kararı TEK seçim: yazılı uyarı / onur kuruluna sevk / disiplin kuruluna sevk; yalnız uyarı → dosya otomatik CLOSED
- Müdür uyarısı (md. 157/7) CEZA DEĞİL, puan düşürmez; tekrar → triaj kurula yönlendirir (md. 166)
- Dosya başına öğrenciye TEK canlı karar; puan + onay/itiraz mercii cezadan OTOMATİK; yalnız PENDING+tebliğsiz+itirazsız karar düzenlenebilir
- Müdür kurul kararını REDDEDEMEZ (md. 197): onaylar / gerekçeyle iade / (iade sonrası) ilçeye sevk
- İtiraz: tebliğsiz itiraz olmaz; süre dışı da kaydedilir (işaretli); OVERTURNED → REJECTED + puan iadesi; okul değiştirmede süresinde itiraz → uygulama bekletilir
- Kapanış uygunluğu (`close_eligible`): md. 197 askısı/PENDING itiraz yok + tebliğ + itiraz süresi + 5 iş günü tampon
- case_no `{ders yılı adı}-NNNN`; aktif ders yılı yoksa dosya açılamaz; davranış puanı yıl aralığından
- Savunma için gün sınırı kodda YOK (yalnız evrak); ceza tebliğinde itiraz son günü BASILMAZ (yalnız "5 iş günü" metni)

### 3.4 Koparılacak bağlar (OYS → standalone ikameleri)
| OYS bağımlılığı | Standalone ikamesi |
|---|---|
| `core.User/Student/Parent/SchoolYear` FK'ları | Yerel `Personnel/Student(+veli alanları)/SchoolYear` tabloları |
| `BaseModel.created_by/deleted_by` (FK User) | FK'sız soft-delete taban model (tarih damgaları kalır) |
| `core.services.is_working_day` (CalendarEvent) | Yerel tatil takvimi tablosu + gömülü TR resmî tatil verisi |
| `get_letterhead_identity` (SchoolConfig) | Kurulum sihirbazından gelen yerel kurum ayarları |
| `apps.denetim` (AuditLog/AccessLog) | Kaldırılır (tek kullanıcı); evrak kütüğü yeter |
| `apps.bildirim` sinyalleri + rehberlik döngüsü | Kaldırılır; rehberlik aşaması elle kayıt |
| Celery `daily_discipline_deadline_check` | Açılışta + periyodik senkron "Yaklaşan süreler" paneli |
| `EncryptedTextField` + blind_index | Düz alan; koruma = opsiyonel tam-DB parolası (§2/2) |
| DRF permission sınıfları + limited-görünüm | Kaldırılır (herkes=tek kullanıcı tam yetkili) |
| PostgreSQL koşullu UniqueConstraint'ler | SQLite partial index desteği doğrulanacak (§4.2) |
| FE: AuthContext, roles.ts, JWT interceptor, AppShell | Authsuz api istemcisi; `deriveCapabilities` → hepsi açık; yeni yalın kabuk |

### 3.5 e-Okul import gerçekleri
- Kaynak: "Veli İletişim Bilgileri" xlsx — Sınıf, TCKN, Numa, Adı Soyadı, Veli Kim, Anne/Baba Adı+Tel; doğum tarihi/cinsiyet e-Okul ihracında YOK (opsiyonel sütun)
- Kritik alanlar: sınıf/şube + TCKN + ad-soyad; TCKN checksum doğrulanır; veli dedup (telefon+ad)
- Personel: xlsx (ad, e-posta, roller) — standalone'da e-posta gereksiz, sadeleşir
- Dry-run önizleme deseni (gerçek ingest + rollback, %100 parite) korunmaya değer

## 4. Mimari ve Çıkarım Planı

### 4.1 Hedef depo yerleşimi (özet)

```
disiplin-defteri/
├── backend/
│   ├── config/            # tek settings.py (SQLite/WAL, DRF authsuz, TZ Istanbul)
│   ├── apps/okul/         # core ikamesi: SchoolConfig, SchoolYear, Holiday,
│   │                      #   Personnel, Student(+veli alanları), ImportRun-lite,
│   │                      #   is_working_day, letterhead, imports, backup, purge
│   │                      #   + excel_veli/excel_personel/normalize (OYS kopyası, saf)
│   ├── apps/disiplin/     # ogrenci_isleri'nden çıkarılan disiplin çekirdeği:
│   │                      #   models/, state_machine.py (AYNEN), discipline_periods.py (AYNEN),
│   │                      #   documents.py (UYARLA), honor_documents.py, deadlines.py (YENİ),
│   │                      #   selectors/, services/, views/, templates/disiplin/documents/ (25 dosya)
│   ├── shared/            # FK'sız BaseModel (UYARLA), working_days.py (AYNEN), letterhead.py (AYNEN)
│   └── templates/documents/base.html + templates/print/_design.css  (AYNEN — DOKUNMA)
├── frontend/src/          # ui/ M3 kiti (AYNEN), lib/api.ts (authsuz), hooks/,
│   └── modules/           # disiplin/ (uyarlama) + kurulum/ + kisiler/ + ayarlar/ + panel/ (YENİ)
├── desktop/               # main.py (kilit→yedek→migrate→waitress thread→pywebview), server.py, lock.py
├── packaging/             # PyInstaller spec, windows/ (Inno + DLL kapanışı), linux/ (.deb)
└── docs/, scripts/
```

### 4.2 Veri modeli — anahtar kararlar

- **BaseModel:** `created_by/deleted_by` FK'ları atılır; `created_at/updated_at/deleted_at` +
  `objects/all_objects` + soft delete/restore davranışı aynen.
- **YENİ tablolar:** `SchoolConfig` (singleton; kurum + `setup_completed` + `app_password_hash`),
  `SchoolYear` (name/start/end/is_active; tek-aktif kuralı serviste), `Holiday`
  (yalnız resmî/idari tatil; **ara tatil GİRİLMEZ** — yasal süre hesabı bozulur, sihirbazda açık uyarı),
  `Personnel` (ad/soyad/unvan/branş; login alanları yok), `Student` (Enrollment+Parent+Link
  DÜZLEŞTİRMESİ: sınıf/şube/no satırda; `guardian_name/kinship/phone/phone2/address` satır içi —
  Form-15/17 veli tebliğleri buradan), `ImportRun`-lite (sha256 + koşullu unique).
- **Şablon sadakati kritiği:** `documents.py::_student_context` anahtarları (`full_name, tckn,
  birth_date, class_label, student_number`) yerel property'lerle DEĞİŞMEDEN üretilirse
  24 şablonun içeriğine hiç dokunulmaz.
- **Disiplin tabloları:** alan listeleri AYNEN; yalnız FK ikameleri —
  `petitioner_user→Personnel`, `petitioner_parent` KALKAR (VELI rolünde öğrenci FK + ad snapshot),
  `performed_by/issued_by/generated_by/uploaded_by` KALKAR (tek kullanıcı),
  `assigned_guidance FK→assigned_guidance_name Char` (sinyalsiz rehberlik),
  `chair/member_user→Personnel`, `member_parent` KALKAR (ad snapshot yeter).
  `DisciplineAttachment` TAŞINIR (dilekçe taraması pratik ihtiyaç; media veri dizininde).
  Onur tarafı **honors-lite**: `HonorBoard` + sadeleşmiş `HonorCertificate` (yalnız 3 PDF'in
  şablon gereksinimleri kadar alan).
- **SQLite koşullu UniqueConstraint: DESTEKLENİR** (SQLite 3.8+ partial index; Django kısıtı yalnız
  MySQL/Oracle). Projedeki 6+ canlı-unique aynen çalışır; F2'de IntegrityError regresyon testi yazılır.
  `select_for_update` SQLite'ta no-op — tek yazar olduğundan kabul, yorumla belgelenir.
- **JSONField (`principal_decisions`)** SQLite JSON1 ile sorunsuz.

### 4.3 Django yapılandırması

`contenttypes + auth (altyapı için, model FK'sız) + staticfiles + DRF + okul + disiplin`;
DRF: `AUTHENTICATION []`, `AllowAny`, limit/offset 25, `{code,message,fields}` hata sözleşmesi
(FE `lib/api.ts` bunu bekler). `ALLOWED_HOSTS=127.0.0.1`; WhiteNoise + SPA catch-all;
`platformdirs` ile veri dizini; WAL/foreign_keys/busy_timeout/synchronous=NORMAL
`init_command`'da; WeasyPrint TEMBEL import kalır (PDF bağımlılığı bozuksa uygulama yine açılır).

### 4.4 Çıkarım haritası (özet)

- **AYNEN:** state_machine, discipline_periods, working_days, letterhead, base.html + _design.css,
  25 şablon (yalnız dizin adı `ogrenci_isleri→disiplin`), excel_veli/excel_personel/normalize,
  FE `ui/` kiti + format/download/pagination + useAutosave/useFormErrors + decisionTemplates/SelectOrOther.
- **UYARLA (doğrulanmış noktalar):** `documents.py` 7 dokunuş — s.31 import, s.343-352 `_student_context`,
  s.365-379 `_common_context` (letterhead ikamesi), s.382-397 `_parent_context` (guardian alanlarından),
  s.492-499 `_suspension_dates` (yerel is_working_day), s.727/1043/1105 get_student ikameleri,
  s.898-1038 `generate_document` (user/ip parametreleri kalkar; **Dal A/B kısıtı + Form-16/17
  kesinleşme kilidi AYNEN KORUNUR**). Selectors: rol/görünürlük fonksiyonları silinir
  (`has_full_discipline_access, case_visibility, cases_for_user…` → yalın `all_cases()`).
  Services: `_audit_write` ve bildirim emit'leri SİLİNİR; `generate_case_no` aynen.
  Views: permission sınıfları + `log_access` satırları silinir; CRUD/akış aynen.
  FE: `api.ts` JWT katmanı kalkar; `workflow.ts::deriveCapabilities` → hepsi-true sabit
  (dal/adım mantığı `caseBranch/caseSteps/nextStepFor` AYNEN); DisiplinDetayPage (2250 satır)
  capability/`useAuth` ayıklaması — TS derleyicisi yönlendirir.
- **ALMA:** Celery/tasks, signals, permissions, devamsızlık/mektup/rapor dosyaları, denetim,
  bildirim, core'un kalanı, blind_index/EncryptedField (bkz. §6), FE AuthContext/roles/tokens/pkce/
  sentry/AppShell/diğer modüller.

### 4.5 "Yaklaşan Süreler" paneli (Celery ikamesi)

Üç tarama zaten selector'larda (`appeals_awaiting_forward`, `cases_awaiting_committee_decision`,
`precautions_awaiting_deadline`) — YENİ `deadlines.py::collect_deadline_items(today)` bunlara
iki bölüm ekler: tebliğ bekleyen kararlar + kapanışa hazır dosyalar (`close_eligible`).
Öğe: `{severity: GEÇTİ/YAKLAŞIYOR/BİLGİ, case_no, başlık, son_gün, madde_atfı, link}`.
`GET /api/v1/disiplin/yaklasan-sureler/` senkron (yerel ölçek küçük); panel ana sayfada,
30 dk `refetchInterval` + kabukta rozet.

### 4.6 Yıl devri + md. 157/7 imha

- **Yıl devri sihirbazı:** yeni SchoolYear → is_active taşınır (case_no yeni prefix; eski numaralar
  regex-izole) → yeni yıl tatilleri → yeni kurul tanımı (yıl başına tek kurul) → öğrenci güncelleme
  (önerilen yol: yeni e-Okul listesini yeniden import — upsert; alternatif toplu `class_level+1`) →
  kapanmamış eski-yıl dosyaları UYARILIR (engellenmez — süreç yıl aşabilir).
- **İmha aracı (md. 157/7):** yalnız uyarı belgeleri — `DisciplineWarning` + bağlı `WARNING_LETTER`
  kütük satırları + yalnız-uyarıyla kapanmış Dal A dosyaları listelenir → **imha tutanağı PDF'i**
  (kalıcı tek iz) → iki aşamalı onay → `hard_delete()` (soft-delete'in bilinçli istisnası; sıra:
  önce belgeler/olaylar, sonra dosya; öğrenci PROTECT — silinmez). Dal B (kurul kararlı) dosyalar
  aracın DIŞINDA, UI zorlar. Nakil senaryosu: öğrenci detayından tekil imha (+5 iş günü göstergesi).

### 4.7 Import akışları

Parser'lar `rows` matrisi alır → **xlsx ve pano yapıştırma aynı boru hattı**. Her kaynak iki adımlı:
`preview` (dry-run: kolon eşleşmesi, satır hataları, N yeni/M güncel/K atlanan) → `commit`.
(1) e-Okul veli xlsx aynen; hedef düzleşir (student_number→tckn upsert; veli → guardian alanları).
(2) Genel Excel şablonu: `sablon-ogrenci.xlsx` indirilebilir; sinonimler zaten tanır — ayrı kod yolu YOK.
(3) Personel xlsx aynen → Personnel upsert. (4) Yapıştırma: textarea → tab-split matris → aynı preview;
başlıksız yapıştırmada kolon-eşleme dropdown'ları. (5) Idempotency: dosya/matris sha256 —
`already_imported` UYARI olarak (engel değil; güncelleme meşru). (6) Elle ekleme formları.

### 4.8 Test stratejisi

- **Aynen:** state_machine, periods (tüm yasal süre matematiği), normalize/parser testleri;
  FE workflow/decisionTemplates/SelectOrOther/ui testleri.
- **Uyarlanarak:** factories (User/Parent→Personnel/guardian), models (koşullu unique'ler İLK KEZ
  SQLite'ta — kendi başına değerli regresyon), services/decisions (close_eligible, puan iadesi),
  committee, participants (ACCUSED senkron), precautions, documents + PDF smoke (Dal A/B kısıtı,
  Form-16/17 kilidi, dizi pusulası), council, deadline task→`collect_deadline_items`, import preview.
- **Yeni:** SQLite IntegrityError doğrulaması; yapıştırma→preview; imha aracı (Dal B reddi, tutanak,
  silme sırası); yıl devri (prefix + tek aktif); sihirbaz `setup_completed` kapısı.
- **Kapı:** `--cov-fail-under=75` korunur (saf modüller fiilen ~%100); vitest yeşil.

### 4.9 Uygulama fazları

| Faz | İçerik | Çıktı | Durum |
|---|---|---|---|
| F0 — İskele | Depo + git; settings, FK'sız BaseModel, shared kopyaları, pytest/ruff/mypy, vite + ui kiti; tasarım dokümanı `docs/`'a | Boş proje yeşil; FE dev açılıyor | **TAMAMLANDI** |
| F1 — Okul çekirdeği | okul modelleri + is_working_day + letterhead + parser kopyaları + import preview/commit + sihirbaz API | Kurulan, liste yüklenebilen backend | **TAMAMLANDI** |
| F2 — Disiplin backend (EN BÜYÜK) | models FK-ikameli + 0001_initial + saf katman + selectors/services temizliği + views authsuz + deadlines.py | Tüm disiplin API'si uçtan uca; SQLite constraint testleri yeşil | **TAMAMLANDI** |
| F3 — Evrak motoru | documents.py 7-nokta uyarlaması + 25 şablon + honors-lite + karar defteri + dizi pusulası | Tüm PDF'ler OYS çıktısıyla karşılaştırmalı doğrulanmış | **TAMAMLANDI** — parite koşusu: EK-1 + Form-14/15/16 + dizi pusulası pypdf metni OYS ile 5/5 BİREBİR (24.07.2026, sabit saat + aynı fixture) |
| F4 — Frontend | api.ts sadeleştirme + disiplin ekran uyarlaması + kurulum/kisiler/ayarlar/panel + süre paneli | Tarayıcıda tam işlevli uygulama | **TAMAMLANDI** — 5 dilim: mantık katmanı → disiplin sayfaları + kurul → odul (honors-lite) → yeni ekranlar → faz denetimi. `deriveCapabilities` yerine `ALL_CAPABILITIES` sabiti; kurulum kapısı (`setup_completed` false → sihirbaz). Denetim: 8 boyut × bulgu başına 2 hakem, 39 bulgu → 23 doğrulandı ve kapatıldı (kurul üye ekleme yanıtında bayat prefetch, EK-1 doğum tarihi kaybı, katılımcı sonrası öğrenci listesinin tazelenmemesi, onur teklif PDF'inde tek imza adı, pasif karar tipinin tek yönlü kapan olması). 374 BE + 325 FE test |
| F5 — Masaüstü + paket | pywebview launcher, yedek/geri yükleme, parola, imha aracı, yıl devri UI, PyInstaller/Inno/.deb + CI | Kurulabilir paketler + docs | **TAMAMLANDI** — desktop/ başlatıcı (115 test), imha aracı, yıl devri, opsiyonel parola (zarf şifreleme + kurtarma anahtarı), SPA servisi. **CI'da uçtan uca yeşil (24.07.2026):** Linux `.deb` temiz `debian:11`+`debian:12`'ye kuruluyor, Windows `setup.exe` + `portable.zip` üretiliyor, her iki platformda Türkçe PDF duman testi gömülü DejaVu ile geçiyor, `--autotest` çıkış 0. İlk CI koşuları 3 gerçek kusur buldu: PS1 BOM'suzluğu, MSYS2 python'unun gölgelemesi, paket içi fontconfig. 483 BE + 117 desktop/paketleme + 360 FE test |

F5 başında **Windows WeasyPrint spike** (en riskli kalem önce doğrulanır).

## 5. Paketleme ve Dağıtım

Temel sürümler (kaynak: `backend/requirements.txt`, `backend/Dockerfile`):
Python 3.12 · Django 5.1.4 · DRF 3.15.2 · **WeasyPrint 63.1** (cairo'suz nesil —
`libgdk-pixbuf`/`libpangocairo` Dockerfile mirası, Windows paketine TAŞINMAZ) ·
cryptography 44 · React 18.3 + Vite 5.4. Sunucu bağımlılıkları (psycopg, redis,
celery, gunicorn, sentry, simplejwt, axes, cors, csp, structlog…) ayıklanır;
`python-magic` yerine saf-Python `filetype`.

### 5.1 Windows
- **PyInstaller onedir** (onefile DEĞİL: açılış süresi, AV false-positive, DLL ayıklanabilirliği).
  Spec: `collect_submodules('apps'/'django')` (migrations dinamik import tuzağı), templates + FE `dist/` + fontlar `datas`'ta.
- WeasyPrint dlopen bağımlılıkları (gobject/glib/pango/pangoft2/harfbuzz(-subset)/fontconfig)
  **MSYS2** `mingw-w64-x86_64-pango`'dan; DLL kapanışı elle liste DEĞİL, CI'da `ntldd -R` ile script üretimi.
  Bootstrap'te `WEASYPRINT_DLL_DIRECTORIES` (WeasyPrint ≥60 resmî destek).
- **fontconfig tuzağı:** gömülü `fonts.conf` + `FONTCONFIG_FILE` + yazılabilir cache
  (`%LOCALAPPDATA%\...\cache`); font olarak YALNIZ gömülü DejaVu Sans TTF'leri (4 kesim) — sistem fontuna güven yok.
- **pywebview → WebView2:** Win11'de hazır; Win10 okul imajında garanti yok → açılışta registry tespiti,
  yoksa Türkçe yönlendirme (MSHTML'e düşüş KODLA ENGELLİ — React 18 çalışmaz). Kurulum paketine
  Evergreen Standalone Installer gömülür; kilitli PC'ler için Fixed-Version'lı "full" zip varyantı ayrıca üretilir.
- **Installer:** Inno Setup `PrivilegesRequired=lowest` → `%LOCALAPPDATA%\Programs\` (admin'siz, VS Code deseni)
  + taşınabilir zip (ikisi de). İmzasız v1: SHA256SUMS + ekran görüntülü Türkçe kurulum dokümanı;
  USB/yerel ağ dağıtımında MotW oluşmaz (SmartScreen hiç görünmez) — talimata yazılır. İmzalama v2 (Azure Trusted Signing/SignPath).

### 5.2 Pardus/Linux
- Sistem-python'lu .deb **ELENDİ**: Pardus 21 = Python 3.9 (Django 5.1 ≥3.10 ister); Debian 12'de Django 3.2 var, 5 yok.
- **PyInstaller onedir → .deb sargısı**: build YALNIZ `python:3.12-bullseye` container'ında (glibc 2.31 = Pardus 21 tabanı)
  → tek paket iki Pardus'ta çalışır. Pango/glib/fontconfig Linux'ta bundle'lanMAZ — .deb `Depends`
  (`libpango-1.0-0, libpangoft2-1.0-0, libharfbuzz0b, libfontconfig1, libglib2.0-0, fonts-dejavu-core`; hepsi Debian 11+12 ana depoda).
- **Pencere:** `pywebview[qt]` + PyQt5 5.15 + PyQtWebEngine 5.15 (manylinux2014 → glibc 2.17; PyInstaller hook'ları olgun).
  WebKitGTK/PyGObject yolu ELENDİ (typelib paketleme + Pardus 21/23 ABI oynaklığı). Bedel ~200-250 MB; kabul.
- `/opt/disiplin-defteri/` + `/usr/bin` symlink + `.desktop` + hicolor ikonlar; `dpkg-deb --build`.
  Admin'siz senaryo için aynı onedir `.tar.gz` + `kur.sh`.

### 5.3 Çalışma zamanı düzeni
- **Veri dizini exe DIŞINDA:** Win `%LOCALAPPDATA%\DisiplinDefteri\{data,backups,logs,cache}` (§10.3; Roaming DEĞİL — profil senkronu
  açık SQLite'ı bozar); Linux XDG (`~/.local/share|state|.cache/disiplin-defteri`).
- **Açılış sırası:** tek-instance kilidi (`msvcrt.locking`/`fcntl.flock`) → günlük otomatik yedek
  (`sqlite3.Connection.backup()`, 14 gün rotasyon; migrate öncesi ayrıca `pre-migrate-<sürüm>` kopyası) →
  `migrate --no-input` (hata → pencere açılmaz, "son yedekten dön" diyaloğu) → `waitress` arka-plan thread'i
  (127.0.0.1, `bind(0)` ile boş port) → pywebview penceresi.
- **Yerel güvenlik sigortası:** authsuz olduğundan rastgele oturum belirteci URL'ye eklenir; middleware belirteçsiz istekleri reddeder
  (aynı makinedeki diğer işlem/kullanıcılara karşı).
- WAL + `synchronous=NORMAL`; açılışta hızlı `PRAGMA integrity_check`; sürüm karşılaştırması (eski exe yeni DB'yi AÇMAZ).

## 6. Opsiyonel Parola — Fizibilite Kararı

- **SQLCipher RET** (gerekçeli): pysqlcipher3 terk edilmiş; sqlcipher3-binary yalnız Linux wheel;
  Windows'ta SQLCipher+OpenSSL derleme hattı tek geliştiricide sürdürülemez; Django backend sarmaları bakımsız.
- Kapanışta-dosya-şifrele RET (crash'te düz kalır — yanıltıcı güvence).
- **SEÇİLEN: OYS'nin test edilmiş `shared/fields.py` Fernet alan şifrelemesi + UI kilidi birlikte.**
  Anahtar kullanıcı parolasından Argon2id ile türetilir (salt + doğrulama hash'i veri dizininde);
  hassas alanlar (TCKN, telefon, ifade/karar metinleri) şifreli, şema düz. İlk kurulumda tek seferlik
  **kurtarma anahtarı** yazdırılır (parola-bağımsız ikinci sarmal — parola unutma = veri kaybı olmasın).
  Ayarlarda dürüst metin: "tam disk şifreleme için BitLocker/LUKS."
  Parolasız modda alanlar düz durur; parola konunca alan içerikleri şifrelenir (tek yönlü geçiş aracı).

## 7. Tatil Takvimi Verisi

`holidays` pip paketi RET: TR dini bayramları hicri hesapla üretir, Diyanet ilanından ±1 gün
sapabilir — süre hesabı tatile bağlı resmî evrak programında kabul edilemez. OYS'nin
`seed_official_holidays` deseni taşınır: sabit resmî tatiller gömülü statik tablo + önümüzdeki
3-4 yılın Diyanet-teyitli dini bayramları ("teyitli/tahmini" bayrağıyla) + takvim ekranında
tamamı kullanıcı-düzenlenebilir (ara tatiller zaten elle).

## 8. CI (GitHub Actions)

- `frontend-build` (node 20) → `dist/` artefaktı; iki paket işi indirir.
- **Windows:** windows-latest + setup-python 3.12 (MSVC) + msys2 (pango, ntldd) → DLL kapanışı → PyInstaller →
  **duman testi: Türkçe metinli ("ĞÜŞİÖÇ ığüşiöç İstanbul") PDF üret + pypdf ile metni doğrula** → Inno → artefaktlar.
- **Linux:** ubuntu-latest üstünde `container: python:3.12-bullseye` → onedir → dpkg-deb →
  temiz `debian:11` VE `debian:12` container'larında kurulum+`--autotest` doğrulaması (iki Pardus provası).
- Artefaktlar: `-win64-setup.exe`, `-win64-portable.zip`, `-win64-full.zip` (Fixed WebView2), `_amd64.deb`,
  `-linux-x64.tar.gz`, `SHA256SUMS.txt`. Sürüm: `VERSION` dosyası (CalVer), `v*` tag → release.

## 9. Risk Kütüğü (özet)

| Risk | Azaltım |
|---|---|
| WeasyPrint Win DLL cehennemi (Y/Y) | ntldd otomatik kapanış; her build'de Türkçe PDF duman testi; `WEASYPRINT_DLL_DIRECTORIES` |
| WebView2 yokluğu (O/Y) | Registry tespiti; Evergreen gömülü; Fixed-Version full zip; MSHTML düşüşü engelli |
| Pardus 21 glibc (—/Y) | Build yalnız bullseye container; debian:11+12 kurulum testi CI kapısı |
| SQLite bozulması (D-O/ÇY) | WAL; günlük yedek + 14g rotasyon + migrate-öncesi kopya; integrity_check; USB yedek hatırlatması |
| Türkçe font/İ-i PDF (O/Y) | Gömülü DejaVu + fontconfig yalnız gömülü fonta; CI'da PDF metin çıkarma doğrulaması; `text-transform:uppercase` yasağı sürer |
| AV false-positive (O/O) | onedir; VirusTotal taraması + Defender istisna dokümanı |
| İmzasız exe SmartScreen (Y/O) | USB/yerel dağıtım (MotW yok); "Yine de çalıştır" dokümanı; v2 imzalama |
| QtWebEngine ambalajı (O/Y) | PyQt5 5.15 pin; xvfb pencere duman testi; çift-Debian kurulum testi |
| Roaming/OneDrive senkron bozması (D-O/Y) | Veri `%LOCALAPPDATA%` (senkron dışı); açılışta yol kontrolü + uyarı |

## 10. Tamamlayıcı Kararlar

1. **Linux paketi:** AppImage yolu ELENDİ — gerekçeli **PyInstaller onedir → .deb** yolu
   (bullseye/glibc 2.31 build) geçerli (§5.2).
2. **Opsiyonel parola (birleşik tasarım):** Kullanıcı seçimi "parola konursa DB o parolayla
   şifrelensin"di. SQLCipher RED edildi (§6). Birleşik çözüm:
   - Varsayılan (parolasız): hassas alanlar DÜZ; dürüst KVKK notu + BitLocker/LUKS önerisi
     (anahtar+DB aynı makinede — tam şifreleme yanılsaması yaratılmaz).
   - Parola konursa: **OYS'nin test edilmiş `EncryptedTextField`'ı** ile hassas alanlar
     (TCKN'ler, telefonlar, guardian bilgileri) Argon2id-türetilmiş Fernet anahtarıyla şifrelenir +
     UI kilidi + tek seferlik yazdırılabilir **kurtarma anahtarı**. Blind index ALINMAZ —
     yerel ölçekte (≤1000 kayıt) eşleştirme bellek-içi çözülür; import/arama sade kalır.
   - Parola sonradan konabilir/kaldırılabilir (alanları şifreleyen/çözen tek yönlü geçiş aracı).
   - UI metni dürüst: "Bu, kişisel veri alanlarını şifreler; tam disk şifreleme değildir."
3. **Veri dizini adı:** `DisiplinDefteri`.

## 11. Doğrulama (uçtan uca)

- Her faz: `pytest` (+ kapsam kapısı), `ruff check` + `ruff format --check`, `mypy --strict`,
  FE `tsc && vitest` — depoda kendi gates betiği (`scripts/gates.sh`, OYS gates.sh deseninden sadeleştirilmiş).
- F3 kabulü: aynı girdi verisiyle OYS'de ve standalone'da üretilen PDF'lerin metin içeriği
  (pypdf ile çıkarılıp) birebir karşılaştırılır; Türkçe karakter duman testi ("ĞÜŞİÖÇ ığüşiöç").
- F5 kabulü: temiz `debian:11` + `debian:12` container kurulum testi; Windows'ta temiz VM/PC'de
  setup.exe + portable zip; WebView2'siz senaryonun yönlendirme diyaloğu; e-Okul gerçek ihraç
  dosyasıyla (anonimleştirilmiş) import provası; örnek dosya yaşam döngüsü uçtan uca
  (dilekçe→rehberlik→kurul→EK-1→tebliğ→itiraz→kapanış) + dizi pusulası.
