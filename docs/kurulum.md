# Disiplin Defteri — Kurulum ve Sorun Giderme Kılavuzu

Bu belge programı bir okul bilgisayarına kurup çalıştırmak içindir. Teknik
bilgi gerektirmez; adımlar sırayla izlenir.

> **Program internet bağlantısı gerektirmez.** Kurulduktan sonra tüm veriler
> yalnız o bilgisayarda kalır; hiçbir yere gönderilmez.

---

## 1. Hangi dosyayı indirmeliyim?

| Dosya | Ne zaman |
|---|---|
| `disiplin-defteri-<sürüm>-win64-setup.exe` | **Windows** — normal kurulum. Yönetici parolası GEREKMEZ. |
| `disiplin-defteri-<sürüm>-win64-portable.zip` | **Windows** — kurulum yapılamıyorsa (kilitli bilgisayar, USB'den çalıştırma). |
| `disiplin-defteri_<sürüm>_amd64.deb` | **Pardus / Debian / Ubuntu** — normal kurulum. Yönetici (sudo) parolası gerekir. |
| `disiplin-defteri-<sürüm>-linux-x64.tar.gz` | **Pardus / Linux** — yönetici parolanız yoksa. |

`SHA256SUMS.txt` dosyası indirilen dosyaların bozulmadığını doğrulamak içindir
(bkz. §7).

---

## 2. Windows kurulumu

### 2.1 Kurulum paketi ile (önerilen)

1. `disiplin-defteri-<sürüm>-win64-setup.exe` dosyasına çift tıklayın.
2. **"Windows bilgisayarınızı korudu" uyarısı çıkarsa:** bu, programın dijital
   imzası olmadığı içindir, virüs olduğu anlamına gelmez.
   **Daha fazla bilgi** → **Yine de çalıştır** deyin.
   * Dosyayı USB bellekten veya okulun yerel ağından kopyaladıysanız bu uyarı
     genellikle hiç çıkmaz.
3. Kurulum sihirbazında **İleri** ile ilerleyin. Kurulum klasörünü
   değiştirmenize gerek yoktur; program kendi kullanıcı klasörünüze kurulur:
   `C:\Users\<kullanıcı>\AppData\Local\Programs\Disiplin Defteri`
4. Kurulum sırasında "Microsoft Edge WebView2 bileşeni kuruluyor" adımı
   görünebilir — bu, programın pencereyi çizebilmesi için gereklidir.
5. Bitince Başlat menüsünden **Disiplin Defteri** ile açın.

### 2.2 Taşınabilir sürüm (kurulum yapmadan)

1. `disiplin-defteri-<sürüm>-win64-portable.zip` dosyasına sağ tıklayıp
   **Tümünü ayıkla** deyin. Hedef olarak Belgeler altında bir klasör seçin.
   *Program Files altına ayıklamayın — yazma yetkisi olmayabilir.*
2. Klasördeki `disiplin-defteri.exe` dosyasına çift tıklayın.

> **Not:** Taşınabilir sürüm WebView2 bileşenini kurmaz. Program açılmıyor ve
> "WebView2 bulunamadı" diyorsa §6.1'e bakın.

---

## 3. Pardus / Linux kurulumu

### 3.1 `.deb` paketi ile (önerilen)

**Grafik arayüzden:** `.deb` dosyasına çift tıklayın, açılan yazılım
yükleyicisinde **Kur** deyin ve yönetici parolanızı girin.

**Uçbirimden:**

```bash
sudo apt install ./disiplin-defteri_<sürüm>_amd64.deb
```

Bu komut programın ihtiyaç duyduğu sistem paketlerini (yazı tipi ve metin
dizme kütüphaneleri) kendiliğinden kurar.

Kurulduktan sonra program menüde **Ofis** (veya **Eğitim**) altında
**Disiplin Defteri** olarak görünür.

### 3.2 Taşınabilir arşiv ile (yönetici parolası olmadan)

```bash
tar -xzf disiplin-defteri-<sürüm>-linux-x64.tar.gz
cd disiplin-defteri-<sürüm>
./kur.sh
```

Program ev dizininize kurulur, menüye eklenir. Ayrıntılar arşivin içindeki
`BENIOKU.txt` dosyasındadır.

---

## 4. İlk açılış

Program ilk açıldığında **kurulum sihirbazı** çıkar:

1. Okul bilgileri (okul adı, il/ilçe, müdür adı) — evrak antetinde kullanılır.
2. Ders yılı (örn. 2026-2027) ve başlangıç/bitiş tarihleri.
3. Tatil takvimi — **resmî ve idari tatiller**. *Ara tatilleri GİRMEYİN:*
   yasal süreler iş günü üzerinden hesaplanır ve ara tatil iş günüdür.
4. Öğrenci ve personel listelerinin içe aktarılması (e-Okul Excel dosyası veya
   panodan yapıştırma).

Sihirbaz tamamlanmadan disiplin dosyası açılamaz.

---

## 5. Verileriniz nerede? Yedekleme

| | Windows | Pardus / Linux |
|---|---|---|
| Veritabanı | `%LOCALAPPDATA%\DisiplinDefteri\data` | `~/.local/share/disiplin-defteri/data` |
| Otomatik yedekler | `%LOCALAPPDATA%\DisiplinDefteri\backups` | `~/.local/share/disiplin-defteri/backups` |
| Günlük kayıtları | `%LOCALAPPDATA%\DisiplinDefteri\logs` | `~/.local/state/disiplin-defteri/logs` |

* Program **her açılışta** otomatik yedek alır (`gunluk-<tarih>.sqlite3`) ve
  yedekleri 14 gün saklar.
* Program **güncellenmeden önce** ayrıca bir yedek alır
  (`pre-migrate-<sürüm>-<tarih>.sqlite3`).
* **Yedekler aynı bilgisayardadır.** Disk arızasına karşı `backups` klasörünü
  ayda en az bir kez USB belleğe kopyalayın.

> **Önemli:** Programı kaldırmak veya yeniden kurmak bu klasörleri silmez.
> Bu davranış güncelleme sırasında kayıtların kaybolmasını önler. Aynı Windows
> kullanıcısıyla yeniden kurulan program bu nedenle önceki kayıtları tekrar
> görür.

### 5.1 Yedekten geri dönme

1. Programı **kapatın**.
2. `backups` klasöründeki en güncel dosyayı seçin
   (örn. `gunluk-2026-07-20.sqlite3`).
3. Bu dosyayı `data` klasörüne kopyalayın ve adını **`db.sqlite3`** yapın
   (eski `db.sqlite3` dosyasını silmeden önce başka bir yere taşıyın).
4. Programı yeniden açın.

### 5.2 Bütün verileri silip temiz başlama

Bu işlem kurum, personel, öğrenci/veli, kurul dosyaları, ekler ve bütün
yedekleri **geri alınamayacak biçimde siler**:

1. Programı kapatın.
2. Saklamak istediğiniz bir kayıt varsa önce §5'teki klasörü güvenli bir yere
   yedekleyin.
3. Windows'ta Dosya Gezgini adres çubuğuna
   `%LOCALAPPDATA%\DisiplinDefteri` yazıp açılan klasörün tamamını silin.
   Pardus/Linux'ta `~/.local/share/disiplin-defteri` klasörünü silin.
4. Programı yeniden açın. Kurum bilgilerini isteyen ilk kurulum sihirbazı
   görünmelidir.

Kurulum dosyaları kullanıcı verisi içermez. Paketleme işlemi; veritabanı,
yüklenen medya ve Excel dosyası pakete karışırsa otomatik olarak başarısız olur.

---

## 6. Sık karşılaşılan sorunlar

### 6.1 "Microsoft Edge WebView2 Çalışma Zamanı bulunamadı" (Windows)

Program pencereyi çizmek için WebView2 bileşenini kullanır. Windows 11'de
kuruludur, bazı Windows 10 kurulumlarında yoktur.

* Kurulum klasöründeki `MicrosoftEdgeWebView2Setup.exe` dosyasını çalıştırın.
* Yoksa okul bilişim sorumlusundan **"WebView2 Runtime"** kurulumunu isteyin.
* Program bileşen olmadan **bilerek açılmaz**: eski motorla açılsaydı boş beyaz
  bir pencere görürdünüz.

### 6.2 "Disiplin Defteri zaten çalışıyor"

Program aynı anda tek kopya çalışır (iki kopya veritabanını bozardı).
Görev çubuğunda açık pencereyi arayın. Pencere görünmüyorsa bilgisayarı
yeniden başlatın.

### 6.3 "Program başlatılamadı: yerel sunucuya bağlanılamadı"

Program kendi içinde küçük bir yerel sunucu çalıştırır ve **boş portu kendisi
seçer** — yani "port meşgul" hatası vermez. Bu ileti genellikle güvenlik
duvarı veya antivirüsün `127.0.0.1` (kendi bilgisayarınız) bağlantısını
engellediğini gösterir.

* Antivirüs/güvenlik duvarı ayarlarında programa izin verin.
* Kurumsal olarak yönetilen bilgisayarlarda bilişim sorumlusuna başvurun.

### 6.4 "Veritabanı bozuk"

Program açılışta veriyi denetler; bozuksa **açılmaz** (bozuk veriyle çalışıp
kayıtları büsbütün kaybetmemek için). §5.1'deki adımlarla en son yedeğe dönün.

### 6.5 "Program sürümü eski"

Veri, programın daha yeni bir sürümüyle oluşturulmuş. Bu bilgisayardaki
programı güncel sürüme yükseltip yeniden açın. (Örneğin veriyi başka bir
bilgisayardan kopyaladıysanız bu ileti çıkar.)

### 6.6 PDF/evrak üretilmiyor, boş sayfa veya bozuk karakter çıkıyor

Programın PDF motorunu tek komutla sınayabilirsiniz.

**Windows** (Başlat → `cmd`):

```
"%LOCALAPPDATA%\Programs\Disiplin Defteri\disiplin-defteri.exe" --pdf-duman "%USERPROFILE%\Desktop\deneme.pdf"
```

**Pardus / Linux:**

```bash
disiplin-defteri --pdf-duman ~/deneme.pdf
```

Oluşan `deneme.pdf` dosyasında **ĞÜŞİÖÇ ığüşiöç** yazısı düzgün görünüyorsa PDF
motoru sağlamdır; sorun belgeye özeldir. Görünmüyorsa veya komut hata verirse
`logs` klasöründeki `uygulama.log` dosyasıyla birlikte bilişim sorumlusuna
başvurun.

Linux'ta eksik sistem paketleri şu komutla tamamlanır:

```bash
sudo apt install libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz0b \
                 libfontconfig1 libglib2.0-0 fonts-dejavu-core
```

### 6.7 Program hiç açılmıyor, hata da vermiyor

`logs` klasöründeki `uygulama.log` dosyasının son satırlarına bakın (§5'teki
tablo). Program her hatayı buraya yazar; kişisel veri yazmaz, bu yüzden dosya
paylaşılabilir.

---

## 7. Çıkış kodları (bilişim sorumlusu için)

Program bir sorun nedeniyle açılmadığında süreç çıkış kodu ile sebebi bildirir.
Uçbirimden `disiplin-defteri --autotest` çalıştırıp kodu okuyabilirsiniz
(pencere açmadan tüm açılış zincirini dener).

| Kod | Anlamı | Yapılacak |
|---|---|---|
| 0 | Her şey yolunda | — |
| 1 | Beklenmeyen hata | `uygulama.log` son satırları |
| 2 | Program zaten çalışıyor | Açık pencereyi bul / yeniden başlat |
| 3 | Veritabanı bozuk | §5.1 yedekten dönüş |
| 4 | Program sürümü veriden eski | Programı güncelle |
| 5 | Veritabanı güncellenemedi | §5.1 yedekten dönüş (`pre-migrate-*`) |
| 6 | Yerel sunucu başlamadı | §6.3 güvenlik duvarı/antivirüs |
| 7 | Pencere motoru yok (WebView2) | §6.1 |
| 8 | PDF duman testi başarısız | §6.6 |

---

## 8. İndirilen dosyayı doğrulama

`SHA256SUMS.txt` içindeki özet ile indirdiğiniz dosyanın özetini karşılaştırın.

**Windows (PowerShell):**

```powershell
Get-FileHash .\disiplin-defteri-<sürüm>-win64-setup.exe -Algorithm SHA256
```

**Pardus / Linux:**

```bash
sha256sum -c SHA256SUMS.txt
```

---

## 9. Programı kaldırma

* **Windows:** Ayarlar → Uygulamalar → **Disiplin Defteri** → Kaldır.
  Taşınabilir sürümde klasörü silmek yeterlidir.
* **Pardus / Linux (.deb):** `sudo apt remove disiplin-defteri`
* **Pardus / Linux (taşınabilir):** arşivin içindeki `./kaldir.sh`

**Kaldırma verilerinizi SİLMEZ.** Disiplin kayıtları ve yedekler §5'teki
klasörlerde kalır; programı yeniden kurduğunuzda kaldığınız yerden devam
edersiniz. Veriyi de silmek isterseniz o klasörleri elle silin — geri dönüşü
yoktur.
