// Kurul Toplantı Tutanağı / Karar Defteri API katmanı — backend
// apps/disiplin/views.py (CouncilMeetingViewSet) 1:1 yansıması.
//
// OYS `modules/kurul/api.ts`'ten UYARLANDI (F4-D3). Sapmalar: `member_parent` yok
// (veli katılımcı yalnız ad snapshot'ı); okuma serializer'ı display türevlerini
// taşımaz (decision_basis_display/minutes_type_display/attendee_role_display/
// attendee_count/created_at yok — etiketler *_TR sabitlerinden, sayı
// attendees.length'ten); create gövdesi model-alan adlarını izler
// (`school_year`/`discipline_case` — çeviri BU dosyada, imza OYS adlarını korur);
// prefill düz liste döner (OYS `{attendees}` zarfı burada sarılır); case-options
// ögesi `{id, case_no, students}` (decision_count yok); ders yılları OYS
// `sistem/api` yerine buradaki `listSchoolYears`'tan (okul `/school-years/` ucu).

import { api } from "../../lib/api";
import { unwrap, type Paginated } from "../../lib/pagination";
import type { ActingChairOptions } from "../disiplin/api";
import type { HonorCertificate } from "../odul/api";

export type { ActingChairOptions, Paginated };

// --- TextChoices (backend models/council_meeting.py ile birebir) ---

export type CouncilType = "DISCIPLINE" | "HONOR";
export type HonorMeetingKind = "BOARD" | "GENERAL_ASSEMBLY";
export type DecisionBasis = "UNANIMITY" | "MAJORITY";
export type AttendeeRole = "VOTING_MEMBER" | "NON_VOTING_INVITEE";
export type MinutesType = "CASE_REVIEW" | "GENERAL";

// --- Türkçe etiketler ---

export const COUNCIL_TYPE_TR: Record<CouncilType, string> = {
  DISCIPLINE: "Ödül ve Disiplin Kurulu",
  HONOR: "Onur Kurulu",
};

export const MINUTES_TYPE_TR: Record<MinutesType, string> = {
  CASE_REVIEW: "Disiplin dosyası görüşme",
  GENERAL: "Diğer",
};

export const DECISION_BASIS_TR: Record<DecisionBasis, string> = {
  UNANIMITY: "Oy birliği",
  MAJORITY: "Oy çoğunluğu",
};

export const ATTENDEE_ROLE_TR: Record<AttendeeRole, string> = {
  VOTING_MEMBER: "Oy hakkı olan üye",
  NON_VOTING_INVITEE: "Oy hakkı olmayan davetli",
};

// --- Veri modelleri (serializers.py ile birebir) ---

export interface CouncilAttendee {
  id?: number;
  attendee_role: AttendeeRole;
  person_name: string;
  title: string;
  is_chair: boolean;
  dissent_note: string;
  order?: number;
  member_user?: number | null;
  member_student?: number | null;
}

export interface CouncilMeeting {
  id: number;
  school_year: number;
  school_term?: number | null;
  term_name?: string | null;
  council_type: CouncilType;
  council_type_display: string;
  meeting_no: number;
  meeting_no_display: string;
  meeting_date: string;
  honor_meeting_kind?: HonorMeetingKind;
  honor_meeting_kind_display?: string;
  agenda: string;
  decision_text: string;
  decision_basis: DecisionBasis;
  notes: string;
  minutes_type: MinutesType;
  discipline_case: number | null;
  discipline_case_no: string | null;
  // VEKÂLET KAYDI (S7, 14.11.2026 — yalnız Ödül ve Disiplin Kurulu): başkan katılmadı;
  // başkan işaretli katılımcı kurula başkanlık eden öğretmen üyedir (md. 188).
  chair_absent: boolean;
  attendees: CouncilAttendee[];
  // Kurul işleyişi (04.10.2026): kurul kararı gündem maddesinde verilir.
  agenda_items: AgendaItem[];
  // Ödül ve Disiplin Kurulu yeter sayısı (md. 191/1); Onur Kurulunda null.
  quorum: Quorum | null;
  // Kurulun md. 185/1 bileşim uyarıları (S5, 14.11.2026) — uyarır, engellemez; Onur
  // Kurulu toplantısında boş.
  composition_warnings?: string[];
  // VEKÂLET KAYDI uyarıları (S7) — uyarır, engellemez: başkan katılmadı ama yedek üye
  // çağrılmamış (md. 188) ya da dosya görüşme tutanağı dosya toplantısı kaydıyla çelişiyor.
  chair_warnings?: string[];
}

export type AgendaOutcome = "PENDING" | "FAVORABLE" | "UNFAVORABLE";

