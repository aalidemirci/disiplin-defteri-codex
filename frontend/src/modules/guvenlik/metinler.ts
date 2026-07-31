// Güvenlik arayüzünün DÜRÜST metinleri — tek kaynak (tasarım §6/§10.2).
// Kural: bu program "veritabanını şifreliyorum" DEMEZ. Şifrelenen şey belirli
// kişisel veri alanlarıdır; anahtar da aynı bilgisayarda durur. Kullanıcıya
// olduğundan güçlü bir koruma vadetmek, gerçek önlemi (tam disk şifreleme)
// almasını engellerdi.

/** Ayarlar ve kilit ekranında gösterilen kapsam açıklaması. */
export const KAPSAM_METNI =
  "Bu koruma, kayıtlardaki kişisel veri alanlarını (TCKN, telefon ve veli " +
  "bilgileri) parolanızdan türetilen bir anahtarla şifreler. TAM DİSK ŞİFRELEME " +
  "DEĞİLDİR: bilgisayarın tamamını korumak için Windows'ta BitLocker, " +
  "Pardus/Linux'ta LUKS kullanın.";

/** Şifrelenmeyen alanlar açıkça söylenir — sürpriz olmasın. */
export const KAPSAM_DISI_METNI =
  "Öğrenci ad-soyadı, okul numarası ve sınıf bilgisi arama ve listeleme için " +
  "şifrelenmez. Dosya ekleri (PDF/görsel) de şifrelenmez.";

/** Kurtarma anahtarı diyaloğunun uyarısı. */
export const KURTARMA_UYARISI =
  "Bu anahtar bir daha gösterilmez. Parolanızı unutursanız kayıtlara ERİŞMENİN " +
  "TEK YOLU budur. Yazdırın veya elle yazıp okul kasasında saklayın; " +
  "bilgisayarın kendisinde saklamayın.";

/** Parola kurma onayı. */
export const KURMA_UYARISI =
  "Parola konulduğunda mevcut kayıtlar şifrelenir. İşlem öncesi otomatik yedek " +
  "alınır ve birkaç saniye sürer; bu sırada programı kapatmayın.";

/** Parola kaldırma onayı. */
export const KALDIRMA_UYARISI =
  "Parola kaldırılınca kişisel veri alanları düz metne döner ve programı açan " +
  "herkes okuyabilir. İşlem öncesi otomatik yedek alınır.";

/** Yarım kalan geçiş uyarısı (elektrik kesintisi vb.). */
export const YARIM_GECIS_METNI =
  "Önceki güvenlik işlemi yarıda kalmış. Parolanızla açtığınızda kaldığı yerden " +
  "otomatik olarak tamamlanacaktır.";
