// Ödül/Onur (honor) modülü API katmanı — backend apps/disiplin/views.py
// (HonorBoardView + HonorCertificateViewSet + honor documents) 1:1 yansıması.
//
// OYS `modules/odul/api.ts`'ten UYARLANDI (F4-D3). Sapmalar (honors-lite, tasarım §4.2):
// teklif penceresi/kotası (proposal-window/proposal-quota/proposal-limit), toplu ret
// (reject-student), form teslim işareti (mark-delivered) ve çok-öğrencili teklif
// (certificates/batch) yüzeyleri standalone'da YOK → ilgili tipler + çağrılar kalktı;
// `SUPERSEDED` durumu ve `superseded_*`/`form_delivery_*`/`recommended_by`/
// `awarded_by_committee`/`teacher_proposal_limit`/`created_at` alanları serializer'da yok;
// `criteria_display` yerine yerel `criteriaDisplay()` (HONOR_CRITERION_TR'den);
// karar bağlamı rozetleri (has_active_discipline_penalty/total_absence/prior_honor_count)
// kalktı; `chair` → `okul.Personnel`, üye → `okul.Student` (member_user/member_parent yok);
// başkan atama PUT → POST; üye ekleme GÜNCEL KURULUN TAMAMINI döner; GET board 204 →
// `{board: null}` zarfı (disiplin/api.ts `getCommittee` deseni); kişi aramaları
// disiplin/api.ts'ten re-export (userLookupApi → personnelLookupApi). Tel anahtarları
// backend model-alan adlarını izler (`student`/`chair`/`school_year`); OYS bileşenlerinin
// BİREBİR taşınabilmesi için fonksiyon imzaları OYS adlarını (`student_id`…) korur,
// çeviri BU dosyada yapılır.

import { api } from "../../lib/api";
import { unwrap, type Paginated } from "../../lib/pagination";

export type { Paginated };

// --- TextChoices (backend models/honors.py ile birebir) ---

export type HonorCertificateStatus =
  | "PROPOSED"
  | "HONOR_BOARD_RECOMMENDED"
  | "AWARDED"
  | "PRINCIPAL_APPROVED"
  | "PRINCIPAL_REJECTED"
  | "REJECTED";

export type HonorProposerRole = "STUDENT" | "TEACHER" | "ADMINISTRATION";

export type HonorCriterion =
  | "LANGUAGE"
  | "ACHIEVEMENT"
  | "RESOURCES"
  | "MANNERS"
  | "TRAFFIC"
  | "IT"
  | "ATTENDANCE"
  | "SOCIAL_RESPONSIBILITY"
  | "SAFETY"
  | "OTHER";

// --- Türkçe etiketler ---

export const HONOR_STATUS_TR: Record<HonorCertificateStatus, string> = {
  PROPOSED: "Teklif edildi",
  HONOR_BOARD_RECOMMENDED: "Onur kurulu uygun gördü",
  AWARDED: "Ödül ve disiplin kurulu kabul etti",
  PRINCIPAL_APPROVED: "Okul müdürü onayladı",
  PRINCIPAL_REJECTED: "Okul müdürü onaylamadı",
  REJECTED: "Uygun görülmedi",
};

export const HONOR_PROPOSER_ROLE_TR: Record<HonorProposerRole, string> = {
  STUDENT: "Öğrenci",
  TEACHER: "Öğretmen",
  ADMINISTRATION: "Okul yönetimi",
};

// Onur belgesi kriterleri (md. 161/1 a-ğ + 161/2). Backend HonorCriterion ile birebir.
export const HONOR_CRITERION_TR: Record<HonorCriterion, string> = {
  LANGUAGE: "(a) Türkçeyi doğru, güzel ve etkili kullanarak örnek olmak",
  ACHIEVEMENT: "(b) Bilimsel/sosyal etkinliklerde liderlik ve üstün başarı",
  RESOURCES: "(c) Okul araç-gereci ve çevreyi koruma/gözetmede örneklik",
  MANNERS: "(ç) Görgü kuralları ve insan ilişkilerinde örneklik",
  TRAFFIC: "(d) Trafik kurallarına uymada örnek davranış",
  IT: "(e) Bilişim araçlarını kullanmada iyi örneklik",
  ATTENDANCE: "(f) Okula ve derslere düzenli devam, arkadaşlarına örneklik",
  SOCIAL_RESPONSIBILITY: "(g) Sosyal sorumluluk programı çalışmalarında görev almak",
  SAFETY: "(ğ) Sağlık ve güvenlik tedbirlerine uymada örneklik",
  OTHER: "Öğretmenler kurulunca belirlenen diğer davranış (md. 161/2)",
};