export interface AgendaItem {
  id: number;
  order: number;
  item_type: "HONOR_PROPOSAL";
  honor_certificate: number | null;
  student: number | null;
  student_name: string;
  class_label: string;
  criteria: string[];
  justification: string;
  proposer_role_display: string;
  certificate_status: string;
  // Öğrenci onur belgesine uygun mu (md. 161/1: davranış puanı indirilmemiş). S6,
  // 14.11.2026: `false` ise Onur Kurulu karar öncesi uyarılır; karar yine verilebilir.
  honor_eligible?: boolean | null;
  outcome: AgendaOutcome;
  outcome_display: string;
  decision_text: string;
  decision_basis: DecisionBasis;
  dissent_note: string;
}

export interface Quorum {
  full: number;
  required: number;
  present: number;
  ok: boolean;
  // "Oy hakkı olan üye" yazılmış ama kurul listesiyle eşleşmediği için yeter sayıya
  // girmeyen satırların adları (S13, 14.11.2026).
  unmatched?: string[];
  // "Başkan katılmadı" kayıtlı toplantıda kurulun BUGÜNKÜ başkanıyla eşleştiği (ve o gün üye
  // olduğu da gösterilemediği) için sayılmayan satırların adları (S7, 14.11.2026). Başkan
  // değişikliğinin geçmişi tutulmaz; satır sessizce düşmez, nedeniyle gösterilir.
  chair_skipped?: string[];
}

export interface AgendaDecisionBody {
  outcome: Exclude<AgendaOutcome, "PENDING">;
  decision_text?: string;
  decision_basis?: DecisionBasis;
  dissent_note?: string;
}

// Kurulun olumlu/olumsuz karar adı (md. 183/b uygun görüş; md. 161/1 kabul/ret).
export const OUTCOME_ACTION_TR: Record<CouncilType, { favorable: string; unfavorable: string }> = {
  HONOR: { favorable: "Uygun gör", unfavorable: "Uygun görme" },
  DISCIPLINE: { favorable: "Kabul et", unfavorable: "Reddet" },
};

/** Toplantıda karar bekleyen gündem maddesi var mı (açık toplantı). */
export function hasPendingItems(meeting: CouncilMeeting): boolean {
  return (meeting.agenda_items ?? []).some((item) => item.outcome === "PENDING");
}

// Panel "Müdür onayı bekleyenler" kartı.
export interface PrincipalPending {
  honor_certificates: {
    id: number;
    student_name: string;
    class_label: string;
    awarded_at: string | null;
  }[];
  decisions: {
    id: number;
    case: number;
    case_no: string;
    student_name: string;
    penalty_type_display: string;
    decision_no: string;
    decision_date: string;
  }[];
}

// Dosya görüşme tutanağına bağlanabilecek dosya seçeneği (kurula sevkli + kararlı).
export interface CaseOption {
  id: number;
  case_no: string;
  students: string[];
}

// Yeni katılımcı girdisi (form → backend council servisi katılımcı sözlüğü).
export interface AttendeeInput {
  attendee_role: AttendeeRole;
  person_name: string;
  title?: string;
  is_chair?: boolean;
  dissent_note?: string;
  order?: number;
  member_user_id?: number | null;
  member_student_id?: number | null;
}

export interface MeetingCreateBody {
  school_year_id: number;
  council_type: CouncilType;
  honor_meeting_kind?: HonorMeetingKind;
  meeting_date: string;
  agenda?: string;
  decision_text?: string;
  decision_basis?: DecisionBasis;
  notes?: string;
  minutes_type?: MinutesType;
  discipline_case_id?: number | null;
  attendees: AttendeeInput[];
  // Toplantı açılırken gündeme alınacak onur belgesi teklifleri.
  honor_certificate_ids?: number[];
  // VEKÂLET KAYDI (S7): başkan katılmadı (yalnız Ödül ve Disiplin Kurulu).
  chair_absent?: boolean;
}

// --- Ders yılları (okul modülü /school-years/ ucu) ---
// ToplantiForm aktif yılı buradan bulur. OYS'de `sistem/api.listSchoolYears` idi;
// bileşen sözleşmesi (`{school_years: [...]}` zarfı) korunur, çeviri burada.

export interface SchoolYear {
  id: number;
  name: string;
  start_date: string;
  end_date: string;
  is_active: boolean;
}

export async function listSchoolYears(): Promise<{ school_years: SchoolYear[] }> {
  const data = await api.get<Paginated<SchoolYear> | SchoolYear[]>("/school-years/?limit=200");
  return { school_years: unwrap(data) };
}

const BASE = "/council/meetings";

