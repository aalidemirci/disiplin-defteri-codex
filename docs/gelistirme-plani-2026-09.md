# Geliştirme Planı — Mevzuat Uyum Düzeltmeleri (Eylül 2026)

Kaynak: 23.09.2026 gözden geçirmesi (Ortaöğretim Kurumları Yönetmeliği md. 157-206
karşılaştırması). Her maddenin kusuru önce bir testle yeniden üretildi, sonra
düzeltildi; testler `backend/apps/disiplin/tests/test_mevzuat_uyum.py` içinde.

Durum işaretleri: ✅ yapıldı · ⏸ bilinçli olarak ertelendi (`docs/teknik-borc.md` M1-M8).

## Faz 1 — Hukuki sonucu doğrudan yanlış olanlar (backend)

| # | Kusur | Mevzuat | Durum |
|---|---|---|---|
| 1 | Onaysız karar tebliğ ediliyor, "kesinleşiyor", e-Okul'a işleniyor, puan düşürüyordu | 163/2, 169/2 | ✅ Tebliğ onay ister; `decision_is_final` onaysızı kesin saymaz; puan yalnız onaylı cezadan düşer |
| 2 | Kurula sevk edilmemiş / kapalı dosyaya ceza girilebiliyordu | 163/2 | ✅ `record_decision` sevk + açık dosya + sevk sonrası tarih ister |
| 3 | İtirazda "değiştirildi" cezayı ve puanı değiştirmiyordu | 170, 200/Ç | ✅ Yeni ceza zorunlu; karar ve puan güncellenir, eski tür itiraz kaydında |
| 4 | Sonuçlanmış itiraza yeniden itiraz / sonuç değişikliği | 169/4 | ✅ Engellendi |
| 5 | "Kapatıldı" aşama olayı kapanış denetimini deliyordu | 169 | ✅ Aynı uygunluk kuralı; uygun değilse gerekçeli override + iz |
| 6 | Bozulan / cezasız kararlar "önceki ceza" ve triajda sayılıyordu | 171/3, 157/7 | ✅ Tek kaynak: `selectors.penalties_in_force` |

## Faz 2 — Orta öncelik (backend)

| # | Kusur | Mevzuat | Durum |
|---|---|---|---|
| 7 | md. 197 ile ilçeye giden kararda itiraz mercii "ilçe" (doğrusu il) | 169/4, 202/1-b | ✅ Kayıt: onaylayan merciin bir üstü; Form-18 metni de kayıttan (26.09.2026) |
| 8 | Uzaklaştırma günleri ara tatile/hafta sonuna düşüyordu | 172/1-a | ✅ `is_school_open_day` + `SCHOOL_BREAK` tatil türü; başlangıç günü doğrulanır |
| 9 | Form-16/17 kınamada da üretilebiliyordu | 164/2, 172/1 | ✅ Yalnız kısa süreli uzaklaştırma |
| 10 | EK-1 imzası toplantıya katılanları değil, aktif yılın kurulunu basıyordu | 196/1, 185/4 | ✅ Dosyanın yılının kurulu + toplantı katılımcıları |
| 11 | Toplantı yeter sayısı / şikâyetçi üye denetimi yoktu | 191/1-2 | ✅ Salt çoğunluk + şikâyetçi/zarar gören/hakkında işlem yapılan üye engeli |
| 12 | md. 197 iadesi tekrarlanabiliyor; "ilçeye gönderildi" çıkmaz sokak | 197 | ✅ Tek iade; gerekçeler korunur; ilçe kurulu kararı girilebilir |
| 13 | "İlk defa" koşulu korunmuyordu (yazılı uyarı ikinci kez) | 157/7, 157/7-e | ✅ Geçmişi olan öğrenciye yazılı uyarı yolu override'sız kapalı; Dal A dosyası triajda uyarı sayılır. ⏸ İmha zamanı (M5) |
| 14 | Şifreli kipte aynı TCKN ile ikinci öğrenci | K1 | ✅ Elle kayıtta da servis denetimi |
| 15 | Ceza kaldırma / puan iadesi yoktu | 171/2-3 | ✅ Kaldırma + geri alma; puan/triaj/EK-1'den düşer |
| 16 | 15 Temmuz / 30 Ağustos takvimde yoktu; bayram tablosu 2029'da bitiyordu | — | ✅ Seed penceresi 31 Ağustos'a uzadı; tablo 2031'e kadar (tahmini) |
| 17 | Onur kurulu başkanı disiplin kuruluna üye yapılabiliyordu | 182 | ✅ Engellendi |
| 18 | Yanlış "yazılı uyarı" düzeltilse de dosya Dal A'da kalıyordu | — | ✅ Dal en son müdür kararından türer |
| 19 | 18 yaş itiraz kontrolü yoktu | 169/3 | ✅ Doğum tarihine göre |

## Faz 3 — Arayüz

| # | Değişiklik | Durum |
|---|---|---|
| 20 | Tebliğ düğmesi yalnız onaylı kararda; "Kurula iade" bir kez; "İlçe kurulu kararı" | ✅ |
| 21 | Onayda / itiraz sonucunda "değiştirildi" için yeni ceza seçimi | ✅ |
| 22 | İtirazı sonuçlanmış kararda "İtiraz ekle" yok; md. 171/2 kaldırma formu | ✅ |
| 23 | "Karar ekle" yalnız kurula sevkli açık dosyada | ✅ |
| 24 | EK-1 anlatı formu "Kapat" sonrası bayat veriyle ezme riski | ✅ |
| 25 | Dosya listesi 200 kayıtta kesiliyordu | ✅ Tüm sayfalar toplanır |
| 26 | "Ara tatil (okul kapalı)" tatil türü + uyarı metinleri; tedbir "Uzat" ölü düğmesi; yanlış madde atıfları | ✅ |

