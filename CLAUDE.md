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
   **Bilinçli istisnalar (kullanıcı kararı, 24-26.09.2026):** `precaution_notice`,
   `appeal_letter` (Form-18), `penalty_notice_parent` / `penalty_days_notice_parent`
   (Form-15/17), `deadline_extension_record` (Form-12), `deadline_extension_petition`
   (Form-13 OLUR bloğu) ve `ek1_committee_decision` (müdür onay kutusu) metinleri
   mevzuata göre değiştirildi; `return_letter`, `district_referral_letter`,
   `approval_request_letter`, `precaution_mem_*` (M2 Grup 1) ile `parent_*`,
   `search_record`, `non_compliance_record` (M2 Grup 2), `guidance_assessment` (Form-01)
   OYS'de yoktur, yeni eklendi — bunları OYS'ye "geri
   döndürme"; gerekçe `docs/teknik-borc.md` "Kapanmış" tablosunda.
   `council_meeting_minutes` (karar defteri) 04.10.2026'dan beri yalnız EKLEME ile
   "GÜNDEM MADDELERİ VE KARARLAR" bloğu basar (kurul işleyişi Aşama 1); gündemsiz
   toplantıda çıktı OYS ile aynıdır — bloğu kaldırma. İkinci bilinçli sapma (kullanıcı
   kararı, 14.11.2026): imza ızgarası 6 ve üzeri imzacıda 5'erli satırlara bölünür
   (kalabalık kurulda imza haneleri sayfa dışına taşıyordu); 5 ve altında çıktı OYS ile
   aynıdır — `_SIGNERS_PER_ROW` değerini düşürme.
   **Kullanıcı kararları 14.11.2026 (S1, S3, S4, S12) — OYS'ye "geri döndürme":**
   `warning_letter_parent` (Form-02 veli: ad sonrası tamlayan eki `tr_ekler` ile),
   `penalty_notice` (Form-14: cezasız kararda tebellüğ metni "ceza" demez; değişen cezada
   Form-15'teki `penalty_change_note` paragrafı), `honor_recommendation_record` (toplantılı
   yolda "Toplantı Tarihi / No" satırı) ve `defense_record` (Form-11 YALNIZ dolu mod: imza
   bloğu bölünmez, kutu en az 4 cm; boş mod ve "Yer" varsayılanı DEĞİŞMEDİ) değiştirildi.
   Karar defterinde (dosya görüşme tutanağı) kararlar KARAR NUMARASI sırasıyla dizilir ve
   uzaklaştırmada gün sayısı basılır (`documents._council_minutes_context`; dosyasız tutanak
   etkilenmez).
   **Kullanıcı kararı 14.11.2026 (S7 — vekâlet) — OYS'ye "geri döndürme":**
   `ek1_committee_decision` ve `_defense_record_committee_grid` (Form-11 / md. 195 ızgarası)
   başkan hanesi etiketini bağlamdan alır (`chair_role`; verilmezse eski sabit "Başkan
   (Müdür Yrd.)"); `council_meeting_minutes` başkanın katılmadığı toplantıda "(Başkan)"
   işaretini basmaz (`acting_chair`) ve katılanlar tablosunun altına `chair_absence_note`
   cümlesini ekler. Vekâletsiz çıktı üçünde de bayt bayt aynıdır (testli) — kaldırma.
   Aynı kararın devamı (14.11.2026): `meeting_call` (Form-10), `deadline_extension_record`
   (Form-12), `deadline_extension_petition` (Form-13), `statement_call` (Form-3),
   `statement_record` (Form-4/5/6), `info_gathering` (Form-7/8) ve `defense_call` (Form-9)
   başkan etiketini de bağlamdan alır (`chair_role`; verilmezse şablonun eski sabit metni).
   Form-12 giriş cümlesi `chair_presiding`, Form-13 gövdesi `chair_office` ile aynı yolu izler.
   Bu anahtarlar dosyanın SON toplantı kaydı vekâletliyse verilir — başkan dosyada şikâyetçi /
   zarar gören olsun ya da yalnız izinli olsun (kullanıcı kararı, 15.11.2026;
   `documents._case_committee`, `_committee_with_members_context`). Dizi pusulasının düzenleyen
   hanesi aynı kuralı izler (`_index_sheet_context`). Son toplantı kaydı vekâletli değilse yedi
   şablonun çıktısı bayt bayt aynıdır (testli) — kaldırma. Ceza tebliğleri ("Tebliğ Eden —
   Müdür Yardımcısı") kapsam DIŞIDIR, AYNEN: izinli başkanda asıl başkan basılır, şikâyetçi /
   zarar gören başkanda hane boş kalır (`_case_committee(acting=False)`).
   `discipline_periods.py::precaution_end_date`: tedbir başlangıcı iş günü
   değilse günler izleyen İLK İŞ GÜNÜNDEN sayılır (başlangıç iş günüyse sonuç OYS ile aynı);
   dosyanın geri kalanı AYNEN.
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
yeşil koştu. Sürüm: `VERSION` → `2026.11.0-beta.1` (CalVer; kasım 2026 yedekleme düzeltmesi + 14.11.2026 saha denemesi kararları S1-S13: vekâlet kaydı, toplantı zorunluluğu, şema göçleri 0014-0017).

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
                    documents.py (2470 satır), honor_documents.py, purge (md. 157/7),
                    templates/disiplin/documents/  ← 25 evrak şablonu
  shared/           FK'sız BaseModel, working_days, letterhead, crypto (Fernet+Argon2id),
                    exceptions ({code,message,fields} sözleşmesi), text
  templates/        documents/base.html + print/_design.css   ← DOKUNMA
frontend/src/
  ui/               M3 bileşen kiti (OYS'den AYNEN)
  lib/              api.ts (authsuz istemci), format.ts (todayIso!), download, pagination
  modules/          disiplin/ (dosyalar) kurul/ (Ödül ve Disiplin Kurulu + Onur Kurulu
                    sayfaları, gündem, toplantı ekranı, müdür onayı) odul/ (onur panelleri)
                    kisiler/ kurulum/ ayarlar/ panel/
                    imha/ yildevri/ guvenlik/ okul/
desktop/            main.py (kilit→geri yükleme→bütünlük→yedek→migrate→waitress thread→pencere),
                    server.py, lock.py, backup.py, restore.py, integrity.py, session_guard.py,
                    paths.py, dialogs.py
packaging/          pyinstaller/ (ortak spec + rthook + fonts.conf), windows/ (build.ps1,
                    dll_kapanisi.py, .iss, NOTLAR.md), linux/ (build.sh, .deb, kurulum provası),
                    fontlar/ (DejaVu 4 kesim), ikonlar/
website/            okulapp.org'a yönlendiren stub sayfalar (eski GitHub Pages
                    bağlantıları kırılmasın diye — tek kaynak okulapp.org, §5)
docs/               tasarim/ (331 satır genel tasarım), mevzuat/, kurulum.md, teknik-borc.md
scripts/gates.sh    tek komutluk kapı koşusu
.github/workflows/  kapilar.yml (her PR'da gates.sh adımları) + paketleme.yml +
                    r2-yukle.yml (Release → indir.okulapp.org) + en-son-surum.yml
                    (Release'i "en son" yap) + pages.yml (yönlendirme stub'ları)
```

**Açılış sırası (kritik, `desktop/main.py`):** tek-instance kilidi → bekleyen
geri yükleme (`desktop/restore.py`) → sürüm damgası → `PRAGMA integrity_check` →
günlük otomatik yedek (14 gün rotasyon; parola kuruluysa şifreli `.ddbak`, değilse
düz `.sqlite3`; `geri-yukleme-oncesi-*` klasörleri de 14 günde silinir) → migrate
öncesi ayrı kopya + `migrate --no-input` → `waitress`
arka plan thread'i → `pywebview` penceresi. Bütünlük denetimi bilinçli olarak
yedekten ÖNCE koşar (bozuk veriyle rotasyon sağlam yedekleri silmesin).
Her adımın hata yolu ayrı çıkış koduna bağlı (`docs/kurulum.md §7`).

Ölçek duygusu (2026.11.0-beta.1 itibarıyla, kaba; satır sayıları test ve göç dışı, parantezde
testlerle): backend ~24.300 satır Python (~46.200) + 1288 test · desktop/packaging ~3.200 satır
(~5.700) + 169 test · frontend ~27.700 satır TS/TSX (~39.100) + 556 test.

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
| Üretilen evrak PDF'i veritabanında (`GeneratedDocument.stored_pdf_b64`) saklanıyor | Kütükten yeniden indirme için bilinçli. İfade/savunma/davranış özeti metinleri de bu PDF'in içindedir; alan `EncryptedTextField` — parola kuruluysa şifreli. (Eski "no-trace" ifadesi artık geçerli DEĞİL; KVKK değerlendirmesi buna göre.) | `models/document_log.py` |
| Dosya ekleri (`MEDIA_ROOT`) şifrelenmiyor | Yalnız alan şifrelemesi seçildi; UI bunu açıkça söylüyor. Tam koruma = BitLocker/LUKS. | borç K2 |
| Şifreli kipte `uq_student_tckn_alive` etkisiz | Fernet deterministik değil; blind index bilinçli alınmadı (≤1000 kayıt). Tekillik serviste: `selectors.find_student_by_tckn`. | borç K1, §10.2 |
| Şifreleme anahtarı süreç ömrü boyunca bellekte | Bağlanacak oturum kimliği yok; her istekte Argon2id ~0,2 sn maliyet olurdu. Kilitleme = kapatma veya açık "Kilitle". | `shared/crypto.py` başlığı |
| Boşta-kalma otomatik kilidi yok | Aynı gerekçe. | borç K3 |
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
metne uygulanmaz. Şube adı için doğru yol `normalize.section_upper` (Türkçe büyük harf,
katlama YOK — "10/Ç" ≠ "10/C", borç M6).

### 7.3 İş günü vs takvim günü
Yasal sürelerin **hepsi iş günü** (`shared/working_days.py` + `is_working_day`
predicate enjeksiyonu). `timedelta(days=N)` ile süre hesabı gören her yer kusur
adayıdır. Ayrıca: **ara tatil resmî tatil olarak girilmez** — girilirse yasal
süre hesabı bozulur. Kasım/nisan ara tatili yalnız `HolidayKind.SCHOOL_BREAK`
türüyle girilir: `is_working_day`'i etkilemez, yalnız `is_school_open_day`'de
(uzaklaştırma günleri, md. 172/1-a "okulun açık olduğu sürede") atlanır.
Yasal süre → `is_working_day`; cezanın fiilen çekildiği gün → `is_school_open_day`.

### 7.4 Evrak/şablon paritesi
`documents.py::_student_context` anahtarları (`full_name, tckn, birth_date,
class_label, student_number`) **değişmeden** üretilmeli; değişirse 25 şablon
sessizce boş alan basar. Korunması gereken kilitler: **Dal A/B kısıtı** (kurula
sevksiz dosyada yalnız uyarı + tedbir + dizi pusulası üretilebilir),
**Form-16/17 yalnız kesinleşmiş kararda** ve **Dal B'de uyarı belgesi kilidi** (S12,
14.11.2026): kurula sevkli dosyada öğrencinin o dosyada müdür uyarısı kaydı yoksa Form-02
(öğrenci ve veli) ile veli görüşme tutanağı üretilmez; veli davet yazısı ve "veli gelmedi"
tutanağı kapsam dışıdır, Dal A'da kayıt aranmaz.

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

- **Ceza kararı yalnız disiplin kuruluna sevkli, açık dosyada** girilir (md. 163/2).
- **Onaysız karar ceza değildir** (md. 163/2, 169/2): tebliğ edilemez, kesinleşmez,
  davranış puanı düşürmez. Hukuken var sayılan cezalar tek yerden:
  `selectors.penalties_in_force` (onaylı + cezalı + bozulmamış + md. 171/2 ile
  kaldırılmamış) — puan, triaj ve EK-1 "önceki cezalar" bunu kullanır.
- **İtiraz mercii onaylayan merciin bir üstüdür** (md. 169/4):
  `services.decisions.appeal_authority_for_decision` — md. 197 ile ilçeye giden
  kararda il kurulu. "Değiştirildi" (REDUCED) sonucu cezayı ve puanı günceller.
- **Müdür kararı tek seçimdir:** yazılı uyarı / onur kuruluna sevk / disiplin
  kuruluna sevk. Yalnız uyarı → dosya otomatik `CLOSED`.
- **Müdür uyarısı (md. 157/7) ceza değildir**, davranış puanı düşürmez; geçmişte
  ceza/uyarı (uyarıyla kapanmış Dal A dosyası dahil) varsa yazılı uyarı yolu
  kapalıdır (md. 157/7-e, 166). Bu engel aşama atlama override'ıyla AŞILMAZ (S10,
  14.11.2026): yalnız AYRI işaret + AYRI gerekçeyle
  (`add_event(warning_block_override=True, warning_block_override_reason=…)`) aşılır;
  iz olayın `override_reason` alanına "md. 157/7-e engeli aşıldı: …" önekiyle yazılır.
- **md. 166:** öğrencinin aynı öğretim yılında yürürlükte cezası varsa ondan ağır
  olmayan ceza yalnız gerekçeyle (`md166_override_reason`) girilir; sıralama
  `selectors.decisions.PENALTY_SEVERITY`. Cezasız karar kural dışı.
- Dosya başına öğrenciye **tek canlı karar**. Puan ve onay/itiraz mercii cezadan
  **otomatik** türer. Yalnız `PENDING` + tebliğsiz + itirazsız karar düzenlenebilir.
- **Toplantı zorunlu (S8 — 14.11.2026):** yeni disiplin kararı yalnız dosyanın kayıtlı, yeter
  sayısı olan (md. 191/1) kurul toplantısına (`DisciplineMeeting`) bağlı girilir; karar tarihi =
  toplantı tarihi, ayrı tarih girilemez (`services.decisions.record_decision`; toplantı
  verilmezse dosyanın TEK toplantısı seçilir). Toplantı kurula sevk tarihinden önce olamaz.
  Yeter sayı karar anında yeniden doğrulanır (`services.committee.case_meeting_quorum`).
  `meeting IS NULL` = S8 öncesi toplantısız girilmiş karar: GEÇERLİDİR; onay/tebliğ/itiraz/
  kapanış toplantıya bakmaz, kayıt kendiliğinden değiştirilmez, geriye dönük toplantı
  üretilmez; arayüz "Toplantı kaydı yok" bilgisini gösterir. Canlı kararı bağlı toplantı
  silinemez; bağ KALDIRILAMAZ, yalnız taşınır: beklemedeki karar düzenlemede başka toplantıya
  (tarih toplantıya geçer — md. 197 iadesinden sonraki ikinci görüşme böyle kaydedilir),
  düzenlemeye kapalı karar ve eski karar yalnız AYNI tarihli toplantıya
  (`rebind_decision_meeting`). Bağlı karar çöp kutusundan, toplantısı silinmişse ya da toplantı
  yürürlükteki sevk tarihinden önce kaldıysa geri yüklenmez (eski bağsız karar bu denetime
  girmez). Toplantıya katılanlar her yerde AYNI kümedir (`services.committee.meeting_attendees`:
  sonradan kuruldan çıkarılan üye dahil — `meeting.attendees.all()` kullanma, çıkarılanı
  süzer). EK-1 imza heyeti kararın BAĞLI toplantısından, bağ yoksa dosyanın son toplantısından
  basılır. Göç yok: mevcut `DisciplineDecision.meeting` alanı kullanılır. Testlerde karar
  `tests/factories.py::decide` ile (gerçek yol), S8 öncesi kayıt `legacy_decision` ile kurulur.
- **Vekâlet kaydı (md. 188, 191/2 — S7, 14.11.2026):** kurul başkanı toplantıya katılmadıysa
  toplantı `chair_absent` ile kaydedilir ve kurula kurulun ASIL ÖĞRETMEN üyelerinden biri
  başkanlık eder (`services.committee.acting_chair_candidates`; yedek, veli ve öğrenci üye
  başkanlık edemez — dar yorum, kullanıcı kararı). Uygun üye yoksa ileti kurula üye eklemeyi
  ÖNERMEZ, md. 186-187'yi söyler. Başkan dosyada şikâyetçi / zarar gören ise o dosyanın YENİ
  toplantısı (dosya toplantısı ve dosya görüşme tutanağı) ancak vekâletle kaydedilir; kayıtlı
  tutanağın düzeltilmesinde vekâlet zorlanmaz (eski tutanak kilitlenmez). Katılmayan başkan
  yeter sayıya girmez (tam sayı değişmez); sayılamayan "bugünkü başkan" satırı `chair_skipped`
  ile gösterilir ve mevcut toplantının düzeltilmesini engellemez. Belgeler: vekâletli
  toplantıda EK-1, Form-11, md. 195 tutanağı ve karar defteri başkanlık eden üyeyi TEK
  ifadeyle basar (`documents.ACTING_CHAIR_ROLE`). Şikâyetçi / zarar gören başkan dosyanın
  BÜTÜN kurul evrakından çıkar (`documents._signing_panel`, `documents._case_committee`):
  vekâletli toplantı kaydı varsa başkanlık eden üye (ad satırı YALNIZ ad, etiket
  `ACTING_CHAIR_ROLE`; Form-12/13 gövdesi de vekâlete göre), yoksa boş (noktalı) hane ve eski
  sabit etiket; (şikâyetçi / zarar gören başkanda) ceza tebliğlerinde tebliğ eden hanesi her
  durumda boş. Başkanlık eden üye
  Form-12 ızgarasında ve Form-10 çağrılanlar tablosunda ikinci kez basılmaz; Form-10
  tablosunda o toplantı kaydında katılan yedek üye basılır (md. 188/1, 191/2 — yalnız bağlam:
  `documents._meeting_call_context`; kayıtta yedek yoksa ad uydurulmaz).
  Başkan şikâyetçi / zarar gören DEĞİLSE de (izinli başkan — kullanıcı kararı, 15.11.2026)
  dosyanın SON toplantı kaydı vekâletliyse Form-3, 4-6, 7-8, 9, 10, 12, 13 ve dizi pusulası
  başkanlık eden üyeyi AYNI biçimde basar; ceza tebliğleri bu durumda asıl başkanı basmayı
  sürdürür. "Son" = toplantı tarihi en geç olan kayıt: toplantı kaydından ÖNCE üretilen çağrı
  asıl başkanla çıkar; vekâletli toplantıdan sonra daha ileri tarihli vekâletsiz toplantı
  kaydedilirse evrak yeniden asıl başkanı basar. EK-1 kararın BAĞLI toplantısından basıldığı
  için çok toplantılı dosyada çağrı evrakından farklı kişi taşıyabilir. Son toplantı kaydı
  vekâletli değilse ve başkan şikâyetçi / zarar gören değilse bu belgelerin çıktısı değişmez. Eski kayıt kendiliğinden DEĞİŞTİRİLMEZ: ekranda uyarılır
  (`case_chair_warnings`, `council_chair_warnings`). Onur Kurulu (md. 182) kapsam dışıdır.
- **Müdür kurul kararını reddedemez** (md. 197): onaylar / gerekçeyle **bir kez**
  iade eder / (iade sonrası) ilçeye sevk eder.
- **Özgün ceza ve iade tarihi saklanır** (S11b — 14.11.2026): ceza üst kurulca (onayda)
  ya da itirazla İLK KEZ değişirken okul kurulunun verdiği ceza `board_penalty_type` /
  `board_suspension_days` alanlarına yazılır (tek yer: `services.decisions._apply_penalty_change`)
  ve ceza kurulun verdiğine geri dönse de BOŞALTILMAZ; "boş" yalnız "hiç değişmedi / S11
  göçünden önce değişti" demektir (o eski kayıtta özgün ceza onay merciinden okunur:
  `_legacy_board_penalty`). `penalty_type` her zaman YÜRÜRLÜKTEKİ cezadır — puan, yürürlük,
  itiraz mercii ve tebliğler ondan türer; EK-1, karar defteri, Form-18, onaya sevk yazısı
  kurulun verdiği cezayı basar. Üst kurul onayı "beklemede"ye geri alınırken itiraz kaydı
  yoksa ceza kurulun verdiğine geri yüklenir (`_restore_board_penalty`).
  `DisciplineAppeal.previous_*` ayrıdır: itiraza KONU ceza. `first_returned_at` kurula İADE
  tarihidir, ilçeye sevk onu ezmez; `returned_at` son md. 197 adımının tarihidir.
- **EK-1 "önceki cezalar" özeti anlık kopyadır** (S11c — 14.11.2026): `prior_penalties_summary`
  karar anında yalnız bu karardan ÖNCEKİ `penalties_in_force` ile derlenir, kullanıcı
  düzenleyebilir ve HİÇBİR ZAMAN kendiliğinden yeniden derlenmez. Bayatlık
  `prior_penalties_compiled` iziyle ölçülür (`selectors.prior_penalties_summary_is_stale`;
  elle düzenleme bayat sayılmaz). Yeniden derleme yalnız kullanıcı onayıyla ve açık dosyada.
- **İtiraz:** tebliğsiz itiraz olmaz; süre dışı itiraz da kaydedilir (işaretli);
  sonuçlanmış itiraza yeniden itiraz ve sonuç değişikliği yok (md. 169/4).
  `OVERTURNED` → `REJECTED` + puan iadesi. Okul değiştirme cezasında süresinde
  itiraz → uygulama bekletilir.
- **Kapanış uygunluğu (`close_eligible`):** onaylı karar + md. 197 askısı ve `PENDING` itiraz yok
  + tebliğ yapılmış + itiraz süresi dolmuş + 5 iş günü tampon.
  Kural hem "Kapat" ucunda hem CLOSED aşama olayında uygulanır; uygun değilse
  yalnız gerekçeli override (iz kaydedilir). **Cezasız karar istisnası** (S9, 14.11.2026):
  "ceza verilmesine yer olmadığı" kararı onaylanıp TEBLİĞ edildikten sonra itiraz süresi
  ve tampon beklenmez (itiraz yolu yok, md. 169/3). Kural karar bazındadır: cezalı
  kararların süreleri beklenir ve hakkında işlem yapılan her öğrencinin kararı girilmiş
  olmalıdır.
- **Kapalı dosyada kapanış dayanağı kilitli:** onay, tebliğ, md. 197 iade/sevk ve
  karar düzenleme/silme, karar–toplantı bağının değiştirilmesi, toplantı silme ve EK-1 önceki
  cezalar özetinin yeniden derlenmesi reddedilir;
  itiraz + sonucu, e-Okul, md. 171/2 serbest
  (`services.decisions._assert_case_open`). Kurula sevk tarihi = **son** müdür kararı
  (`committee_referred_on`; geri alınmış sevk/uyarı sayılmaz).
- Okul değiştirme cezası onayla uygulanır; **süresinde itirazda itiraz sonuçlanana
  dek uygulanmaz** (md. 172/2-ç, `_enforced_state`).
- `case_no` biçimi `{ders yılı adı}-NNNN`; **aktif ders yılı yoksa dosya açılamaz**.
  Sıra ders yılının KALICI sayacından gelir (`CaseNumberCounter`, S11a — 14.11.2026):
  imha (md. 157/7) ya da soft-delete edilen dosyanın numarası yeniden verilmez.
- Ceza tebliğinde **itiraz son günü basılmaz** (yalnız "5 iş günü" metni).
- **Yıl başına tek disiplin kurulu**, tek aktif `SchoolYear`. Kurul bileşimi (md. 185/1)
  UYARILIR, engellenmez (S5, 14.11.2026: `selectors.committee_composition_warnings`).
  Yeter sayıya (md. 191/1) yalnız kurul üyeleri girer; sayılmayan oy hakkı satırları
  `meeting_quorum_detail` ile adlarıyla gösterilir (S13).
- **Onur kurulu (md. 180-181):** üye sınıf seviyesi sicilden, seviye başına tek asıl
  üye, asıl ikinci başkan 11/12. sınıftan; onur belgesi müdür onayında uygunluk
  yeniden denetlenir, müdür onayı geri alınamaz (öncesi gerekçeyle geri alınır).
  Onur Kurulu, davranış puanı indirilmiş öğrenci için uygun görüş verebilir (md. 183/b)
  ama karar öncesi uyarılır (S6, 14.11.2026: gündem maddesi `honor_eligible`).
- **Onur belgesinde kurul kararı yalnız toplantıda** (kurul işleyişi, 04.10.2026):
  uygun görüş (md. 183/b) ve kabul/ret (md. 161/1) yalnız bir kurul toplantısının
  gündem maddesi karara bağlanarak verilir (`services.council.decide_agenda_item`);
  karar tarihi = toplantı tarihi; ÖDK maddesi md. 191/1 yeter sayısı olmadan karara
  bağlanmaz; olumsuz kararda gerekçe zorunlu; ret kurula göre ayrı durumdur
  (`HONOR_BOARD_DECLINED` / `COMMITTEE_REJECTED`). Karara bağlı maddesi olan toplantı
  silinemez, tarihi değişmez; geri alma maddeyi yeniden "karar bekliyor" yapar.

Süre matrisi (iş günü): itiraz tebliğ+5, sevk+5, kurul 10 (+1 uzatma), tedbir ≤10
(+2 uzatma, her biri ayrı ≤10 ve MEM onaylı; başlama+3 karar gününden; başlangıç tatil günüyse tedbir günleri izleyen ilk iş gününden), uzaklaştırma 1-5 gün, kapanış tamponu +5. Puan indirimleri
10/20/40/80. Hepsi `discipline_periods.py`'de.

---

## 9. Açık borç (zaten biliniyor)

Tam liste `docs/teknik-borc.md`. Özeti — **bunları yeniden keşfetme**:

*Doğrulanamayanlar (kod yazıldı, ortam kısıtı nedeniyle koşulmadı):* Qt penceresi
hiç açılmadı (D3) · paketlenmiş ikili üzerinden gerçek evrak üretimi (D4) · `.deb`
yükseltme yolu (D5) · Windows başlatıcı yolları: ikinci kopya kilit çakışması,
WebView2 yokluğu (D6). (D7 Argon2 paketi 27.09.2026'da `--kripto-duman` ile kapandı.)

*Kabul edilmiş bedeller:* K1-K5, K7 → §6 tablosunda karşılıkları var (K6 27.09.2026'da
`GRADUATED` "Mezun" durumuyla kapandı; "Ayrıldı" artık yalnız nakil demektir. K8 React
Router 7'ye yükseltmeyle kapandı; `npm audit --omit=dev` 0 açık).

Windows tarafında ayrıca `packaging/windows/NOTLAR.md` W1-W9 doğrulanmamış
varsayım listesi tutuyor.

---

## 10. Gözden geçirmede öncelik önerisi

Etki × yoğunluk sırasıyla:

1. **`backend/apps/disiplin/services/` + `selectors/`** — iş kurallarının kalbi;
   §8 invariantlarına karşı oku.
2. **`backend/apps/disiplin/views.py` (1700 satır) + `serializers.py`** — doğrulama
   boşlukları, 500 dönmesi gereken yerde 400, kısmi güncellemenin veri silmesi.
3. **`frontend/src/modules/disiplin/DisiplinDetayPage.tsx` (2891 satır) +
   `DecisionsSection.tsx` (2713)** — en büyük iki dosya, en çok durum barındıran
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
- **`bash scripts/gates.sh` yeşil olmadan iş bitmiş sayılmaz.** Aynı adımlar her PR'da
  `.github/workflows/kapilar.yml` ile CI'da da koşar; birini değiştiren ötekini de değiştirir. mypy `strict`,
  ruff `E,F,I,UP,B,DJ,S,C4`, satır 100.
- **Commit mesajları Türkçe**, Conventional Commits biçiminde ve kapsam etiketli:
  `fix(disiplin): …`, `feat(okul): …`, `chore(ci): …`, `docs: …`. Git geçmişine bak,
  kalıbı sürdür.
- **Yeni Python bağımlılığı eklersen** `packaging/pyinstaller/disiplin_defteri.spec`
  içindeki `hiddenimports`'u da güncelle (borç K7) — yoksa paket açılmaz, testler
  bunu yakalamaz.
- **Migration:** `okul` 0006'da, `disiplin` 0017'de (0014 dosya numarası sayacı, 0015
  md. 197 özgün ceza + ilk iade tarihi, 0016 önceki cezalar derleme izi, 0017 toplantıda
  başkana vekâlet — yalnız şema). Veri göçleri
  yalnız DÜZ alan okur: parola kuruluysa açılışta `migrate` koşarken anahtar henüz yoktur —
  şifreli alan okuyan/yazan göç yazma (kilitli kip testi:
  `test_s11_gocleri_kilitli_kipte_sifreli_alana_dokunmadan_kosar`). Şema değişikliği şifreli
  alan geçişini etkileyebilir (`0002_encrypt_sensitive_fields`) — dikkat.
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
| `docs/saha-provasi.md` | Okulda gerçek bilgisayarda D3-D6/D8 + W4-W9 kontrol listesi ve sonuç tablosu. |
| `packaging/README.md` | Paket üreten kişi için dosya haritası ve komutlar. |
| `packaging/windows/NOTLAR.md` | Windows'a özgü doğrulanmamış varsayımlar (W1-W9). |
| `README.md` | Genel tanıtım; güncel. |

---

## 13. Diğer ajanlar

Bu brifing eskiden `codex-bilgilendirme.md` adını taşıyordu; içerik buraya
taşındı. Claude dışındaki ajanlar (Codex vb.) için depo kökündeki `AGENTS.md`
bu dosyaya işaret eder — brifingi iki yerde tutma, yalnız burayı güncelle.
