// EK-1 anlatı şablonları — Tur 149 tek kanaat şablonu + Tur 219 çoklu kayıt defteri.
// Kapsam: OYS verisi ön-dolu mu, boş alanlar köşeli-parantez yer-tutucuya düşüyor mu,
// kayıt defterinin şekli (alan başına ≥2 varyant, benzersiz id, ayırt edici kalıplar).

import { describe, expect, it } from "vitest";

import { formatDate } from "../../lib/format";
import { buildCommitteeOpinionTemplate, NARRATIVE_TEMPLATES } from "./decisionTemplates";
import type { DecisionTemplateContext } from "./decisionTemplates";

describe("buildCommitteeOpinionTemplate", () => {
  it("OYS verisini metne ön-doldurur (ad, olay tarihi, madde, ceza)", () => {
    const out = buildCommitteeOpinionTemplate({
      studentName: "Ali Veli",
      penaltyLabel: "Kınama",
      statuteRef: "md. 164/1-c",
      incidentDate: "2026-05-26",
    });
    expect(out).toContain("Ali Veli adlı öğrencinin");
    expect(out).toContain(`${formatDate("2026-05-26")} tarihinde`);
    expect(out).toContain("md. 164/1-c maddesi uyarınca");
    expect(out).toContain('"Kınama" cezası ile');
    expect(out).toContain("[oybirliği/oyçokluğu]");
  });

  it("boş alanlarda köşeli-parantez yer-tutucular kullanır", () => {
    const out = buildCommitteeOpinionTemplate({
      studentName: "",
      penaltyLabel: "",
      statuteRef: "  ",
      incidentDate: "",
    });
    expect(out).toContain("[öğrencinin adı soyadı]");
    expect(out).toContain("…/…/……");
    expect(out).toContain("[ilgili madde]");
    expect(out).toContain("[ceza türü]");
    expect(out).toContain("[fiilin kısa tanımı]");
  });
});

describe("NARRATIVE_TEMPLATES — çoklu şablon kayıt defteri (Tur 219)", () => {
  const FULL_CTX: DecisionTemplateContext = {
    studentName: "Ali Veli",
    penaltyLabel: "Kınama",
    statuteRef: "md. 164/1-c",
    incidentDate: "2026-05-26",
  };
  const EMPTY_CTX: DecisionTemplateContext = {
    studentName: "",
    penaltyLabel: "",
    statuteRef: "",
    incidentDate: "",
  };
  const entries = Object.entries(NARRATIVE_TEMPLATES);

  it("beklenen 5 alanı kapsar; her alanda ≥2 varyant; id'ler global benzersiz", () => {
    const keys = entries.map(([k]) => k).sort();
    expect(keys).toEqual([
      "accused_statement_summary",
      "committee_opinion",
      "mitigating_aggravating",
      "other_evidence",
      "witness_statement_summary",
    ]);
    const ids: string[] = [];
    for (const [, templates] of entries) {
      expect(templates!.length).toBeGreaterThanOrEqual(2);
      for (const t of templates!) {
        expect(t.label.trim()).not.toBe("");
        ids.push(t.id);
      }
    }
    expect(new Set(ids).size).toBe(ids.length);
  });

  it("her varyant boş ctx'te yer-tutucuya düşer, asla boş metin üretmez", () => {
    for (const [, templates] of entries) {
      for (const t of templates!) {
        const out = t.build(EMPTY_CTX);
        expect(out.trim().length).toBeGreaterThan(20);
        // Tarih/ad gerektiren şablonlar yer-tutucu basar; hiçbiri "undefined" sızdırmaz.
        expect(out).not.toContain("undefined");
      }
    }
  });

  it("kurul kanaati varyantları ayırt edici kalıplar taşır", () => {
    const opinions = NARRATIVE_TEMPLATES.committee_opinion!;
    expect(opinions[0].build(FULL_CTX)).toContain('"Kınama" cezası ile');
    expect(opinions.map((t) => t.id)).toEqual([
      "opinion-penalty",
      "opinion-lower-penalty",
      "opinion-no-penalty",
    ]);
    const lower = opinions[1].build(FULL_CTX);
    expect(lower).toContain("bir alt ceza");
    expect(lower).toContain("[alt ceza türü]");
    const none = opinions[2].build(FULL_CTX);
    expect(none).toContain("ceza tayinine yer olmadığına");
  });

  it("ifade özeti varyantları (kabul/ret/kısmi) ve tanık varyantları ayrışır", () => {
    const accused = NARRATIVE_TEMPLATES.accused_statement_summary!;
    expect(accused[0].build(FULL_CTX)).toContain("pişmanlığını");
    expect(accused[1].build(FULL_CTX)).toContain("kabul etmemiş");
    expect(accused[2].build(FULL_CTX)).toContain("[kabul edilen kısım]");
    const witness = NARRATIVE_TEMPLATES.witness_statement_summary!;
    expect(witness[2].build(FULL_CTX)).toContain("görgü tanığı bulunmamaktadır");
  });

  it("varyant metinlerine madde numarası gömülmez (yalnız ctx.statuteRef)", () => {
    // Yanlış atıf riski: sabit "md. NNN" yalnız kanaat şablonunda ctx'ten gelir.
    for (const [, templates] of entries) {
      for (const t of templates!) {
        const out = t.build(EMPTY_CTX);
        expect(out).not.toMatch(/md\.\s*\d/);
      }
    }
  });
});
