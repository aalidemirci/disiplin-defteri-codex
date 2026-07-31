// Disiplin süreç modeli — aşama rayı + "sıradaki adım" türetimi.
// Backend state_machine.py akışını UI'da görselleştirir; backend'e dokunmaz.
// Dal A = yazılı uyarı (kurul yok), Dal B = onur/disiplin kuruluna sevk.
//
// OYS `modules/disiplin/workflow.ts`'ten UYARLANDI (F4-D1): caseBranch/caseSteps/
// nextStepFor/earlierStages/generatableTypesFor AYNEN; tek sapma deriveCapabilities —
// tek kullanıcılı/authsuz masaüstünde operatör tüm rolleri üstlenir, bu yüzden
// yetenekler `ALL_CAPABILITIES` sabitidir (rol/başkan eşlemesi yok). nextStepFor'un
// rol-duyarlı gövdesi bilerek korunur: sahip notları hepsi-true'da hiç tetiklenmez,
// eylemlerin tamamı görünür; OYS ile davranış farkı yalnız budur.

import { GENERATABLE_DOCUMENT_TYPES } from "./api";
import type { CaseStage, DisciplineEvent, GeneratableDocType } from "./api";

export type CaseBranch = "A" | "B" | null;

export const BRANCH_TR: Record<"A" | "B", string> = {
  A: "Dal A · uyarı",
  B: "Dal B · kurul",
};

/** DECIDED olayının müdür kararlarından dalı türetir. Karar yoksa null. */
export function caseBranch(events: DisciplineEvent[] | undefined): CaseBranch {
  if (!events) return null;
  const decided = events.find((e) => e.stage === "DECIDED");
  const pds = decided?.principal_decisions;
  if (!pds || pds.length === 0) return null;
  if (pds.includes("DISCIPLINE_COMMITTEE") || pds.includes("HONOR_COMMITTEE")) return "B";
  return "A"; // yalnız WRITTEN_WARNING
}

// Dal A (yalnız yazılı uyarı) dosyasında üretilebilir belge türleri: kurul formları
// (ifade/savunma/toplantı/EK-1/tebliğ/itiraz) kurul antedi + imza ızgarası
// bastığından Dal A dosyasında mevzuata aykırı görüntü oluşturur → listeden gizlenir.
// DECIDED öncesi (dal belirsiz) ve Dal B'de tam liste kalır. Dizi pusulası ayrı buton.
const BRANCH_A_DOC_TYPES: ReadonlySet<string> = new Set(["WARNING_LETTER", "PRECAUTION_NOTICE"]);

/** Dosyanın dalına göre üretilebilir belge türü listesi (yalnız UI filtresi). */
export function generatableTypesFor(branch: CaseBranch): GeneratableDocType[] {
  if (branch !== "A") return GENERATABLE_DOCUMENT_TYPES;
  return GENERATABLE_DOCUMENT_TYPES.filter((t) => BRANCH_A_DOC_TYPES.has(t.value));
}

export type StepStatus = "done" | "current" | "upcoming" | "skipped";

export interface WorkflowStep {
  key: string;
  label: string;
  icon: string;
  status: StepStatus;
}

const STAGE_ORDER: Record<CaseStage, number> = {
  PETITION: 0,
  GUIDANCE_REFERRED: 1,
  GUIDANCE_RETURNED: 2,
  DECIDED: 3,
  COMMITTEE_DONE: 4,
  CLOSED: 5,
};

/** Verilen aşamadan ÖNCEKİ (daha erken) aşamalar — aşama geri alma hedefleri.
 *  Backend `revert_stage` _STAGE_ORDER ile birebir; gerçek koruma backend'de. */
export function earlierStages(current: CaseStage): CaseStage[] {
  const ci = STAGE_ORDER[current];
  return (Object.keys(STAGE_ORDER) as CaseStage[]).filter((s) => STAGE_ORDER[s] < ci);
}

/**
 * Aşama rayı için 5 adımlık süreç durumu.
 * Rehberlik atlandıysa (events biliniyor + DECIDED'a rehberlik olmadan geçildi)
 * "skipped"; Dal A'da kurul adımı "skipped".
 */
