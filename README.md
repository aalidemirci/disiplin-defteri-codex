# Disiplin Defteri

Tek kullanıcılı, girişsiz/şifresiz, masaüstünde çalışan bir disiplin kurulu programı.
Bir ortaöğretim kurumunun disiplin süreçlerini (dilekçe/ihbar → rehberlik aşaması →
müdür kararı → gerekirse kurul → itiraz → kapanış) uçtan uca yönetir; her adımda
gereken resmi evrakı (16 disiplin belge türü + dizi pusulası + karar defteri + müdür
uyarısı formları + 3 onur/ödül PDF'i) üretir ve Ortaöğretim Kurumları Yönetmeliği
md. 157-206'daki iş günü tabanlı yasal süreleri (itiraz, tebliğ, kurul kararı, tedbir,
kapanış) otomatik takip eder. Kayıtlar ders yılı bazlıdır.

Program internet veya ağ bağlantısı gerektirmez; okulun kendi bilgisayarında
(Windows veya Pardus) tek başına kurulup çalışır. Öğrenci ve personel bilgileri
e-Okul ihracından veya Excel dosyasından/yapıştırarak içe aktarılır; rol atamaları
(Müdür, Disiplin Kurulu Başkanı vb.) personel yüklendikten sonra arayüzden yapılır.
Bu proje, OYS (Okul Yönetim Sistemi) adlı ayrı bir okul yönetim sisteminin olgun
disiplin modülünden kod kopyalanarak türetilmiştir; OYS'ye çalışma zamanında hiçbir
bağımlılığı yoktur — bağımsız bir depo olarak yaşar.

## Mimari

Backend Django + DRF üzerine SQLite ile kurulu (authsuz, yalnız `127.0.0.1`);
durum makinesi, yasal süre motoru ve evrak üretimi (WeasyPrint ile PDF) OYS'nin
disiplin modülünden aynen veya uyarlanarak taşınır. Frontend React + TypeScript +
Vite, OYS'nin Material Design 3 arayüz kitinden türetilir. Masaüstü kabuğu
`pywebview` ile backend'i arka planda başlatıp yerel bir pencerede gösterir;
paketleme Windows için PyInstaller + Inno Setup, Pardus/Linux için PyInstaller +
`.deb` ile yapılır. Detay: `docs/tasarim/2026-07-23-genel-tasarim.md`.

## Geliştirme

Tüm bağımlılıklar Docker konteynerinde çalışır; host'a Python/Node kurulmaz.

```bash
docker compose build backend
docker compose run --rm backend python manage.py migrate
docker compose run --rm frontend npm ci        # ilk kurulumda ve lock dosyası değişince
bash scripts/gates.sh
```

`scripts/gates.sh` sırasıyla backend konteynerinde `pytest`, `ruff check`,
`ruff format --check`, `mypy`'yi; masaüstü ve paketleme testlerini; ardından
frontend konteynerinde `tsc` (typecheck), `eslint`, `prettier --check` ve
`vitest`'i çalıştırır. Herhangi biri kırmızı olursa durur.

Docker Compose proje adı `disiplin-defteri-codex` olarak sabittir. Bu sayede
PowerShell, Git Bash ve CI aynı imaj/önbelleği kullanır; başka Docker projelerinin
konteyner veya ağlarına dokunulmaz.

## Depo yerleşimi

```
disiplin-defteri/
├── backend/            # Django: config/, apps/okul/, apps/disiplin/, shared/, templates/
├── frontend/            # React + TS + Vite + Tailwind M3 ekranları ve testleri
├── desktop/             # pywebview başlatıcı, yedek, kilit, bütünlük ve yerel sunucu
├── packaging/           # PyInstaller, Inno Setup ve .deb üretim/test betikleri
├── docker/, docker-compose.yml
├── scripts/gates.sh     # tek komutla test+lint+format+tip kapısı (backend+frontend)
└── docs/                # tasarım dokümanı + mevzuat kopyaları
```

## Şifreli veritabanı yedeği

Ayarlar → Güvenlik ekranındaki “Şifreli yedeği indir” eylemi, tutarlı SQLite
görüntüsünü cihazda `X25519 + AES-256-GCM` ile şifreler ve kullanıcıya yalnız
`.ddbak` kapsayıcısını verir. Düz veritabanı ara dosyası oluşturulmaz. Özellik
kullanılmadan önce uygulama parolası kurulmalı ve uygulamanın kilidi açık olmalıdır.

