# CLAUDE.md — Disiplin Defteri

> Bu dosya her oturumda otomatik yüklenir ve projeyi ilk kez gören bir
> ajan/denetçi içindir. Amacı: kodu doğru okumanı sağlamak ve **kasıtlı
> kararları kusur sanmanı engellemek**. Depodaki yorumlar ve `docs/` kütükleri
> gerekçe taşır — bir şey tuhaf görünüyorsa önce yakınındaki yorumu ve tasarım
> dokümanının ilgili bölümünü oku.
>
> Depo dili **Türkçe**: kod yorumları, commit mesajları, testler, dokümanlar,
> kullanıcıya görünen tüm metinler Türkçe. Tanımlayıcılar (sınıf/alan/uç adları)
> İngilizce — bu bilinçli: model ve API yüzeyi OYS'den kopyalandığı için birebir
> korundu. Aynı kalıbı sürdür.

---

## 1. Altın kurallar (önce bunlar)

1. **Kasıtlı olanı kusur sanma.** §6 "bulgu DEĞİL" listesini rapor yazmadan önce
   oku. Aynı şey `docs/teknik-borc.md` için de geçerli: orada yazan her kalem
   zaten biliniyor ve kabul edilmiş — tekrar raporlamak gürültüdür.
2. **Mevzuat kaynağı koddur, sezgin değil.** Yasal süreler, ceza puanları, itiraz
   mercileri ve kurul kompozisyonu Ortaöğretim Kurumları Yönetmeliği md. 157-206'ya
   bağlı. Doğrulama kaynağı: `docs/mevzuat/ortaogretim-yonetmeligi-disiplin-md157-206.md`
   (tam metin). "Bence şöyle olmalı" ile bulgu açma; maddeye atıf ver.
3. **`AYNEN` işaretli dosyalara dokunma.** `backend/templates/documents/base.html`,
   `backend/templates/print/_design.css`, 25 evrak şablonu, `state_machine.py`,
   `discipline_periods.py`, `shared/working_days.py`, `shared/letterhead.py` —
   bunlar OYS'den birebir taşındı ve F3'te PDF çıktısı OYS ile **5/5 birebir**
   doğrulandı. Buradaki bir "iyileştirme" sessizce resmî evrak paritesini bozar.
4. **Test/lint sadece Docker'da koşar.** Host'ta Python veya Node yok (§4).
5. **Tarih ve büyük harf iki gerçek tuzak.** §7'ye bak — bu projede en çok gerçek
   kusur bu iki sınıftan çıktı.
6. **Sürüm çıkışı siteye dokunur.** okulapp.org kartı güncellenmezse site eski
   paketi göstermeye devam eder — en sık yapılan hata budur (§5).

---

## 2. 60 saniyede proje

Türkiye'de bir ortaöğretim kurumunun **disiplin kurulu süreçlerini** uçtan uca
yürüten, **tek kullanıcılı, girişsiz, çevrimdışı bir masaüstü programı**.

Akış: dilekçe/ihbar → (rehberlik aşaması) → müdür kararı → gerekirse disiplin
kurulu → tebliğ → itiraz → kapanış. Her adımda gereken resmî evrak PDF olarak
üretilir (16 disiplin belge türü + dizi pusulası + karar defteri + müdür uyarısı
formları + 3 onur/ödül belgesi = 25 şablon). Yasal süreler **iş günü** tabanlı
otomatik izlenir. Kayıtlar ders yılı bazlıdır.

Yığın:

| Katman | Teknoloji |
|---|---|
| Backend | Django 5.1 + DRF 3.15, **SQLite** (WAL), Python 3.12 |
| Evrak | WeasyPrint 63.1 + HTML/CSS şablonlar (gömülü DejaVu Sans) |
| Frontend | React 18 + TypeScript + Vite 5 + Tailwind (Material Design 3 kiti) |
| Masaüstü | `pywebview` + `waitress` (127.0.0.1, rastgele boş port) |
| Paket | Windows: PyInstaller onedir + Inno Setup · Linux: PyInstaller onedir → `.deb` |

**Köken:** Proje, OYS (Okul Yönetim Sistemi) adlı ayrı ve olgun bir okul yönetim
sisteminin disiplin modülünden **kod kopyalanarak** türetildi. OYS'ye çalışma
zamanı bağımlılığı yok. Kodda sık geçen `OYS'den AYNEN` / `UYARLA` / `ALMA`
işaretleri bu çıkarımın haritasıdır (`docs/tasarim/…§4.4`). Bir kodun neden öyle
yazıldığını anlamıyorsan cevap çoğu kez "OYS'de öyleydi ve pariteyi koruyoruz".