export function caseSteps(
  currentStage: CaseStage,
  branch: CaseBranch,
  events?: DisciplineEvent[],
): WorkflowStep[] {
  const ci = STAGE_ORDER[currentStage];
  const hasGuidance = events?.some(
    (e) => e.stage === "GUIDANCE_REFERRED" || e.stage === "GUIDANCE_RETURNED",
  );
  const guidanceSkipped = ci >= STAGE_ORDER.DECIDED && events !== undefined && !hasGuidance;
  const committeeSkipped = branch === "A";
  // Dal B'de DECIDED aşaması müdürün kurula sevk kararıyla biter; kurul süreci
  // (ifade/savunma/toplantı/karar) backend'de hâlâ DECIDED altında yürür — ayrı
  // bir stage yok. Kullanıcı için aktif aşama artık "Kurul"dur; rayı "sıradaki
  // adım" metniyle (nextActionHint DECIDED+B) tutarlı kıl: müdür değ. bitti,
  // kurul yürürlükte.
  const committeeOngoing = currentStage === "DECIDED" && branch === "B";

  const step = (
    key: string,
    label: string,
    icon: string,
    stages: CaseStage[],
    skipped = false,
    forced?: StepStatus,
  ): WorkflowStep => {
    const maxIdx = Math.max(...stages.map((s) => STAGE_ORDER[s]));
    let status: StepStatus;
    if (forced) status = forced;
    else if (skipped) status = "skipped";
    else if (stages.includes(currentStage)) status = "current";
    else if (ci > maxIdx) status = "done";
    else status = "upcoming";
    return { key, label, icon, status };
  };

  return [
    step("petition", "Dilekçe", "description", ["PETITION"]),
    step(
      "guidance",
      "Rehberlik",
      "psychology",
      ["GUIDANCE_REFERRED", "GUIDANCE_RETURNED"],
      guidanceSkipped,
    ),
    step(
      "decided",
      "Müdür değ.",
      "gavel",
      ["DECIDED"],
      false,
      committeeOngoing ? "done" : undefined,
    ),
    step(
      "committee",
      "Kurul",
      "how_to_vote",
      ["COMMITTEE_DONE"],
      committeeSkipped,
      committeeOngoing ? "current" : undefined,
    ),
    step("closed", "Kapanış", "lock", ["CLOSED"]),
  ];
}

// --- Aktör yetenekleri + "sıradaki adım" ---
// OYS'de rol-duyarlı ekran: müdür yalnız müdür eylemlerini görür; kurul süreci
// eylemlerini atanmış kurul başkanı yürütür. Mevzuat: md. 196 (karar müdüre sunulur),
// md. 197 (müdür onaylar ya da gerekçeyle kurula iade eder — REDDEDEMEZ; kurul
// ısrar ederse ilçeye gönderir), md. 163/2 onay mercii, md. 169/3 tebliğ sonrası itiraz.

export interface DisciplineCapabilities {
  isAdmin: boolean;
  isMudur: boolean;
  /** OYS'de: giriş yapan, aktif ders yılı disiplin kurulunun atanmış başkanı mı? */
  isChair: boolean;
  isMemur: boolean;
  isRehber: boolean;
}

/** Tek kullanıcılı masaüstü: operatör tüm aktörleri üstlenir — yetenekler sabit AÇIK.
 *  (OYS `deriveCapabilities(roles, userId, chairUserId)` yerine geçer.) */
export const ALL_CAPABILITIES: DisciplineCapabilities = {
  isAdmin: true,
  isMudur: true,
  isChair: true,
  isMemur: true,
  isRehber: true,
};

export type DisciplineTab = "genel" | "taraflar" | "kurul" | "evraklar";

/** Kart eyleminin hedefi: aşama formu açar, sekmeye yönlendirir veya dosyayı kapatır. */
export type ActionKind =
  | { type: "stage"; stage: CaseStage }
  | { type: "tab"; tab: DisciplineTab }
  // Dosya kapatma özel uç (close_case): uygunluk geçidi + erken-kapatma override.
  // Aşama formundan ayrı.
  | { type: "close" };

export interface CardAction {
  key: string;
  label: string;
  icon: string;
  variant: "tonal" | "text";
  kind: ActionKind;
}

export interface NextStep {
  title: string;
  description: string;
  /** Hepsi-true yeteneklerde hiç üretilmez (OYS kalıntısı — bilerek korunur). */
  ownerNote?: string;
  actions: CardAction[];
}

const ACTIONS = {
  referGuidance: {
    key: "refer",
    label: "Rehberliğe sevk",
    icon: "psychology",
    variant: "tonal",
    kind: { type: "stage", stage: "GUIDANCE_REFERRED" },
  },
  guidanceReport: {
    key: "report",
    label: "Rehberlik raporu",
    icon: "psychology_alt",
    variant: "tonal",
    kind: { type: "stage", stage: "GUIDANCE_RETURNED" },
  },
  decide: {
    key: "decide",
    label: "Müdür değerlendirmesi / sevk",
    icon: "gavel",
    variant: "tonal",
    kind: { type: "stage", stage: "DECIDED" },
  },
  enterCommittee: {
    key: "committee",
    label: "Kurul kararı gir",
    icon: "how_to_vote",
    variant: "tonal",
    kind: { type: "stage", stage: "COMMITTEE_DONE" },
  },
  close: {
    key: "close",
    label: "Dosyayı kapat",
    icon: "lock",
    variant: "tonal",
    kind: { type: "close" },
  },
  goPeriods: {
    key: "periods",
    label: "Tedbir / süre işlemleri",
    icon: "block",
    variant: "tonal",
    kind: { type: "tab", tab: "kurul" },
  },
  goDecision: {
    key: "decision",
    label: "Karara git (onayla / iade / itiraz)",
    icon: "approval",
    variant: "tonal",
    kind: { type: "tab", tab: "kurul" },
  },
  goDocs: {
    key: "docs",
    label: "İfade/savunma/toplantı evrakı",
    icon: "folder",
    variant: "tonal",
    kind: { type: "tab", tab: "evraklar" },
  },
} satisfies Record<string, CardAction>;

