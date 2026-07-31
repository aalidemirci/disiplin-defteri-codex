// EK-1 anlatı alanları için akıllı şablon metinleri.
//
// Tur 149 (Talep 3 Faz C): tek "Kurul kanaati" şablonu. Tur 219 (talep 3): alan
// başına BİRDEN ÇOK seçilebilir varyant (NARRATIVE_TEMPLATES kayıt defteri) —
// farklı durumlar (ceza önerisi / alt ceza / ceza yok; ifade kabul / ret / kısmi…)
// için taslak iskeletler. OYS'nin bildiği veri (öğrenci adı, ceza türü, yönetmelik
// maddesi, olay tarihi) ön-doldurulur; kurul GÖRÜR ve DÜZENLER. Köşeli-parantez
// yer-tutucular elle doldurulur. Bu YASAL belge metnidir → son içerik/onay
// kurulundadır; şablon yalnız taslaktır. Varyant metinlerine madde numarası
// YAZILMAZ (yalnız statuteRef bağlamdan gelir) — yanlış atıf riski sıfırlanır.

import { formatDate } from "../../lib/format";
import type { DecisionNarrative } from "./api";

export interface DecisionTemplateContext {
  studentName: string;
  penaltyLabel: string; // ceza türü (penalty_type_display)
  statuteRef: string; // yönetmelik dayanağı (örn. "md. 164/1-c"), boş olabilir
  incidentDate: string; // ISO "YYYY-MM-DD" veya "" (olay tarihi)
}

// Geriye uyumlu takma ad (Tur 149 dış kullanımları kırılmasın).
export type CommitteeOpinionContext = DecisionTemplateContext;

export interface NarrativeTemplate {
  id: string;
  label: string;
  build: (ctx: DecisionTemplateContext) => string;
}

const ogrenci = (ctx: DecisionTemplateContext): string =>
  ctx.studentName.trim() || "[öğrencinin adı soyadı]";
const tarih = (ctx: DecisionTemplateContext): string =>
  ctx.incidentDate ? formatDate(ctx.incidentDate) : "…/…/……";
const madde = (ctx: DecisionTemplateContext): string => ctx.statuteRef.trim() || "[ilgili madde]";
const ceza = (ctx: DecisionTemplateContext): string => ctx.penaltyLabel.trim() || "[ceza türü]";

/** "Kurul kanaati" alanı için ön-dolu standart kanaat taslağı üretir (Tur 149). */
export function buildCommitteeOpinionTemplate(ctx: DecisionTemplateContext): string {
  return (
    `${ogrenci(ctx)} adlı öğrencinin ${tarih(ctx)} tarihinde gerçekleştirdiği [fiilin kısa tanımı] ` +
    `nedeniyle; alınan ifadeler, tanık beyanları ve dosyadaki diğer deliller birlikte ` +
    `değerlendirilmiştir. Öğrencinin savunması ile geçmiş hâl ve durumu göz önünde ` +
    `bulundurularak fiilin sübuta erdiği kanaatine varılmış; Millî Eğitim Bakanlığı ` +
    `Ortaöğretim Kurumları Yönetmeliği'nin ${madde(ctx)} maddesi uyarınca "${ceza(ctx)}" cezası ile ` +
    `cezalandırılmasının uygun olacağı sonucuna [oybirliği/oyçokluğu] ile ulaşılmıştır.`
  );
}