**Durum:** F0-F5 fazlarının hepsi tamamlandı. CI'da Linux `.deb` (debian:11 ve
debian:12'ye temiz kurulum) ve Windows `setup.exe` + `portable.zip` uçtan uca
yeşil koştu. Sürüm: `VERSION` → `2026.7.0-beta.1` (CalVer).

---

## 3. Depo haritası

```
backend/
  config/           settings.py (TEK dosya), urls.py (+SPA catch-all), wsgi.py
  apps/okul/        "core" ikamesi: SchoolConfig, SchoolYear, Holiday, Personnel,
                    Student(+veli alanları düz), import boru hattı, kurulum sihirbazı,
                    is_working_day, yıl devri, opsiyonel parola servisi, lock_middleware
  apps/disiplin/    disiplin çekirdeği: models/, selectors/, services/, views.py,
                    state_machine.py, discipline_periods.py, deadlines.py,
                    documents.py (1165 satır), honor_documents.py, purge (md. 157/7),
                    templates/disiplin/documents/  ← 25 evrak şablonu
  shared/           FK'sız BaseModel, working_days, letterhead, crypto (Fernet+Argon2id),
                    exceptions ({code,message,fields} sözleşmesi), text
  templates/        documents/base.html + print/_design.css   ← DOKUNMA
frontend/src/
  ui/               M3 bileşen kiti (OYS'den AYNEN)
  lib/              api.ts (authsuz istemci), format.ts (todayIso!), download, pagination
  modules/          disiplin/ kurul/ odul/ kisiler/ kurulum/ ayarlar/ panel/
                    imha/ yildevri/ guvenlik/ okul/
desktop/            main.py (kilit→yedek→migrate→waitress thread→pencere), server.py,
                    lock.py, backup.py, integrity.py, session_guard.py, paths.py, dialogs.py
packaging/          pyinstaller/ (ortak spec + rthook + fonts.conf), windows/ (build.ps1,
                    dll_kapanisi.py, .iss, NOTLAR.md), linux/ (build.sh, .deb, kurulum provası),
                    fontlar/ (DejaVu 4 kesim), ikonlar/
website/            okulapp.org'a yönlendiren stub sayfalar (eski GitHub Pages
                    bağlantıları kırılmasın diye — tek kaynak okulapp.org, §5)
docs/               tasarim/ (331 satır genel tasarım), mevzuat/, kurulum.md, teknik-borc.md
scripts/gates.sh    tek komutluk kapı koşusu
.github/workflows/  paketleme.yml + pages.yml (yönlendirme stub'larını yayımlar)
```

**Açılış sırası (kritik, `desktop/main.py`):** tek-instance kilidi → günlük
otomatik yedek (14 gün rotasyon + migrate öncesi ayrı kopya) → `migrate --no-input`
→ `PRAGMA integrity_check` → `waitress` arka plan thread'i → `pywebview` penceresi.
Her adımın hata yolu ayrı çıkış koduna bağlı (`docs/kurulum.md §7`).

Ölçek duygusu (F5 sonu itibarıyla, kaba): backend ~22.500 satır Python + 470 test ·
desktop/packaging ~4.700 satır + ~111 test · frontend ~26.900 satır TS/TSX + 360 test.

---

## 4. Nasıl koşulur

Host'a Python/Node **kurulmaz**; her şey Docker konteynerinde çalışır.

```bash
docker compose build backend
docker compose run --rm backend python manage.py migrate
docker compose run --rm frontend npm install     # ilk kurulumda
bash scripts/gates.sh                            # TAM kapı — bunu koş
```

`scripts/gates.sh` sırayla: backend `pytest` (kapsam kapısı `--cov-fail-under=75`)
→ `ruff check` → `ruff format --check` → `mypy` (strict) → **ayrı** bir koşuda
`desktop/` + `packaging/` testleri (günlük yapılandırmasını değiştirdikleri için
backend testleriyle aynı süreçte koşamazlar — birleştirme) → desktop/packaging
ruff+mypy → frontend `tsc` → `eslint` → `prettier --check` → `vitest`.

Tek tek koşmak istersen:

