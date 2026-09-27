# Teknik Borç Kütüğü

Bilinen, kabul edilmiş eksikler. Her satır: **ne**, **neden bırakıldı**, **ne
zaman kapanmalı**. Kapanan kalem silinmez, "KAPANDI (tarih/commit)" işaretlenir.

Son güncelleme: 24.09.2026.

---

## Doğrulanamayan (ortam kısıtı — kod yazıldı, koşulmadı)

| # | Kalem | Neden | Ne zaman kapanır |
|---|---|---|---|
| D3 | **Qt penceresi hiç açılmadı** (ekran yok) — Wayland oturumunda `QT_QPA_PLATFORM=xcb` gereği | Konteynerde görüntü sunucusu yok | Pardus saha provasında |
| D4 | **Paketlenmiş ikili üzerinden gerçek evrak üretimi** — duman testi yalnız WeasyPrint+font zincirini izole ediyor, `documents.py` + 25 şablon zinciri paket içinde koşmadı | DB + fixture gerekiyordu | Saha provasında bir dosya açıp EK-1 üretilerek |
| D5 | **`.deb` yükseltme yolu** (eski sürüm üstüne kurulum) | Yalnız temiz kurulum + kaldırma sınandı | İkinci sürüm çıkarken |
| D6 | **Windows başlatıcı yolları** (`msvcrt.locking`, `winreg`, `MessageBoxW`) | CI'da `--autotest` geçiyor ama tek-instance kilidinin İKİNCİ kopyayla çakışması ve WebView2 yokluğu senaryosu ayrıca koşulmadı | Saha provasında |
| D8 | **Paketlenmiş pencerede gerçek dosya indirme** (XLSX + PDF + TXT) | pywebview indirme izni ve Blob yaşam döngüsü kod/test düzeyinde düzeltildi; başsız CI işletim sistemi “Kaydet” akışını doğrulamaz | Windows ve Pardus saha provasında üç dosya türü indirilerek |

## Kabul edilmiş tasarım bedelleri

| # | Kalem | Gerekçe |
|---|---|---|
| K1 | **`uq_student_tckn_alive` şifreli kipte etkisiz** — Fernet aynı metni farklı token'a çevirir | Blind index alınmadı (tasarım §10.2: yerel ölçek ≤1000 kayıt). Tekillik servis katmanında: `selectors.find_student_by_tckn` — içe aktarma VE elle kayıt/düzenleme (`persons._assert_tckn_unique`, 24.09.2026) |
| K2 | **Dosya ekleri (MEDIA_ROOT) şifrelenmiyor** | Yalnız alan şifrelemesi seçildi; UI metni bunu açıkça söylüyor. Tam koruma için BitLocker/LUKS |
| K3 | **Boşta-kalma otomatik kilidi yok** | Tek kullanıcılı yerel program; kilit = kapatma ya da "Şimdi kilitle" |
| K4 | **FE'de global 423 yakalayıcı yok** (`lib/api.ts`) | Kilit yalnız açılışta ve "Şimdi kilitle" ile ekrana yansır; süreç ömrü boyunca anahtar bellekte olduğundan pratikte 423 ancak başka bir pencereden kilitlenirse görülür |
| K5 | **Gerekçeler saklanmıyor** (aşama geri alma, erken kapatma) | Tasarım AuditLog'u bilinçli kaldırdı ("tek kullanıcı; evrak kütüğü yeter"). UI artık saklandığı yönünde vaat VERMİYOR; kalıcı iz isteyen kullanıcı evrak kütüğüne manuel kayıt ekler |
| K7 | **`backend/` pakete kaynak ağaç olarak girer** (donmuş arşive değil) | `desktop/paths.py::resolve_backend_dir()` gerçek `settings.py` dosyası arıyor. Bedeli: backend'in üçüncü taraf import'ları spec'te elle `hiddenimports` sayılmalı — yeni bağımlılık eklenirse spec de güncellenmeli |
| K8 | **npm üretim denetiminde React Router için 2 orta seviye bildirim** | Düzeltme React Router 7'ye kırıcı yükseltme gerektiriyor. Uygulama SSR kullanmaz, yalnız sabit yerel rotalarda ve `127.0.0.1` içinde çalışır; yükseltme ayrı uyumluluk çalışması olarak yapılacak |

