# Disiplin Defteri — Saha Provası Kontrol Listesi

Bu liste, otomatik testlerin **sınayamadığı** kalemleri okulda gerçek bir
bilgisayarda doğrulamak içindir (`docs/teknik-borc.md` D3-D6, D8 ve
`packaging/windows/NOTLAR.md` W4-W9). Bir prova yaklaşık **45 dakika** sürer.

**Kim yapar:** bilişim sorumlusu ya da müdür yardımcısı. Uçbirim/komut istemi
adımları kopyala-yapıştır düzeyindedir.

**KVKK:** Provada **gerçek öğrenci verisi kullanmayın.** Adımlar uydurma bir
öğrenciyle yürür. Provadan sonra §6'daki temizlik adımını uygulayın.

Her adımın yanında **Beklenen** sonuç yazılıdır. Farklı bir şey görürseniz
adımın numarasını, ekranın fotoğrafını ve `uygulama.log` dosyasını (§5)
not edin; sonuç tablosuna (§7) "✗" yazın.

---

## 0. Hazırlık

- [ ] Paketleri **indir.okulapp.org** ya da GitHub Releases'ten indirin
      (Windows: `…-win64-setup.exe` ve `…-win64-portable.zip`;
      Pardus: `….deb`). §5.2 yükseltme provası için bir **önceki sürümün**
      paketi de gerekir (ör. `2026.7.0-beta.1`).
- [ ] Mümkünse provayı **boş bir kullanıcı hesabında** ya da sanal makinede
      yapın; kendi çalışma verilerinizin olduğu hesapta yapmayın.
- [ ] Windows'ta **yönetici olmayan** bir hesap hazır olsun (adım 1.1).

---

## 1. Windows (10/11)

### 1.1 Kurulum — W8, W6/W7
- [ ] `setup.exe`'yi **yönetici olmayan** hesapta çalıştırın.
      **Beklenen:** UAC (yönetici parolası) istemez; kurulum Türkçedir;
      program `%LOCALAPPDATA%\Programs\Disiplin Defteri` altına kurulur.
- [ ] SmartScreen uyarısı çıkarsa **Daha fazla bilgi → Yine de çalıştır**.
      Çıkıp çıkmadığını not edin.

### 1.2 İlk açılış ve pencere — W9, D6
- [ ] Başlat menüsünden **Disiplin Defteri**'ni açın.
      **Beklenen:** pencere 10 sn içinde açılır, kurulum sihirbazı görünür.
      Beyaz/boş pencere **olmamalı**.
- [ ] Sihirbazı uydurma bilgilerle tamamlayın (okul adı "DENEME LİSESİ",
      bu ders yılı, bir resmî tatil).
- [ ] **Ayarlar → Tatiller**'den kasım ara tatilini **"Ara tatil (okul kapalı)"**
      türüyle ekleyin. **Beklenen:** kayıt listede bu türle görünür.

### 1.3 İkinci kopya — D6 (kilit çakışması)
- [ ] Program açıkken Başlat menüsünden **bir kez daha** açın.
      **Beklenen:** "Disiplin Defteri zaten çalışıyor" iletisi; ikinci pencere
      açılmaz, ilk pencere çalışmaya devam eder.

### 1.4 Evrak üretimi (paket içinde) — D4, W4
- [ ] **Kişiler**'den uydurma bir öğrenci ekleyin: ad "İLKNUR ÇAĞLAR",
      sınıf 10, şube "Ç" (Türkçe harfleri sınamak için).
- [ ] **Disiplin → Yeni dosya** ile bu öğrenciye dosya açın, bir olay
      tarihi ve kısa açıklama girin.
- [ ] Dosyanın evrak bölümünden **Dizi Pusulası** üretip açın.
      **Beklenen:** okul adı antette, tarih bugünün tarihi.
- [ ] Müdür kararı olarak **disiplin kuruluna sevk** seçin. (Sevksiz dosyada
      program yalnız uyarı/tedbir türü belgelere izin verir — bu bilinçli.)
- [ ] **İfade Tutanağı** ve **EK-1 Okul Öğrenci Ödül ve Disiplin Kurulu
      Kararı** üretip açın.
      **Beklenen:** "İLKNUR ÇAĞLAR" ve şube "10/Ç" **doğru Türkçe harflerle**
      (İ, Ç, Ğ) basılı; öğrenci bilgileri dolu.

### 1.5 Dosya indirme — D8
- [ ] Bir PDF'i **İndir** ile kaydedin. **Beklenen:** "Farklı kaydet" penceresi
      açılır, dosya seçtiğiniz yere iner ve açılır.
- [ ] **Kişiler → Öğrenciler** ekranındaki **Şablon indir** ile XLSX şablonu indirin.
      **Beklenen:** Excel/LibreOffice ile açılır.
- [ ] **Ayarlar → Güvenlik**'te parola koyun (adım 1.6); gösterilen **kurtarma
      anahtarını** `.txt` olarak indirin. **Beklenen:** metin dosyası iner.

### 1.6 Parola — D7'nin saha karşılığı
- [ ] **Ayarlar → Güvenlik → Parola koy**. Parola belirleyin.
- [ ] **Şimdi kilitle**'ye basın. **Beklenen:** kilit ekranı gelir.
- [ ] Yanlış parola girin → reddedilir. Doğru parolayla açın → veriler yerinde.
- [ ] Programı kapatıp açın → açılışta parola sorulur.

