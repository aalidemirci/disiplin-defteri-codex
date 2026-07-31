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

export type { Paginated };

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
  attendees: CouncilAttendee[];
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

  // Dosya görüşme tutanağına bağlanabilecek dosyalar (kurula sevkli + kararlı).
  caseOptions: () => api.get<{ cases: CaseOption[] }>(`${BASE}/case-options/`),

  // Tutanak PDF (md. 206 imzalı) — blob.
  minutes: (id: number) => api.getBlob(`${BASE}/${id}/minutes/`),
};