```bash
docker compose run --rm backend pytest apps/disiplin/tests/test_documents.py -q
docker compose run --rm frontend npx vitest run src/modules/disiplin
```

**Ortam tuzakları:**
- `docker compose` kök olarak yazdığı için `backend/data/`, `*_cache/`,
  `frontend/node_modules/`, `frontend/dist/` **root sahipli**. `backend/data/media/imha`
  normal kullanıcıya kapalı — `find`/`grep` orada "Permission denied" uyarısı verir,
  bu bir kusur değil, yok sayabilirsin.
- `docker-compose.yml` hiçbir port açmaz (program ağ servisi sunmaz); komutlar
  `run --rm` ile koşulur.
- `DD_DEBUG=1` yalnız geliştirme konteynerinde açık; varsayılan `False` (KVKK —
  DEBUG sayfası yerel değişkenlerdeki ham TCKN'yi döker).

---

## 5. okulapp.org yayını (ortak yayın alanı)

Bu projenin sitedeki alanı, yan klon `../okulapp.org` içinde
`src/data/dd-release.json` (indirme kartı) ile `/disiplin-defteri/**`
sayfalarıdır. Tanıtım/kılavuz sayfalarının TEK kaynağı sitedir (GitHub
Pages'ten taşındı; MEB ağında GitHub engelli olduğu için). Yeni sürüm
çıktığında `dd-release.json` ve sitedeki proje kartının `badge` alanı
güncellenmezse site eski paketi göstermeye devam eder — en sık yapılan
hata budur.

Siteye dokunmadan önce `../okulapp.org/CLAUDE.md` → **"Ortak çalışma
düzeni"** okunur ve uygulanır. Özet: sitede yalnız kendi alanına yaz ·
işe `git fetch` + güncel `origin/main` ile başla, eski tabandan açılmış
dal güncellenmeden merge edilmez · production yalnız `main` push'uyla
değişir (Cloudflare "Version command" = `npx wrangler versions upload`;
`deploy` yapılmaz).

---

## 6. Bunlar bulgu DEĞİL — kasıtlı kararlar

Aşağıdakiler bir web uygulamasında ciddi bulgu olurdu; **bu program tek
kullanıcılı, girişsiz, ağa hiç açılmayan yerel bir masaüstü uygulamasıdır** ve
her biri gerekçesiyle kayıt altındadır.

| Görünen "sorun" | Gerçek | Kaynak |
|---|---|---|
| DRF `AUTHENTICATION_CLASSES = []`, `AllowAny`, hiçbir permission sınıfı yok | Ürün kararı: girişsiz program. Kullanıcı = işletim sistemi oturumu. | tasarım §2/3, §4.3 |
| `SECRET_KEY` kaynak koda gömülü sabit | Kriptografik oturum yok; ağdan erişilmez. `DD_SECRET_KEY` ile ezilebilir. | `settings.py` yorumu |
| `ALLOWED_HOSTS` sadece 127.0.0.1 / CORS-CSP-HSTS yok | Yalnız yerel loopback dinlenir. | §4.3 |
| Rastgele `DD_SESSION_TOKEN` ile URL'de belirteç | Aynı makinedeki **başka bir işlemin** loopback'e istek atmasına karşı sigorta. Ağ güvenliği iddiası değil. | `desktop/session_guard.py`, §5.3 |
| `select_for_update` etkisiz | SQLite'ta no-op; tek yazar var, bilinçli kabul, yorumla belgeli. | §4.2 |
| `AuditLog`/`AccessLog` yok | Tek kullanıcı; kalıcı iz = evrak kütüğü. AuditLog bilinçli kaldırıldı. | §3.4, borç K5 |
| Aşama geri alma / erken kapatma **gerekçesi saklanmıyor** | Yukarıdakinin sonucu. UI artık saklandığı vaadini vermiyor. | borç K5 |
| İmha aracında `hard_delete()` | Soft-delete'in **bilinçli istisnası** — md. 157/7 uyarı belgelerinin imhası. Kalıcı iz olarak imha tutanağı PDF'i üretilir; öğrenci PROTECT. | §4.6 |
| Evrak PDF'lerinin **içeriği saklanmıyor** | Yalnız `GeneratedDocument` kütüğü tutulur (canonical_order ×10). İfade/savunma gövdeleri "no-trace". | §3.2 |
| Dosya ekleri (`MEDIA_ROOT`) şifrelenmiyor | Yalnız alan şifrelemesi seçildi; UI bunu açıkça söylüyor. Tam koruma = BitLocker/LUKS. | borç K2 |
| Şifreli kipte `uq_student_tckn_alive` etkisiz | Fernet deterministik değil; blind index bilinçli alınmadı (≤1000 kayıt). Tekillik serviste: `selectors.find_student_by_tckn`. | borç K1, §10.2 |
| Şifreleme anahtarı süreç ömrü boyunca bellekte | Bağlanacak oturum kimliği yok; her istekte Argon2id ~0,2 sn maliyet olurdu. Kilitleme = kapatma veya açık "Kilitle". | `shared/crypto.py` başlığı |
| Boşta-kalma otomatik kilidi yok | Aynı gerekçe. | borç K3 |
| 12. sınıflar mezun olduğunda `LEFT` ("Ayrıldı") | Şemada `GRADUATED` yok; `LEFT` doğru davranışı veriyor. | borç K6 |
| `backend/` pakete kaynak ağaç olarak giriyor | `desktop/paths.py::resolve_backend_dir()` gerçek `settings.py` arıyor. Bedeli: yeni bağımlılık eklenirse PyInstaller spec'inde `hiddenimports` güncellenmeli. | borç K7 |
| Celery/Redis/Postgres/Sentry/JWT yok | Sunucu bağımlılıkları bilinçli ayıklandı; süre taraması senkron panele dönüştü. | §3.4, §4.5 |
| `frontend` tarafında global 423 yakalayıcı yok | Kilit yalnız açılışta ve "Şimdi kilitle" ile görünür. | borç K4 |

**Kural:** Bu tabloya veya `docs/teknik-borc.md`'ye giren bir konuyu ancak
*gerekçenin kendisinin yanlış olduğunu* gösterebiliyorsan raporla — o zaman da
gerekçeye karşı argüman kur, "auth yok" demekle yetinme.

---

## 7. Gerçek kusurun yaşadığı yerler

Bu projede F2/F4/F5 denetimlerinde bulunan **doğrulanmış** kusurların hemen hepsi
şu sınıflardan çıktı. Aramaya buradan başla.

### 7.1 Tarih disiplini (en verimli sınıf)
`TIME_ZONE = "Europe/Istanbul"`, `USE_TZ = True`. UTC'den tarih türetmek Türkiye'de
gece 00:00-02:59 arasında **bir gün geriye** kayar ve resmî belgeye yanlış tarih
basar. Daha önce 18 formda aynı anda yakalandı.
- Frontend: `new Date().toISOString().slice(0,10)` **yasak**, doğru yol
  `lib/format.ts::todayIso()`. Bunu `frontend/src/lib/format.test.ts` içindeki
  "tarih disiplini" **kaynak tarama testi** koruyor.
- Backend: `timezone.now().date()` yerine yerel tarih; süre hesaplarına giren her
  tarih `discipline_periods` üzerinden geçmeli.

### 7.2 Türkçe büyük/küçük harf
`text-transform: uppercase` **evrak şablonlarında yasak** — WeasyPrint locale'siz
çevirir, "i" → "I" olur (doğrusu "İ"). Başlıklar doğrudan büyük harfle yazılır.
Python'da çıplak `.upper()`/`.lower()` Türkçe metne uygulanıyorsa şüphelen: doğru
yol `apps/okul/normalize.py` içindeki `_TR_UPPER_MAP` çevirisidir (`ı/İ → I`),
ki o da **eşleştirme/karşılaştırma** içindir — kullanıcıya veya evraka basılacak
metne uygulanmaz.

### 7.3 İş günü vs takvim günü
Yasal sürelerin **hepsi iş günü** (`shared/working_days.py` + `is_working_day`
predicate enjeksiyonu). `timedelta(days=N)` ile süre hesabı gören her yer kusur
adayıdır. Ayrıca: **ara tatiller `Holiday` tablosuna girilmez** — girilirse yasal
süre hesabı bozulur (sihirbazda açık uyarı var).

### 7.4 Evrak/şablon paritesi
`documents.py::_student_context` anahtarları (`full_name, tckn, birth_date,
class_label, student_number`) **değişmeden** üretilmeli; değişirse 25 şablon
sessizce boş alan basar. Korunması gereken kilitler: **Dal A/B kısıtı** (kurula
sevksiz dosyada yalnız uyarı + tedbir + dizi pusulası üretilebilir) ve
**Form-16/17 yalnız kesinleşmiş kararda**.

### 7.5 Bayat önbellek / tazelenmeyen liste
F4 denetiminde birden çok kez çıktı: mutasyondan sonra `prefetch`'in bayat kalması
(kurul üye ekleme yanıtı), React Query invalidasyonunun eksik olması (katılımcı
ekledikten sonra öğrenci listesi). Mutasyon → invalidasyon eşleşmesini kontrol et.

### 7.6 Tek yönlü kapanlar
"Pasif karar tipi seçilince geri dönülemiyor" sınıfı hatalar. Bir durum değişimi
kullanıcıyı geri dönüşü olmayan bir yere sokuyorsa bulgudur.

### 7.7 Tailwind M3 token'ları
Kaynakta kullanılan ama Tailwind çıktısında **üretilmeyen** sınıflar sessizce
görsel bozulma yapar (`rounded-shape-full`, `/8`-`/12` opaklıkları vaktiyle
üretilmiyordu). `frontend/src/App.test.tsx` içindeki "M3 token bütünlüğü" testi
bunu derlenmiş CSS'e karşı doğruluyor — bu testi bozacak sınıf ekleme.

---

## 8. Bozulmaması gereken yasal invariantlar

Bunlar testlerle sabitlenmiş; birini bozan bir değişiklik **gerçek** kusurdur.

- **Müdür kararı tek seçimdir:** yazılı uyarı / onur kuruluna sevk / disiplin
  kuruluna sevk. Yalnız uyarı → dosya otomatik `CLOSED`.
- **Müdür uyarısı (md. 157/7) ceza değildir**, davranış puanı düşürmez; tekrarı
  triajı kurula yönlendirir (md. 166).
- Dosya başına öğrenciye **tek canlı karar**. Puan ve onay/itiraz mercii cezadan
  **otomatik** türer. Yalnız `PENDING` + tebliğsiz + itirazsız karar düzenlenebilir.
- **Müdür kurul kararını reddedemez** (md. 197): onaylar / gerekçeyle iade eder /
  (iade sonrası) ilçeye sevk eder.
- **İtiraz:** tebliğsiz itiraz olmaz; süre dışı itiraz da kaydedilir (işaretli).
  `OVERTURNED` → `REJECTED` + puan iadesi. Okul değiştirme cezasında süresinde
  itiraz → uygulama bekletilir.
- **Kapanış uygunluğu (`close_eligible`):** md. 197 askısı ve `PENDING` itiraz yok
  + tebliğ yapılmış + itiraz süresi dolmuş + 5 iş günü tampon.
- `case_no` biçimi `{ders yılı adı}-NNNN`; **aktif ders yılı yoksa dosya açılamaz**.
- Ceza tebliğinde **itiraz son günü basılmaz** (yalnız "5 iş günü" metni).
- **Yıl başına tek disiplin kurulu**, tek aktif `SchoolYear`.

Süre matrisi (iş günü): itiraz tebliğ+5, sevk+5, kurul 10 (+1 uzatma), tedbir ≤10
(+2 uzatma, başlama+3), uzaklaştırma 1-5 gün, kapanış tamponu +5. Puan indirimleri
10/20/40/80. Hepsi `discipline_periods.py`'de.

---

## 9. Açık borç (zaten biliniyor)

Tam liste `docs/teknik-borc.md`. Özeti — **bunları yeniden keşfetme**:

*Doğrulanamayanlar (kod yazıldı, ortam kısıtı nedeniyle koşulmadı):* Qt penceresi
hiç açılmadı (D3) · paketlenmiş ikili üzerinden gerçek evrak üretimi (D4) · `.deb`
yükseltme yolu (D5) · Windows başlatıcı yolları: ikinci kopya kilit çakışması,
WebView2 yokluğu (D6) · Argon2 cffi ikilisinin pakette toplanması (D7).

*Kabul edilmiş bedeller:* K1-K7 → §6 tablosunda karşılıkları var.

Windows tarafında ayrıca `packaging/windows/NOTLAR.md` W1-W9 doğrulanmamış
varsayım listesi tutuyor.

---

## 10. Gözden geçirmede öncelik önerisi

Etki × yoğunluk sırasıyla:

1. **`backend/apps/disiplin/services/` + `selectors/`** — iş kurallarının kalbi;
   §8 invariantlarına karşı oku.
2. **`backend/apps/disiplin/views.py` (1196 satır) + `serializers.py`** — doğrulama
   boşlukları, 500 dönmesi gereken yerde 400, kısmi güncellemenin veri silmesi.
3. **`frontend/src/modules/disiplin/DisiplinDetayPage.tsx` (2355 satır) +
   `DecisionsSection.tsx` (1840)** — en büyük iki dosya, en çok durum barındıran
   yerler; §7.5 ve §7.6 sınıfları burada yaşıyor.
4. **`documents.py` uyarlama noktaları** — Dal A/B kısıtı ve Form-16/17 kilidinin
   hâlâ yerinde olduğu; şablon bağlam anahtarlarının bozulmadığı.
5. **`shared/crypto.py` + `apps/okul/services/app_password.py`** — parola koyma/
   kaldırma geçişinin veri kaybetmediği, kurtarma anahtarı yolunun sağlam olduğu.
6. **`apps/disiplin/services/purge.py`** — imha aracının silme sırası, Dal B reddi,
   tutanak üretimi (geri dönüşsüz işlem).
7. **`desktop/main.py` açılış sırası** — hata yollarının pencere açmadan doğru
   çıkış kodu verdiği; yedek/migrate/integrity zincirinin sırası.
8. **`apps/okul/services/imports.py` + parser'lar** — TCKN checksum, veli dedup,
   dry-run/commit paritesi, idempotency (sha256).

---

## 11. Değişiklik yaparken

- **Test önce.** Her davranış değişikliği testle gelir; `--cov-fail-under=75`
  kapısı var (saf modüller fiilen ~%100).
- **`bash scripts/gates.sh` yeşil olmadan iş bitmiş sayılmaz.** mypy `strict`,
  ruff `E,F,I,UP,B,DJ,S,C4`, satır 100.
- **Commit mesajları Türkçe**, Conventional Commits biçiminde ve kapsam etiketli:
  `fix(disiplin): …`, `feat(okul): …`, `chore(ci): …`, `docs: …`. Git geçmişine bak,
  kalıbı sürdür.
- **Yeni Python bağımlılığı eklersen** `packaging/pyinstaller/disiplin_defteri.spec`
  içindeki `hiddenimports`'u da güncelle (borç K7) — yoksa paket açılmaz, testler
  bunu yakalamaz.
- **Migration:** `okul` 0002'de, `disiplin` 0001'de. Şema değişikliği şifreli alan
  geçişini etkileyebilir (`0002_encrypt_sensitive_fields`) — dikkat.
- **KVKK:** `.gitignore` `data/`, `media/`, `*.xlsx` girişlerini engelliyor. Gerçek
  öğrenci verisi, e-Okul ihracı veya TCKN içeren fixture **depoya girmez**.

---

## 12. Belge haritası

| Dosya | İçerik |
|---|---|
| `docs/tasarim/2026-07-23-genel-tasarim.md` | **Ana referans.** Kararlar + gerekçeler, veri modeli, çıkarım haritası (AYNEN/UYARLA/ALMA), paketleme, risk kütüğü, faz tablosu. Bir "neden böyle?" sorusunun cevabı %90 buradadır. |
| `docs/teknik-borc.md` | Bilinen eksikler: doğrulanamayanlar, kabul edilmiş bedeller, kapananlar. |
| `docs/mevzuat/ortaogretim-yonetmeligi-disiplin-md157-206.md` | Yasal doğrulama kaynağı (991 satır tam metin). |
| `docs/mevzuat/notlar/` | Ceza süreleri/itiraz, kurul kompozisyonu, onur kurulu üzerine Q&A notları. |
| `docs/kurulum.md` | Son kullanıcı kurulum + sorun giderme + çıkış kodları. |
| `packaging/README.md` | Paket üreten kişi için dosya haritası ve komutlar. |
| `packaging/windows/NOTLAR.md` | Windows'a özgü doğrulanmamış varsayımlar (W1-W9). |
| `README.md` | Genel tanıtım; güncel. |

---

## 13. Diğer ajanlar

Bu brifing eskiden `codex-bilgilendirme.md` adını taşıyordu; içerik buraya
taşındı. Claude dışındaki ajanlar (Codex vb.) için depo kökündeki `AGENTS.md`
bu dosyaya işaret eder — brifingi iki yerde tutma, yalnız burayı güncelle.