/** Kriter kodlarının Türkçe karşılıkları. Backend `criteria_display` türevini
 * DÖNDÜRMEZ (lite serializer) — OYS'nin o alanının yerel karşılığı budur. */
export function criteriaDisplay(criteria: readonly string[]): string[] {
  return criteria.map((code) => HONOR_CRITERION_TR[code as HonorCriterion] ?? code);
}

/** Tek bir dolu teklif formuna girecek teklifler + o formun imza adı. */
export interface ProposalFormGroup {
  proposerName: string;
  ids: number[];
}

/** Teklifleri teklif edene göre ayırır; her grup KENDİ formunu (kendi imzasıyla) alır.
 *
 * Resmî Onur Belgesi Teklif Formunun altında TEK imza satırı vardır ve backend açık ad
 * verilmediğinde listedeki İLK belgenin `proposer_name`'ini basar — farklı kişilerin
 * teklifleri tek forma konursa belge, teklif etmeyen kişiyi teklif sahibi gösterir.
 * Grupların ve grup içindeki id'lerin ilk görülme sırası korunur (form satır sırası). */
export function groupProposalsByProposer(
  proposals: readonly { id: number; proposer_name?: string }[],
): ProposalFormGroup[] {
  const groups = new Map<string, ProposalFormGroup>();
  for (const proposal of proposals) {
    const proposerName = (proposal.proposer_name ?? "").trim();
    const group = groups.get(proposerName);
    if (group) group.ids.push(proposal.id);
    else groups.set(proposerName, { proposerName, ids: [proposal.id] });
  }
  return [...groups.values()];
}

// --- Veri modelleri (serializers.py ile birebir) ---

export interface HonorBoardMember {
  id: number;
  member_student: number;
  member_name: string;
  grade_level: number | null;
  is_second_chair: boolean;
  is_substitute: boolean;
  order: number;
  title: string;
  assembly_member: number | null;
  effective_from: string;
  effective_until: string | null;
  end_reason: string;
  is_active: boolean;
}

export interface HonorBoard {
  id: number;
  school_year: number;
  chair: number | null;
  chair_name: string;
  substitute_chair: number | null;
  substitute_chair_name: string;
  notes: string;
  members: HonorBoardMember[];
}

export interface HonorGeneralAssemblyMember {
  id: number;
  school_year: number;
  member_student: number;
  member_name: string;
  class_level: number;
  class_section: string;
  effective_from: string;
  effective_until: string | null;
  end_reason: string;
  replaced_member: number | null;
  is_active: boolean;
}

export interface HonorComplianceMonth {
  year: number;
  month: number;
  label: string;
  meeting_count: number;
  complete: boolean;
}

export interface HonorComplianceTerm {
  term_id: number;
  sequence: number;
  name: string;
  assembly_meeting_count: number;
  assembly_complete: boolean;
  months: HonorComplianceMonth[];
}

export interface HonorCompliance {
  configured: boolean;
  terms: HonorComplianceTerm[];
}

export interface HonorCertificateEvent {
  id: number;
  event_type: string;
  event_date: string;
  school_term: number | null;
  term_name: string | null;
  meeting: number | null;
  explanation: string;
}

export interface HonorCertificate {
  id: number;
  student: number;
  student_name: string;
  school_year: number;
  school_term?: number | null;
  term_name?: string | null;
  status: HonorCertificateStatus;
  status_display: string;
  proposer_role: HonorProposerRole;
  proposer_role_display: string;
  proposer_name: string;
  criteria: HonorCriterion[];
  justification: string;
  recommended_at: string | null;
  awarded_at: string | null;
  principal_decided_at?: string | null;
  principal_decision_reason?: string;
  rejection_reason: string;
  rejected_at: string | null;
  events?: HonorCertificateEvent[];
}

// --- Form payload'ları ---

export interface HonorBoardCreateBody {
  school_year_id: number;
  chair_id: number;
  substitute_chair_id?: number | null;
  notes?: string;
}

export interface HonorBoardChairUpdateBody {
  chair_id: number;
}