export const kurulApi = {
  listMeetings: async (councilType?: CouncilType): Promise<CouncilMeeting[]> => {
    const qs = new URLSearchParams({ limit: "200" });
    if (councilType) qs.set("council_type", councilType);
    const data = await api.get<Paginated<CouncilMeeting> | CouncilMeeting[]>(
      `${BASE}/?${qs.toString()}`,
    );
    return unwrap(data);
  },

  getMeeting: (id: number) => api.get<CouncilMeeting>(`${BASE}/${id}/`),

  // Tel anahtarı: FE `school_year_id`/`discipline_case_id` → backend model alanları
  // `school_year`/`discipline_case` (OYS bileşen sözleşmesi korunur).
  createMeeting: (body: MeetingCreateBody) => {
    const { school_year_id, discipline_case_id, ...rest } = body;
    return api.post<CouncilMeeting>(`${BASE}/`, {
      ...rest,
      school_year: school_year_id,
      discipline_case: discipline_case_id ?? null,
    });
  },

  deleteMeeting: (id: number) => api.del<void>(`${BASE}/${id}/`),

  // Katılımcı/metin düzeltmesi (tarih: karara bağlı madde varsa backend reddeder).
  updateMeeting: (
    id: number,
    body: Partial<{
      meeting_date: string;
      agenda: string;
      decision_text: string;
      decision_basis: DecisionBasis;
      notes: string;
      attendees: AttendeeInput[];
      // Verilmezse kayıtlı vekâlet durumu korunur (S7).
      chair_absent: boolean;
    }>,
  ) => api.patch<CouncilMeeting>(`${BASE}/${id}/`, body),

  // Gündeme alınmayı bekleyen onur belgesi teklifleri (Onur Kurulu: teklif aşaması;
  // Ödül ve Disiplin Kurulu: Onur Kurulunca uygun görülenler).
  agendaCandidates: (councilType: CouncilType) =>
    api.get<HonorCertificate[]>(`${BASE}/agenda-candidates/?council_type=${councilType}`),

  addAgendaItems: (meetingId: number, honorCertificateIds: number[]) =>
    api.post<CouncilMeeting>(`${BASE}/${meetingId}/agenda-items/`, {
      honor_certificate_ids: honorCertificateIds,
    }),

  removeAgendaItem: (meetingId: number, itemId: number) =>
    api.del<CouncilMeeting>(`${BASE}/${meetingId}/agenda-items/${itemId}/`),

  decideAgendaItem: (meetingId: number, itemId: number, body: AgendaDecisionBody) =>
    api.post<CouncilMeeting>(`${BASE}/${meetingId}/agenda-items/${itemId}/decide/`, body),

  principalPending: () => api.get<PrincipalPending>("/disiplin/mudur-onayi-bekleyenler/"),

  // Aktif kuruldan katılımcı taslağı (form ön-doldurma). Backend düz liste döner;
  // OYS bileşen sözleşmesi `{attendees: [...]}` zarfıdır — çeviri burada.
  prefill: async (
    councilType: CouncilType,
    honorMeetingKind: HonorMeetingKind = "BOARD",
  ): Promise<{ attendees: AttendeeInput[] }> => {
    const attendees = await api.get<AttendeeInput[]>(
      `${BASE}/prefill/?council_type=${councilType}&honor_meeting_kind=${honorMeetingKind}`,
    );
    return { attendees };
  },

  // Aktif Ödül ve Disiplin Kurulunun md. 185/1 bileşim uyarıları (S5, 14.11.2026) —
  // toplantı kaydı formu için. Kurul tanımsızsa (204, boş gövde) uyarı yoktur.
  compositionWarnings: async (): Promise<string[]> => {
    const committee = await api.get<{ composition_warnings?: string[] } | undefined>(
      "/discipline/committee/",
    );
    return committee?.composition_warnings ?? [];
  },

  // VEKÂLET KAYDI (S7): kurul başkanı, başkan seçilen dosyada şikâyetçi / zarar gören mi
  // (md. 191/2) ve kurula başkanlık edebilecek asıl öğretmen üyeler (md. 188). Kurul
  // tanımsızsa (204, boş gövde) null.
  actingChairOptions: async (caseId?: number | null): Promise<ActingChairOptions | null> => {
    const qs = caseId ? `?case=${caseId}` : "";
    const options = await api.get<ActingChairOptions | undefined>(
      `/discipline/committee/acting-chair-options/${qs}`,
    );
    return options ?? null;
  },

  // Dosya görüşme tutanağına bağlanabilecek dosyalar (kurula sevkli + kararlı).
  caseOptions: () => api.get<{ cases: CaseOption[] }>(`${BASE}/case-options/`),

  // Tutanak PDF (md. 206 imzalı) — blob.
  minutes: (id: number) => api.getBlob(`${BASE}/${id}/minutes/`),
};
