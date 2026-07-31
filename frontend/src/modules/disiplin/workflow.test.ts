// Disiplin süreç mantığı — saf fonksiyon testleri (OYS workflow.test.ts uyarlaması).
// caseSteps aşama rayı + nextStepFor eylem türetimi AYNEN; deriveCapabilities yerine
// ALL_CAPABILITIES sabiti pinlenir (tek kullanıcı → tüm yetenekler AÇIK).

import { describe, expect, it } from "vitest";

import { GENERATABLE_DOCUMENT_TYPES } from "./api";
import { ALL_CAPABILITIES, caseSteps, generatableTypesFor, nextStepFor } from "./workflow";
import type { CardAction, DisciplineCapabilities, WorkflowStep } from "./workflow";

const caps = (over: Partial<DisciplineCapabilities> = {}): DisciplineCapabilities => ({
  isAdmin: false,
  isMudur: false,
  isChair: false,
  isMemur: false,
  isRehber: false,
  ...over,
});

const statusOf = (steps: WorkflowStep[], key: string): string | undefined =>
  steps.find((s) => s.key === key)?.status;

const keysOf = (actions: CardAction[]): string[] => actions.map((a) => a.key);

describe("caseSteps — aşama rayı", () => {
  it("Dal B + DECIDED: müdür değ. 'done', kurul 'current'", () => {
    const steps = caseSteps("DECIDED", "B");
    expect(statusOf(steps, "decided")).toBe("done");
    expect(statusOf(steps, "committee")).toBe("current");
  });

  it("COMMITTEE_DONE: kurul 'current', müdür değ. 'done'", () => {
    const steps = caseSteps("COMMITTEE_DONE", "B");
    expect(statusOf(steps, "decided")).toBe("done");
    expect(statusOf(steps, "committee")).toBe("current");
  });

  it("Dal A: kurul adımı 'skipped'", () => {
    const steps = caseSteps("DECIDED", "A");
    expect(statusOf(steps, "committee")).toBe("skipped");
    expect(statusOf(steps, "decided")).toBe("current");
  });

  it("PETITION: dilekçe 'current'", () => {
    const steps = caseSteps("PETITION", null);
    expect(statusOf(steps, "petition")).toBe("current");
  });
});

describe("ALL_CAPABILITIES — tek kullanıcı sabiti", () => {
  it("tüm yetenekler AÇIK", () => {
    expect(Object.values(ALL_CAPABILITIES).every((v) => v === true)).toBe(true);
  });

  it("hepsi-true'da her aşamada sahip notu üretilmez, eylemler tam görünür", () => {
    const decidedB = nextStepFor("DECIDED", "B", ALL_CAPABILITIES);
    expect(decidedB.ownerNote).toBeUndefined();
    expect(keysOf(decidedB.actions)).toEqual(
      expect.arrayContaining(["committee", "docs", "periods"]),
    );
    const committeeDone = nextStepFor("COMMITTEE_DONE", "B", ALL_CAPABILITIES);
    expect(committeeDone.ownerNote).toBeUndefined();
    expect(keysOf(committeeDone.actions)).toEqual(expect.arrayContaining(["decision", "close"]));
  });
});

describe("nextStepFor — rol-duyarlı gövde (OYS paritesi; saf fonksiyon)", () => {
  it("DECIDED·B müdür: tedbir/süre var, kurul kararı girişi YOK", () => {
    const step = nextStepFor("DECIDED", "B", caps({ isMudur: true }));
    expect(keysOf(step.actions)).toContain("periods");
    expect(keysOf(step.actions)).not.toContain("committee");
    expect(step.ownerNote).toMatch(/kurul başkanı/i);
  });

  it("DECIDED·B başkan: kurul kararı girişi + evrak var, tedbir YOK", () => {
    const step = nextStepFor("DECIDED", "B", caps({ isChair: true }));
    expect(keysOf(step.actions)).toEqual(expect.arrayContaining(["committee", "docs"]));
    expect(keysOf(step.actions)).not.toContain("periods");
  });

  it("COMMITTEE_DONE müdür: onay/iade/itiraz var, kapatma YOK", () => {
    const step = nextStepFor("COMMITTEE_DONE", "B", caps({ isMudur: true }));
    expect(keysOf(step.actions)).toContain("decision");
    expect(keysOf(step.actions)).not.toContain("close");
  });

  it("DECIDED·A müdür: dosyayı kapat (Dal A'da başkan yok)", () => {
    const step = nextStepFor("DECIDED", "A", caps({ isMudur: true }));
    expect(keysOf(step.actions)).toContain("close");
  });

  it("rehber: GUIDANCE_REFERRED'de rapor eylemi görür", () => {
    const step = nextStepFor("GUIDANCE_REFERRED", null, caps({ isRehber: true }));
    expect(keysOf(step.actions)).toContain("report");
  });
});

describe("generatableTypesFor — Dal A belge filtresi", () => {
  it("Dal A: yalnız Form-02 + tedbir bildirimi listelenir", () => {
    const values = generatableTypesFor("A").map((t) => t.value);
    expect(values.sort()).toEqual(["PRECAUTION_NOTICE", "WARNING_LETTER"]);
  });

  it("Dal B ve dal-belirsiz (null): tam liste korunur", () => {
    expect(generatableTypesFor("B")).toEqual(GENERATABLE_DOCUMENT_TYPES);
    expect(generatableTypesFor(null)).toEqual(GENERATABLE_DOCUMENT_TYPES);
  });
});
