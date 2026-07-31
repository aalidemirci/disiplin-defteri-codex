> Not: OYS projesinden kopyalanmıştır; "OYS" referansları kaynak projeye aittir.

---
source: kanonik-metin
notebook: "—"
tarih: 2026-05-29
ilgili-modul: ogrenci_isleri
mevzuat-referansi:
  - "MEB Ortaöğretim Kurumları Yönetmeliği md. 185 — data/mevzuat/ortaogretim-kurumlari-yonetmeligi.md#madde-185"
  - "MEB Ortaöğretim Kurumları Yönetmeliği md. 186 — data/mevzuat/ortaogretim-kurumlari-yonetmeligi.md#madde-186"
  - "MEB Ortaöğretim Kurumları Yönetmeliği md. 188 — data/mevzuat/ortaogretim-kurumlari-yonetmeligi.md#madde-188"
  - "MEB Ortaöğretim Kurumları Yönetmeliği md. 191 — data/mevzuat/ortaogretim-kurumlari-yonetmeligi.md#madde-191"
  - "MEB Ortaöğretim Kurumları Yönetmeliği md. 192 — data/mevzuat/ortaogretim-kurumlari-yonetmeligi.md#madde-192"
etiketler: [disiplin, kurul, uye, yedek, baskan, rehberlik, sevk]
---

## Soru

> Okul öğrenci ödül ve disiplin kurulu kimlerden oluşur, başkanı kim, yedek üyeler
> nasıl belirlenir, rehberlik ve okul müdürünün disiplin sürecindeki rolü nedir?
> (OYS disiplin kurulu modeli — Tur 70 / Faz 3 dayanağı)

## Cevap (kanonik metinden özet)

Kaynak: kanonik tam metin (NotebookLM değil), bkz. mevzuat-referansi çapaları.

**Kurul kompozisyonu (md. 185/1):**
- (a) Müdürün görevlendireceği müdür yardımcısı → **kurul başkanı** (md. 188).
- (b) Öğretmenler kurulunca her ders yılının ilk ayında gizli oyla seçilen **iki öğretmen**.
- (c) Onur kurulu ikinci başkanı → **öğrenci üye**.
- (ç) Okul-aile birliğinin kendi üyeleri arasından seçeceği **bir öğrenci velisi** → **veli üye**.

**Başkan (md. 188):** Müdür yardımcısı başkandır. Başkan yoksa müdürün görevlendireceği
öğretmen üyelerden biri başkanlık eder; o durumda **yedek üye** toplantıya katılır.

**Yedek üyelik (md. 186):** Asıl üyelerden sonra oy sırasına göre **üç yedek üye**;
ayrıca onur kurulu üyeleri ile okul-aile birliği üyeleri arasından **birer yedek**.
Asıl üyelik boşalır/üye özürlü olursa sıraya göre yedekle doldurulur.

**Toplantı ve katılım (md. 185/6, 190, 191):**
- Kurul, üyelerin **salt çoğunluğuyla** toplanır, **oy çoğunluğuyla** karar alır.
- Genel (kişisel olmayan) disiplin toplantılarına rehberlik öğretmeni, onur kurulu
  başkanı, varsa okul doktoru katılır ama **oy kullanamaz** (md. 185/6).
- Başkan, görüş için sınıf rehber öğretmenini ve rehberlik öğretmenini toplantıya
  çağırabilir (md. 190).
- Disiplin konusundan **şikâyetçi veya zarar gören üye** kurula katılamaz; yerine
  yedek çağrılır (md. 191/2).

**Rehberlik + okul müdürü akışı (md. 192) — KRİTİK:**
- Disiplin konusu, rehberlik servisi olan okullarda **öncelikle rehberlik servisine**
  intikal eder.
- Rehberlik, öğrencinin **kişilik ve sosyal durumuna ilişkin raporu okul müdürüne** verir.
- **Okul müdürü** raporun içeriğini dikkate alarak **yönlendirmede bulunur** ve gerekli
  gördüğünde **kurul başkanını bilgilendirir**.
- "İfadelerin alınması ve delillerin toplanması" → md. 193.

**Süre (md. 192/3):** Kurul, konuyu **kurula gelişinden itibaren en geç on iş günü**
içinde karara bağlar; süre yetmezse ara karar + okul müdürünün onayıyla **bir kez**
uzatılabilir. (OYS'de Faz 6 yasal-süre işinin dayanağı.)

## Uygulama notları

OYS Tur 70 / Faz 3 tasarımına yansıması:
- **DisciplineCommittee** (ders yılı + `chair`=müdür yardımcısı) — md. 185(a)/188.
- **DisciplineCommitteeMember** (`member_type` TEACHER/STUDENT/PARENT, `is_substitute`)
  — md. 185(1) asıl + md. 186 yedek. Sayılar mevzuatla sabit değil tutulur (md. 185/5
  ikili öğretimde ayrı kurul; okul değişkenliği) — model esnek, doğrulama uyarı düzeyinde.
- **Toplantı katılımcısı** kurul üyelerinin alt kümesinden seçilir; oy hakkı olmayan
  davetliler (rehberlik/onur başkanı/doktor) ayrıca işaretlenebilir (md. 185/6, 190).
- **Rehber seçimi serbest** (md. 192 "okul müdürü yönlendirir") — öğrenci illa sınıf
  rehberine değil; OYS'de `assigned_guidance_id` zaten seçmeli.
- Faz 6: `savunma`/karar **10 iş günü** süresi (md. 192/3).