Program herhangi bir bulut hesabına bağlanmaz ve otomatik yükleme yapmaz.
Kullanıcı indirdiği dosyayı USB belleğe, NAS'a veya tercih ettiği bulut klasörüne
kendi yerel imkânlarıyla kopyalar. Uygulamanın kurtarma amaçlı yerel günlük ve
güncelleme öncesi yedekleri de aynı şifreli `.ddbak` biçimindedir.

## Durum

**F0-F5 geliştirme fazları tamamlandı; sürüm `2026.7.0-beta.1`.** Okul kurulumu ve
kişi aktarımı, disiplin/onur kurulu iş akışları, 25 resmî evrak şablonu,
uygulama parolası, otomatik yedekleme ve Windows/Linux paketleme kodu çalışır
durumdadır. Tam kalite kapısı 26.07.2026 tarihinde backend, masaüstü/paketleme
ve frontend için yeşil koşmuştur.

Gerçek masaüstü ortamında hâlâ saha doğrulaması isteyen başlıklar (Qt penceresi,
paketlenmiş ikiliden uçtan uca evrak/indirme, `.deb` yükseltmesi ve parola
kurulu paket yolu) `docs/teknik-borc.md` dosyasında tutulur. “CI yeşil” ifadesi
bu donanım/GUI senaryolarının doğrulandığı anlamına gelmez.

## Belgeler

- `docs/tasarim/2026-07-23-genel-tasarim.md` — genel tasarım: kararlar, keşif
  bulguları, mimari, veri modeli, paketleme/dağıtım, risk kütüğü, faz planı.
- `docs/mevzuat/ortaogretim-yonetmeligi-disiplin-md157-206.md` — Ortaöğretim
  Kurumları Yönetmeliği'nin disiplin bölümü (md. 157-206), tam metinden alınmıştır.
- `docs/mevzuat/notlar/` — disiplin ceza süreleri/itiraz, disiplin kurulu
  kompozisyonu ve onur kurulu üzerine Q&A notları.
- MEB Önleyici Disiplin Uygulamaları Öğretmen Rehber Kitabı depoda kopyalanmaz;
  [Ortaöğretim Genel Müdürlüğünün resmî yayın sayfasından](https://ogm.meb.gov.tr/www/onleyici-disiplin-uygulamalari-ogretmen-rehber-kitabi-yayimlandi/icerik/1726)
  erişilir.

## Lisans ve iletişim

Copyright © 2026 Ahmet Ali DEMİRCİ — <aalidemirci@gmail.com>

Bu sürüm **PolyForm Noncommercial License 1.0.0** ile sunulur. Eğitim kurumları,
kamu kurumları, kâr amacı gütmeyen kuruluşlar ve bireyler programı ticari olmayan
amaçlarla ücretsiz kullanabilir, değiştirebilir ve ticari olmayan şekilde
dağıtabilir. Ücretli dağıtım, ücretli teknik destek paketine bağlama, barındırılan
veya yönetilen hizmet olarak sunma ya da başka bir ticari kullanım için telif
hakkı sahibinden ayrıca yazılı ticari lisans alınmalıdır.

Gelecekte yayımlanacak sürümlerin koşulları değişebilir; ücretsiz yayımlanmış bir
sürüm kendi lisans koşullarıyla ücretsiz ve ticari olmayan kullanıma açık kalır.
Bağlayıcı koşullar için [`LICENSE`](LICENSE) dosyasına bakın. Talep, öneri, hata
bildirimi ve şikâyetler yukarıdaki e-posta adresine iletilebilir.

## Proje web sitesi

Tanıtım, güvenli indirme, kullanım kılavuzu ve KVKK bilgilendirmesi
[okulapp.org/disiplin-defteri](https://okulapp.org/disiplin-defteri/) adresinde
yayımlanır (MEB ağında GitHub engelli olduğu için GitHub Pages'ten taşındı;
kaynağı ayrı bir depodadır). Site ziyaretçi analizi, reklam, çerez, iletişim
formu veya üçüncü taraf istemci betiği kullanmaz. Bu depodaki `website/`
klasörü yalnız eski GitHub Pages bağlantılarını okulapp.org'a yönlendiren stub
sayfaları içerir.