## Faz 4 — Belgeler

| # | Değişiklik | Durum |
|---|---|---|
| 27 | CLAUDE.md: "PDF içeriği saklanmıyor" gerekçesi düzeltildi (PDF'ler şifreli alanda saklanıyor); yeni invariantlar | ✅ |
| 28 | `docs/teknik-borc.md`: K1 güncellendi; kalan kalemler M1-M8 | ✅ |

## Ertelenen kalemler (neden)

Ayrıntı `docs/teknik-borc.md` M1-M8. Özet:

- **M1 AYNEN şablon metinleri:** ✅ kapandı (26.09.2026) — Form-18, Form-15/17, Form-12 ve EK-1 kullanıcı kararlarıyla düzeltildi.
- **M2 eksik resmî belgeler:** yeni şablon + saha örneği gerekir.
- **M3 onur kurulu üyelik düşmesi/kompozisyon**, 
  **M5 imha zamanı ve yedekler**, **M8 onur kararı geri alma**:
  her biri ayrı ve dikkat isteyen iş.
- **M7 tedbir toplam süresi:** ✅ kapandı — okul yönetimi teyidiyle her uzatma ayrı
  süre (≤10 iş günü), en fazla iki kez; uzatma MEM onayı işaretlenmeden kaydedilmez.

## Okul yönetimi kararları (26.09.2026)

Ara tatilde uzaklaştırma araştırması ve kalan şablon metinleri için tek tek alınan kararlar:

1. **Ara tatil yasal sürelerde iş günü sayılır** (tedbir, itiraz, sevk): yönetmelik
   süreleri "iş günü" diye tanımlar; ara tatil resmî tatil değildir. Kod değişmedi.
2. **Uzaklaştırma başlangıcı okulun kapalı olduğu güne girilemez** (md. 172/1-a):
   mevcut ret davranışı korundu. Kod değişmedi.
3. **Form-18 metni kayıttan doldurulur:** itiraz eden (veli / 18 yaşını tamamlamış
   öğrenci / müdür), süre içi/dışı, tebliğ tarihi, onay makamı ve itiraz mercii
   (md. 197 sevkinde il kurulu, md. 169/4, 202/1-b). "Kesinleşmiştir" ifadesi
   kaldırıldı. Bu formda OYS paritesi bilinçli olarak bırakıldı.

4. **Form-15/17 "savunması alınmış" ifadesi kayda bağlandı:** yalnız dosya kütüğünde
   öğrencinin savunma tutanağı (Form-11) varsa basılır (md. 194/1); yoksa cümle
   "olayla ilgili bilgi ve belgeler incelenmiştir" diye sürer. Savunmayı elle yazdıysanız
   tutanağı kütüğe ekleyin (tek öğrencili dosyada öğrenci seçmeden eklenen de sayılır).

5. **Form-12 oylama esası seçilir:** süre uzatma tutanağı üretilirken "oy birliği /
   oy çoğunluğu" seçilir (md. 191/1); varsayılan oy birliği. Seçim DB'ye yazılmaz.

6. **EK-1 müdür onay kutusu:** "ceza verilmesine yer olmadığına" kararında da
   "YENİDEN GÖRÜŞÜLMESİ HUSUSUNDA (md. 197)" kutusu basılır; "onay ve itiraz
   gerektirmez (md. 191)" cümlesindeki atıf kaldırıldı.

7. **Şube harfi Türkçe saklanır (M6 kapandı):** "10/Ç" artık "10/C"ye katlanmaz;
   içe aktarma, elle giriş ve süzgeç aynı dönüşümü kullanır. Eski kayıtlar öğrenci
   listesi yeniden içe aktarılınca düzelir; eski "10/C" eşleştirme satırı elle silinir.

8. **md. 166 zorunlu kural (B):** öğrencinin aynı öğretim yılında yürürlükte cezası
   varsa ondan ağır olmayan ceza (kayıt veya düzenlemede) yalnız "md. 166 gerekçesi"
   yazılarak girilir; gerekçe karar kaydında kalır, evraka basılmaz. Cezasız karar ve
   üst kurulun itiraz/onay değişiklikleri kural dışıdır. Migrasyon: `disiplin 0007`.

9. **md. 168/5 (zihinsel engel/otizm) programa eklenmedi:** bilgi e-Okul/RAM kaydında;
   kurul kendisi dikkate alır. Özel nitelikli kişisel veri (KVKK md. 6) toplanmaz.

## Geçiş notları (kullanıcıya etkisi)

- Mevcut veritabanında **onaysız ama tebliğ edilmiş** kararlar artık "kesin"
  sayılmaz ve davranış puanı düşürmez; bu kararlar için onay durumunu (müdür /
  ilçe / il kurulu onay tarihi) girin.
- Kasım/nisan ara tatilini Ayarlar > Tatiller'den **"Ara tatil (okul kapalı)"**
  türüyle girin; yalnız uzaklaştırma günlerinde atlanır, yasal süreleri etkilemez.
- Migrasyonlar: `disiplin 0006_decision_legal_fields`, `disiplin 0007_decision_md166_override`,
  `okul 0005_holiday_school_break` (yalnız alan ekleme / seçenek; veri dönüştürmez).