export interface HonorBoardMemberCreateBody {
  student_id: number;
  grade_level?: number | null;
  is_second_chair?: boolean;
  is_substitute?: boolean;
  order?: number;
  title?: string;
  assembly_member_id?: number | null;
}

export interface HonorCertificateCreateBody {
  student_id: number;
  proposer_role: HonorProposerRole;
  // TEK kriter (e-Okul tek madde kuralı; backend tam olarak bir eleman ister — md. 161).
  criteria: HonorCriterion[];
  school_year_id?: number | null; // verilmezse aktif yıl
  school_term_id?: number;
  justification?: string;
  proposer_name?: string;
}

export interface HonorCertificateRecommendBody {
  recommended_on: string; // YYYY-MM-DD
}

export interface HonorCertificateAwardBody {
  awarded_on: string; // YYYY-MM-DD
}

export interface HonorCertificateRejectBody {
  reason: string;
  decided_on: string; // YYYY-MM-DD
}

export interface HonorPrincipalDecisionBody {
  decided_on: string;
  explanation?: string;
  reason?: string;
}

// --- API çağrıları ---

const BASE = "/honor";

export const odulApi = {
  // Onur kurulu (md. 180-184). Backend tekil obje döndürür; kurul tanımsızsa 204
  // (boş gövde). OYS bileşen sözleşmesi `{ board: ... | null }` zarfıdır — çeviri burada.
  getBoard: async (): Promise<{ board: HonorBoard | null }> => {
    const board = await api.get<HonorBoard | undefined>(`${BASE}/board/`);
    return { board: board ?? null };
  },

  // Tel anahtarı: FE `school_year_id`/`chair_id` → backend model alanları.
  createBoard: (body: HonorBoardCreateBody) =>
    api.post<HonorBoard>(`${BASE}/board/`, {
      school_year: body.school_year_id,
      chair: body.chair_id,
      ...(body.substitute_chair_id ? { substitute_chair: body.substitute_chair_id } : {}),
      ...(body.notes !== undefined ? { notes: body.notes } : {}),
    }),

  // Backend'de POST (OYS'de PUT idi); gövde model alanı `chair`.
  setBoardChair: (body: HonorBoardChairUpdateBody) =>
    api.post<HonorBoard>(`${BASE}/board/chair/`, { chair: body.chair_id }),

  setBoardSubstituteChair: (substituteChairId: number) =>
    api.post<HonorBoard>(`${BASE}/board/substitute-chair/`, {
      substitute_chair: substituteChairId,
    }),

  // Üye ekleme güncel kurulun TAMAMINI döner (OYS tek üye dönerdi).
  addBoardMember: (body: HonorBoardMemberCreateBody) => {
    const { student_id, ...rest } = body;
    return api.post<HonorBoard>(`${BASE}/board/members/`, { ...rest, student: student_id });
  },

  removeBoardMember: (memberId: number) => api.del<void>(`${BASE}/board/members/${memberId}/`),

  listGeneralAssemblyMembers: (schoolYearId?: number): Promise<HonorGeneralAssemblyMember[]> =>
    api.get<HonorGeneralAssemblyMember[]>(
      `${BASE}/general-assembly/${schoolYearId ? `?school_year=${schoolYearId}` : ""}`,
    ),

  addGeneralAssemblyMember: (body: {
    student_id: number;
    school_year_id?: number;
    effective_from?: string;
    replaced_member_id?: number | null;
  }): Promise<HonorGeneralAssemblyMember> =>
    api.post<HonorGeneralAssemblyMember>(`${BASE}/general-assembly/`, {
      student: body.student_id,
      ...(body.school_year_id ? { school_year: body.school_year_id } : {}),
      ...(body.effective_from ? { effective_from: body.effective_from } : {}),
      ...(body.replaced_member_id ? { replaced_member: body.replaced_member_id } : {}),
    }),

  endGeneralAssemblyMember: (
    memberId: number,
    body: { effective_until?: string; reason?: string },
  ): Promise<HonorGeneralAssemblyMember> =>
    api.post<HonorGeneralAssemblyMember>(`${BASE}/general-assembly/${memberId}/end/`, body),

  getHonorCompliance: (schoolYearId?: number): Promise<HonorCompliance> =>
    api.get<HonorCompliance>(
      `${BASE}/compliance/${schoolYearId ? `?school_year=${schoolYearId}` : ""}`,
    ),

  // Onur belgeleri (md. 161). Sunucu tarafı filtre (status/student/school_year) destekli;
  // liste sayfalıdır. Tel anahtarı: `student_id` → `student`.
  listCertificates: async (
    params: {
      status?: HonorCertificateStatus | "";
      studentId?: number;
      schoolYearId?: number;
      schoolTermId?: number;
    } = {},
  ): Promise<HonorCertificate[]> => {
    const qs = new URLSearchParams({ limit: "200" });
    if (params.status) qs.set("status", params.status);
    if (params.studentId) qs.set("student", String(params.studentId));
    if (params.schoolYearId) qs.set("school_year", String(params.schoolYearId));
    if (params.schoolTermId) qs.set("school_term", String(params.schoolTermId));
    const data = await api.get<Paginated<HonorCertificate> | HonorCertificate[]>(
      `${BASE}/certificates/?${qs.toString()}`,
    );
    return unwrap(data);
  },

  getCertificate: (id: number) => api.get<HonorCertificate>(`${BASE}/certificates/${id}/`),

  // Tel anahtarı: FE `student_id`/`school_year_id` → backend `student`/`school_year`.
  proposeCertificate: (body: HonorCertificateCreateBody) => {
    const { student_id, school_year_id, school_term_id, ...rest } = body;
    return api.post<HonorCertificate>(`${BASE}/certificates/`, {
      ...rest,
      student: student_id,
      ...(school_term_id !== undefined ? { school_term: school_term_id } : {}),
      ...(school_year_id !== undefined && school_year_id !== null
        ? { school_year: school_year_id }
        : {}),
    });
  },

  // Onur kurulu uygun görüşü (md. 183/b): PROPOSED → HONOR_BOARD_RECOMMENDED.
  recommendCertificate: (id: number, body: HonorCertificateRecommendBody) =>
    api.post<HonorCertificate>(`${BASE}/certificates/${id}/recommend/`, body),

  // Ödül-disiplin kurulu kararı (md. 161): RECOMMENDED → AWARDED.
  awardCertificate: (id: number, body: HonorCertificateAwardBody) =>
    api.post<HonorCertificate>(`${BASE}/certificates/${id}/award/`, body),

  principalApproveCertificate: (id: number, body: HonorPrincipalDecisionBody) =>
    api.post<HonorCertificate>(`${BASE}/certificates/${id}/principal-approve/`, body),

  principalRejectCertificate: (id: number, body: HonorPrincipalDecisionBody) =>
    api.post<HonorCertificate>(`${BASE}/certificates/${id}/principal-reject/`, body),

  // Uygun görülmedi (terminal red): PROPOSED|RECOMMENDED → REJECTED.
  rejectCertificate: (id: number, body: HonorCertificateRejectBody) =>
    api.post<HonorCertificate>(`${BASE}/certificates/${id}/reject/`, body),

  // Evrak (PDF blob): boş teklif formu (GET) + dolu teklif formu / teklif tutanağı (POST id'ler).
  proposalFormBlank: () => api.getBlob(`${BASE}/documents/proposal-form-blank/`),

  // `proposerName` verilirse imza satırına basılır (backend opsiyonel).
  proposalForm: (certificateIds: number[], proposerName?: string) =>
    api.postBlob(`${BASE}/documents/proposal-form/`, {
      certificate_ids: certificateIds,
      ...(proposerName !== undefined ? { proposer_name: proposerName } : {}),
    }),

  // Uygun görüş tutanağı: YALNIZ HONOR_BOARD_RECOMMENDED belgeler kabul edilir;
  // aksi halde backend 400 döner (mesaj kullanıcıya gösterilir).
  recommendationRecord: (certificateIds: number[]) =>
    api.postBlob(`${BASE}/documents/recommendation-record/`, {
      certificate_ids: certificateIds,
    }),

  // Nihai tutanak: belge verilenler (YALNIZ AWARDED) — ödül-disiplin kurulu kararı.
  awardRecord: (certificateIds: number[]) =>
    api.postBlob(`${BASE}/documents/award-record/`, { certificate_ids: certificateIds }),
};

// Kişi arama (öğrenci/personel) burada YOK: tek doğruluk kaynağı ../disiplin/api —
// paneller lookup'ları doğrudan oradan alır (OYS'deki yerel kopya kaldırıldı).