## Açık mevzuat kalemleri (2026-09 gözden geçirmesinden kalan)

Ayrıntı ve gerekçe: `docs/gelistirme-plani-2026-09.md`.

| # | Kalem | Neden bırakıldı |
|---|---|---|
| M1 | ~~AYNEN şablon metinleri~~ | KAPANDI 26.09.2026 — kullanıcı kararlarıyla Form-18, Form-15/17, Form-12 ve EK-1 müdür onay kutusu düzeltildi (ayrıntı aşağıda "Kapanmış"). Bu dört formda OYS birebir paritesi bilinçli olarak bırakıldı |
| M2 | ~~Eksik resmî belgeler~~ | KAPANDI 27.09.2026 — Grup 1 süreç yazıları, Grup 2 tutanaklar, Grup 3 Form-01 eklendi (aşağıda). Hepsinin metni mevzuattan türetildi; okulun saha örneği gelirse uyarlanır |
| M3 | ~~md. 180/181 onur kurulu~~ | KAPANDI 26.09.2026 — md. 181/1 üyelik düşmesi uyarısı ve md. 180 kompozisyon kuralları eklendi (aşağıda) |
| M4 | ~~md. 166 / 168/5 uyarıları~~ | KAPANDI 26.09.2026 — md. 166 kuralı eklendi (aşağıda); md. 168/5 (zihinsel engel/otizm) için bilinçli olarak alan EKLENMEDİ: kullanıcı kararıyla bu bilgi e-Okul/RAM kaydında tutulur ve kurulca dikkate alınır; özel nitelikli kişisel veri (KVKK md. 6) programda toplanmaz |
| M5 | ~~İmha~~ | KAPANDI 27.09.2026 — ders yılı ortası imha engellendi; yedeklerde kalan kopya ve çok öğrencili dosyada nakil imhasının dar kapsamı kullanıcı kararıyla kabul edildi (aşağıda) |
| M6 | ~~Şube adı Türkçe harf~~ | KAPANDI 26.09.2026 — kullanıcı kararıyla şube Türkçe büyük harfle saklanıyor (`normalize.section_upper`); eski "C" kayıtları otomatik dönüştürülmez (C mi Ç mi ayırt edilemez), yeniden içe aktarmayla TCKN üzerinden düzelir |
| M7 | ~~Tedbir toplam süresi~~ | KAPANDI 24.09.2026 — kullanıcı (okul yönetimi) teyidi: her uzatma ayrı süre (≤10 iş günü), en fazla iki kez, MEM onayı zorunlu |
| M8 | ~~Onur kararlarında geri alma yok; müdür onayında uygunluk denetimi yok~~ | KAPANDI 26.09.2026 — kullanıcı kararıyla (A) müdür onayında uygunluk yeniden denetlenir; müdür onayından önceki son adım gerekçeyle geri alınır (`UNDONE` olayı iz bırakır); müdür onayı kesindir |

## Kapanmış