/**
 * Güncel aşama + dal + aktör yeteneklerine göre "sıradaki adım" — başlık, açıklama
 * ve eylemler. OYS gövdesi AYNEN: uygulama daima `ALL_CAPABILITIES` geçirir
 * (tüm eylemler görünür); saf-fonksiyon rol dalları test edilebilirlik için durur.
 */
export function nextStepFor(
  stage: CaseStage,
  branch: CaseBranch,
  caps: DisciplineCapabilities,
): NextStep {
  const mudur = caps.isMudur || caps.isAdmin;
  const chair = caps.isChair || caps.isAdmin;
  const rehber = caps.isRehber || caps.isAdmin;

  switch (stage) {
    case "PETITION":
      return {
        title: "Sıradaki: rehberliğe sevk veya müdür değerlendirmesi",
        description:
          "Dilekçe alındı. Dosyayı rehberliğe sevk edin ya da doğrudan müdür değerlendirmesi/sevk kararını girin.",
        ownerNote: mudur ? undefined : "Bu adımı müdür yürütür.",
        actions: mudur ? [ACTIONS.referGuidance] : [],
      };
    case "GUIDANCE_REFERRED":
      return {
        title: "Sıradaki: rehberlik raporu",
        description: "Dosya rehberliğe sevk edildi. Rehber öğretmenin görüş/raporu bekleniyor.",
        ownerNote: rehber ? undefined : "Bu adımı rehber öğretmen yürütür.",
        actions: rehber ? [ACTIONS.guidanceReport] : [],
      };
    case "GUIDANCE_RETURNED":
      return {
        title: "Sıradaki: müdür değerlendirmesi / sevk",
        description:
          "Rehberlik tamamlandı. Müdür; uyarı, onur kuruluna veya disiplin kuruluna sevk kararını verir.",
        ownerNote: mudur ? undefined : "Bu adımı müdür yürütür.",
        actions: mudur ? [ACTIONS.decide] : [],
      };
    case "DECIDED":
      if (branch === "A")
        return {
          title: "Sıradaki: dosyayı kapatın",
          description: "Yazılı uyarı verildi; kurul süreci gerekmiyor. Dosya kapatılabilir.",
          ownerNote: mudur ? undefined : "Dosyayı müdür kapatır.",
          actions: mudur ? [ACTIONS.close] : [],
        };
      if (branch === "B")
        return {
          title: "Sıradaki: kurul süreci",
          description:
            "Kurula sevk edildi. İfade/savunma/toplantı çağrıları ve kurul kararı girilir; tedbir, süre uzatması onayı ve karar gelince onay/iade/itiraz işlemleri yapılır.",
          ownerNote: chair ? undefined : "Kurul kararını ve evrakı kurul başkanı yürütür.",
          actions: [
            ...(chair ? [ACTIONS.goDocs, ACTIONS.enterCommittee] : []),
            ...(mudur ? [ACTIONS.goPeriods] : []),
          ],
        };
      return {
        title: "Sıradaki: kurul süreci veya kapanış",
        description:
          "Müdür değerlendirmesi girildi. Karara göre kurul süreci yürütülür ya da dosya kapatılır.",
        actions: [],
      };
    case "COMMITTEE_DONE":
      return {
        title: "Sıradaki: müdür onayı / itiraz, sonra kapanış",
        description:
          "Kurul kararı müdür onayına sunuldu. Müdür onaylar (kınama/kısa süreli uzaklaştırma) ya da uygun bulmazsa gerekçeyle kurula iade eder; yetki dışı cezada üst mercie gönderir (md. 197). Onay ve tebliğden sonra dosya kapatılır.",
        ownerNote:
          mudur && chair
            ? undefined
            : mudur
              ? "Dosyayı kurul başkanı kapatır."
              : chair
                ? "Onay / iade / itiraz müdüre aittir."
                : "Onay müdüre, kapanış kurul başkanına aittir.",
        actions: [...(mudur ? [ACTIONS.goDecision] : []), ...(chair ? [ACTIONS.close] : [])],
      };
    case "CLOSED":
      return {
        title: "Dosya kapatıldı",
        description: "Süreç tamamlandı; yeni aşama eklenemez.",
        actions: [],
      };
  }
}