// Alan → seçilebilir şablon varyantları (Tur 219). Alan kayıt defterinde yoksa
// "Şablon" düğmesi görünmez; tek varyantta düğme doğrudan uygular.
export const NARRATIVE_TEMPLATES: Partial<Record<keyof DecisionNarrative, NarrativeTemplate[]>> = {
  committee_opinion: [
    { id: "opinion-penalty", label: "Ceza önerisi", build: buildCommitteeOpinionTemplate },
    {
      id: "opinion-lower-penalty",
      label: "Bir alt ceza",
      build: (ctx) =>
        `${ogrenci(ctx)} adlı öğrencinin ${tarih(ctx)} tarihinde gerçekleştirdiği ` +
        `[fiilin kısa tanımı] nedeniyle yapılan inceleme sonucunda fiilin sübuta erdiği ` +
        `kanaatine varılmıştır. Ancak öğrencinin savunması, pişmanlığı ve olumlu geçmiş ` +
        `hâli göz önünde bulundurularak, "${ceza(ctx)}" yerine bir alt ceza olan ` +
        `"[alt ceza türü]" ile cezalandırılmasının uygun olacağı sonucuna ` +
        `[oybirliği/oyçokluğu] ile ulaşılmıştır.`,
    },
    {
      id: "opinion-no-penalty",
      label: "Ceza tayinine yer yok",
      build: (ctx) =>
        `${ogrenci(ctx)} adlı öğrenci hakkında ${tarih(ctx)} tarihli olaya ilişkin alınan ` +
        `ifadeler, tanık beyanları ve dosyadaki deliller birlikte değerlendirilmiş; isnat ` +
        `edilen fiilin [sübuta ermediği / disiplin cezası gerektirir nitelikte olmadığı] ` +
        `kanaatine varılarak, hakkında ceza tayinine yer olmadığına karar verilmesinin ` +
        `uygun olacağı sonucuna [oybirliği/oyçokluğu] ile ulaşılmıştır.`,
    },
  ],
  accused_statement_summary: [
    {
      id: "accused-admits",
      label: "Kabul + pişmanlık",
      build: (ctx) =>
        `Öğrenci ifadesinde, ${tarih(ctx)} tarihli olaya konu fiili kabul etmiş; ` +
        `[olayın gelişimine ilişkin beyanı] ifade ederek pişmanlığını dile getirmiştir.`,
    },
    {
      id: "accused-denies",
      label: "Ret",
      build: () =>
        `Öğrenci ifadesinde, kendisine isnat edilen fiili kabul etmemiş; ` +
        `[olayın gelişimine ilişkin beyanı] şeklinde beyanda bulunmuştur.`,
    },
    {
      id: "accused-partial",
      label: "Kısmi kabul",
      build: () =>
        `Öğrenci ifadesinde fiilin [kabul edilen kısım] bölümünü kabul etmiş, ` +
        `[reddedilen kısım] yönünden isnadı reddetmiştir.`,
    },
  ],
  witness_statement_summary: [
    {
      id: "witness-consistent",
      label: "Doğrulayan tanıklar",
      build: () =>
        `Dinlenen tanıklar [tanık adları/sayısı], olayı esaslı noktalarda birbiriyle ` +
        `uyumlu biçimde doğrulamış; [öne çıkan ortak beyan] yönünde beyanda bulunmuştur.`,
    },
    {
      id: "witness-conflicting",
      label: "Çelişkili beyanlar",
      build: () =>
        `Dinlenen tanıkların beyanları arasında [çelişki noktası] yönünden farklılık ` +
        `bulunmakta olup beyanlar dosyadaki diğer delillerle birlikte değerlendirilmiştir.`,
    },
    {
      id: "witness-none",
      label: "Tanık yok",
      build: () =>
        `Olayın doğrudan görgü tanığı bulunmamaktadır; değerlendirme dosyadaki diğer ` +
        `bilgi ve belgelere dayanmaktadır.`,
    },
  ],
  other_evidence: [
    {
      id: "evidence-material",
      label: "Somut delil var",
      build: () =>
        `[Kamera kaydı / yazılı belge / mesaj dökümü] dosyaya alınmış ve kurulca ` +
        `incelenmiştir; söz konusu delil [olayla bağlantısı] yönünden değerlendirilmiştir.`,
    },
    {
      id: "evidence-statements-only",
      label: "Yalnız ifadeler",
      build: () => `İfade tutanakları dışında dosyada başkaca yazılı/görsel delil bulunmamaktadır.`,
    },
  ],
  mitigating_aggravating: [
    {
      id: "mitigating",
      label: "Hafifletici",
      build: () =>
        `Fiilin ilk kez işlenmesi, öğrencinin pişmanlığı ve olumlu geçmiş hâli ` +
        `hafifletici sebep olarak değerlendirilmiştir.`,
    },
    {
      id: "aggravating",
      label: "Ağırlaştırıcı",
      build: () =>
        `[Fiilin tekrarı / kasıtlı işlenmesi / sonuçlarının ağırlığı] ağırlaştırıcı ` +
        `sebep olarak değerlendirilmiştir.`,
    },
    {
      id: "neither",
      label: "Sebep yok",
      build: () => `Cezayı hafifletici veya ağırlaştırıcı bir sebep tespit edilmemiştir.`,
    },
  ],
};