| Kalem | Kapanış |
|---|---|
| K6 12. sınıflar yıl devrinde "Ayrıldı" (`LEFT`) olarak işaretleniyordu | KAPANDI 27.09.2026 — `StudentStatus.GRADUATED` ("Mezun", okul 0006). Yıl devri mezunu buna çevirir. Ayrım biçimsel değil: "Ayrıldı" nakil demektir ve md. 157/7-d tekil (nakil) imhasını ders yılı içinde serbest bırakır; mezun ise yıl sonu kuralına tabidir. Eski "Ayrıldı + 12. sınıf" kayıtları otomatik çevrilmez (nakil mi mezun mu ayırt edilemez); gerekirse öğrenci kartından elle düzeltilir |
| D7 Argon2 cffi ikilisinin pakette toplandığı hiç sınanmıyordu (`--autotest` parolasız koşar) | KAPANDI 27.09.2026 — `--kripto-duman` teşhis kipi (`packaging/pyinstaller/giris.py`): pakette gerçek KDF parametreleriyle Argon2id türetme + zarf sarmalama + `EncryptedTextField` yazma/okuma; Linux derlemesi, debian:11/12 kurulum provası ve Windows derlemesi bunu koşar (çıkış 9 = zincir bozuk). `--autotest`'e parola adımı yerine ayrı kip seçildi: açılış zincirine veri dizininde `guvenlik.json` bırakan bir test adımı sokmamak için |
| M2 Grup 3 Form-01 (md. 157/7-a değerlendirme ve öneri formu) yoktu | KAPANDI 27.09.2026 — GUIDANCE_ASSESSMENT: sınıf rehber + rehber öğretmen imzalı, önceki cezalar ("ilk defa" koşulu) ve uyarı özeti dolu, müdür GÖRÜLDÜ; md. 157/7-d imhasına girer. Form-01 kimliği yönetmelik metninden çıkarıldı (saha örneğiyle doğrulanmalı) |
| M2 Grup 2 tutanaklar yoktu: md. 157/7-b veli davet/görüşme/gelmedi, md. 158/3 arama, md. 195 tespit | KAPANDI 27.09.2026 — 3 yeni belge türü (veli: 3 sürüm); künye, veli ve sınıf sorumluları dolu, beyan elle. Veli görüşmesi belgeleri md. 157/7-d gereği nakil imhasına da girer |
| M2 Grup 1 süreç yazıları yoktu: md. 197 iade ve ilçeye gönderme, md. 169/1 onaya sevk, md. 175 MEM bilgilendirme/uzatma onayı, md. 192/3 müdür OLUR bloğu | KAPANDI 27.09.2026 — kullanıcı kararıyla (C, sırayla) 4 yeni belge türü + Form-13 OLUR bloğu; kayıttan dolu basılır, yanlış aşamada üretilmez. Resmî MEB örneği yok — saha örneği gelirse metin uyarlanır |
| Tekil (nakil) imha çok öğrencili dosyada yalnız uyarı kaydı + uyarı yazısını siliyor; dosya bağı, katılımcı kaydı ve diğer kütük satırları kalıyor (M5 alt kalemi) | KABUL EDİLDİ 27.09.2026 — kullanıcı kararıyla (C) dokunulmadı: md. 157/7-d imha konusu uyarı belgeleridir; diğer öğrencilerin dosyası bütünlüğünü korur |
| İmha edilen veri 14 günlük otomatik yedeklerde kalıyor (M5 alt kalemi) | KABUL EDİLDİ 27.09.2026 — kullanıcı kararıyla (C) dokunulmadı: yedekler şifreli (`.ddbak`, yalnız kurtarma anahtarıyla açılır) ve 14 günde kendiliğinden döner; geri dönüş noktalarını korumak öncelikli |
| İmha ders yılı ortasında yalnız rozetle uyarılıyordu (md. 157/7-d) (M5 alt kalemi) | KAPANDI 26.09.2026 — kullanıcı kararıyla (A) toplu imha yalnız ders yılı bittikten sonra; tekil imha ders yılı içinde yalnız sicilde "Ayrıldı" (nakil) öğrenci için. Tutanak ile uygulama arasında nakil geri alınırsa imha reddedilir |
| md. 180: onur kurulu kompozisyonu doğrulanmıyordu (sınıf seviyesi elle, aynı seviyeden iki asıl üye, 9/10. sınıftan ikinci başkan) (M3 alt kalemi) | KAPANDI 26.09.2026 — kullanıcı kararıyla (A) engellenir: seviye sicilden, her seviyeden tek asıl üye, asıl ikinci başkan yalnız 11/12. sınıftan; yedekler sınır dışı |
| md. 181/1: ceza alan öğrencinin onur genel kurulu / onur kurulu üyeliği düşmüyordu (M3 alt kalemi) | KAPANDI 26.09.2026 — kullanıcı kararıyla (B) otomatik düşürülmez; aktif üyede bu ders yılında yürürlükte ceza varsa `md181_penalty` uyarısı gösterilir, sonlandırma gerekçesi "md. 181/1: disiplin cezası (karar no)" olarak önerilir |
| md. 166: aynı öğretim yılında tekrar için "bir derece ağır ceza" hiç hatırlatılmıyordu (M4 alt kalemi) | KAPANDI 26.09.2026 — kullanıcı kararıyla (B) öğrencinin bu öğretim yılında yürürlükte cezası varsa ondan ağır olmayan ceza yalnız kurul gerekçesiyle girilir (`md166_override_reason`, evraka basılmaz); cezasız karar ve üst kurulun itiraz/onay değişiklikleri kural dışı |
| EK-1 müdür onay kutusu cezasız kararda yalnız "GÖRÜLMÜŞTÜR" basıyor, md. 197 iadesini dışlıyor ve "onay ve itiraz gerektirmez" için md. 191'e atıf yapıyordu (M1 alt kalemi) | KAPANDI 26.09.2026 — kullanıcı kararıyla cezasız kararda da "YENİDEN GÖRÜŞÜLMESİ HUSUSUNDA (md. 197)" kutusu basılıyor; md. 191 atfı bu cümleden kaldırıldı |
| Form-12 süre uzatma tutanağı hep "oy birliği" basıyordu (M1 alt kalemi) | KAPANDI 26.09.2026 — kullanıcı kararıyla üretimde "oy birliği / oy çoğunluğu" seçiliyor (md. 191/1; geçici alan, DB'ye yazılmaz) |
| Form-15/17 savunma alınmamış dosyada da "öğrencinin savunması alınmış" basıyordu (M1 alt kalemi) | KAPANDI 26.09.2026 — kullanıcı kararıyla ifade yalnız dosya kütüğünde öğrencinin savunma tutanağı (Form-11) varsa basılıyor (md. 194/1) |
| Form-18 itiraz edeni hep "veli", süreyi hep "süresinde", kararı "kesinleşmiştir" yazıyor, merciyi ceza türünden türetiyordu (md. 197 sevkinde "ilçe" — doğrusu il) (M1 alt kalemi) | KAPANDI 26.09.2026 — kullanıcı kararıyla OYS paritesi bu formda bırakıldı: itiraz eden, süre durumu, tebliğ tarihi, onay makamı ve itiraz mercii kayıttan basılıyor; müdür itirazında "orantılı" görüşü basılmıyor |
| Tedbir bildirimi uzatılmış tedbirde toplam süreyi "en fazla 10 iş günü" notuyla basıyordu (M1 alt kalemi) | KAPANDI 24.09.2026 — kullanıcı onayıyla şablon notu uzatma sayısını basıyor |
| SPA hiç servis edilmiyordu (`GET /` → 404; paket açılmazdı) | KAPANDI 24.07.2026 · `5d4c175` |
| Erişim logu PII sızdırıyordu (`?search=<öğrenci adı>`) | KAPANDI 24.07.2026 · `bbbca99` (ayrıca `django.setup()` susturmayı siliyordu) |
| 18 form varsayılan tarihi UTC'den türüyordu (TR'de gece bir gün geriye) | KAPANDI 24.07.2026 · `c16ee0f` + kaynak tarama kapısı |
| Tailwind `rounded-shape-full` ve `/8`–`/12` opaklıkları sessizce üretilmiyordu | KAPANDI 24.07.2026 · `c16ee0f` + derlenmiş CSS guard testi |
| **Windows paketleme yolu doğrulanmamıştı** (eski D1) | KAPANDI 24.07.2026 — CI'da uçtan uca yeşil: setup.exe + portable.zip üretiliyor, Türkçe PDF duman testi gömülü DejaVu ile geçiyor, `--autotest` çıkış 0 |
| **CI hiç koşmamıştı** (eski D2) | KAPANDI 24.07.2026 — depo açıldı, 6 koşuda 3 gerçek kusur bulundu ve kapatıldı (BOM, MSYS2 python gölgelemesi, fontconfig) |
| pywebview dosya indirmelerini varsayılan ayarla sessizce engelliyordu | KAPANDI 26.07.2026 — `ALLOW_DOWNLOADS` pencere oluşturulmadan açıldı; masaüstü koruma testi eklendi |
| Blob URL'si WebView isteği devralmadan aynı çağrı yığınında bırakılıyordu | KAPANDI 26.07.2026 — URL temizliği geciktirildi ve sahte zamanlayıcılı frontend testi eklendi |