### 1.7 WebView2 yokken — D6, W5 (yalnız sanal makine/deneme bilgisayarı)
- [ ] WebView2 kurulu **olmayan** bir Windows'ta **taşınabilir zip**'i açıp
      `disiplin-defteri.exe`'yi çalıştırın.
      **Beklenen:** Türkçe "WebView2 bulunamadı" iletisi ve indirme yönlendirmesi;
      beyaz pencere **olmamalı**. (Kurulu bilgisayarda bu adımı atlayın.)

### 1.8 Taşınabilir sürüm — W8
- [ ] Zip'i USB belleğe ya da Belgeler altına ayıklayıp çalıştırın.
      **Beklenen:** açılır; SmartScreen genellikle çıkmaz.

---

## 2. Pardus 23 (ve varsa Pardus 21)

### 2.1 Kurulum
- [ ] `.deb` dosyasına çift tıklayıp **Kur** deyin (ya da
      `sudo apt install ./disiplin-defteri_*.deb`).
      **Beklenen:** bağımlılıklar kendiliğinden kurulur; menüde
      **Ofis/Eğitim → Disiplin Defteri** görünür.

### 2.2 Pencere — D3
- [ ] Menüden açın. **Beklenen:** Qt penceresi açılır, kurulum sihirbazı görünür.
- [ ] Pencere açılmazsa uçbirimde şunu deneyin ve sonucu not edin:
      `QT_QPA_PLATFORM=xcb disiplin-defteri`
      (Wayland oturumlarında gerekebilir.)

### 2.3 Windows adımlarının Pardus karşılığı
- [ ] 1.2 (sihirbaz + ara tatil), 1.3 (ikinci kopya), 1.4 (evrak),
      1.5 (indirme), 1.6 (parola) adımlarını aynen tekrarlayın.

---

## 3. Yükseltme — D5 (eski sürümün üstüne kurulum)

Bu adım gerçek kullanımın en riskli anıdır: okuldaki kayıtlar yeni sürüme
taşınır.

- [ ] Önce **önceki sürümü** kurun, açın, sihirbazı tamamlayıp bir öğrenci ve
      bir disiplin dosyası oluşturun, kapatın.
- [ ] Yeni sürümü **kaldırmadan üstüne** kurun
      (Windows: yeni `setup.exe`; Pardus: `sudo apt install ./yeni.deb`).
- [ ] Açın. **Beklenen:** öğrenci ve dosya yerinde; ekranda hata yok.
- [ ] Yedek klasöründe (§5) `pre-migrate-…` adlı bir **güncelleme öncesi
      yedek** oluştuğunu görün.

---

## 4. Otomatik teşhis komutları (isteğe bağlı, 2 dk)

Uçbirim/komut isteminde çalıştırın; her biri **0** ile bitmeli.

| Komut | Sınadığı |
|---|---|
| `disiplin-defteri --autotest` | açılış zinciri (kilit, yedek, veritabanı, sunucu) |
| `disiplin-defteri --pdf-duman deneme.pdf` | PDF motoru + Türkçe yazı tipi |
| `disiplin-defteri --kripto-duman` | parola/şifreleme bileşeni |

Windows'ta `disiplin-defteri` yerine
`"%LOCALAPPDATA%\Programs\Disiplin Defteri\disiplin-defteri.exe"` yazın.
Çıkış kodunu görmek için: Windows `echo %ERRORLEVEL%`, Pardus `echo $?`.
Kodların anlamı: `docs/kurulum.md` §7.

---

## 5. Bir şey ters giderse

| Ne | Windows | Pardus |
|---|---|---|
| Günlük (`uygulama.log`) | `%LOCALAPPDATA%\DisiplinDefteri\logs` | `~/.local/state/disiplin-defteri/logs` |
| Yedekler | `%LOCALAPPDATA%\DisiplinDefteri\backups` | `~/.local/share/disiplin-defteri/backups` |

`uygulama.log` kişisel veri içermez; paylaşılabilir.

---

## 6. Provadan sonra temizlik

Uydurma veriler gerçek kullanıma karışmasın diye: programı kapatın ve
`docs/kurulum.md` §5.2'deki adımlarla veri klasörünü silin (yedekler dahil).
Program sonraki açılışta kurulum sihirbazıyla temiz başlar.

---

## 7. Sonuç tablosu

Doldurup `docs/teknik-borc.md`'deki ilgili satırı "KAPANDI (tarih, prova)"
olarak işaretleyin; ✗ varsa adım numarası + log ile bildirin.

| Adım | Kalem | Windows | Pardus 23 | Pardus 21 |
|---|---|---|---|---|
| 1.1 | W8 kullanıcı kurulumu | | — | — |
| 1.2 | W9 / D3 pencere açılıyor | | | |
| 1.3 | D6 ikinci kopya engelleniyor | | | |
| 1.4 | D4 evrak paket içinde, Türkçe harfler | | | |
| 1.5 | D8 PDF / XLSX / TXT indirme | | | |
| 1.6 | Parola koy / kilitle / aç | | | |
| 1.7 | D6 WebView2 yokken ileti | | — | — |
| 1.8 | Taşınabilir sürüm | | | |
| 3 | D5 yükseltme, veri korunuyor | | | |
| 4 | Teşhis komutları 0 | | | |

Prova tarihi: ____________ Yapan: ____________ Sürüm: ____________
