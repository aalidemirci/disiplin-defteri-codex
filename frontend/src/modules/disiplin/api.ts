// Disiplin modülü API katmanı — backend apps/disiplin/views.py 1:1 yansıması.
//
// OYS `modules/disiplin/api.ts`'ten UYARLANDI (F4-D1). Sapmalar:
// - Rol/yetki yok (tek kullanıcı): limited görünüm kalktı, liste de tam alanları döner.
// - FK ikameleri (tasarım §4.2): `petitioner_parent` yok; `assigned_guidance` FK yerine
//   `assigned_guidance_name` (serbest metin — guidance-counselors ucu YOK);
//   `performed_by/uploaded_by/issued_by/generated_by` türevleri kalktı.
// - Tel anahtarları backend'in model-alan adlarını izler (`student`, `participant`,
//   `parent_document`, `committee_decision_type`); OYS bileşenlerinin (Dilim 2)
//   BİREBİR taşınabilmesi için fonksiyon imzaları OYS adlarını (`student_id`…)
//   korur, çeviri BU dosyada yapılır.
// - Liste ucu sunucu-taraflı filtre destekler (stage/search/student) — OYS'de
//   istemci-taraflıydı.

import { api } from "../../lib/api";
import { unwrap, type Paginated } from "../../lib/pagination";

export type { Paginated };

// --- TextChoices (backend models ile birebir) ---

export type CaseStage =
  "PETITION" | "GUIDANCE_REFERRED" | "GUIDANCE_RETURNED" | "DECIDED" | "COMMITTEE_DONE" | "CLOSED";

export type PetitionerRole = "OGRETMEN" | "VELI" | "OGRENCI" | "IDARE" | "DIGER";

export type PrincipalDecision = "WRITTEN_WARNING" | "HONOR_COMMITTEE" | "DISCIPLINE_COMMITTEE";

export type AttachmentType =
  "PETITION_SCAN" | "GUIDANCE_FORM" | "PRINCIPAL_DECISION" | "COMMITTEE_DECISION" | "OTHER";

// --- Veri modelleri ---

export interface CaseStudent {
  id: number;
  full_name: string;
  student_number: string;
  class_label: string;
}

export interface DisciplineAttachment {
  id: number;
  event: number | null;
  file_type: AttachmentType;
  file_type_display: string;
  original_filename: string;
  file_size_bytes: number;
  mime_type: string;
  sha256: string;
  uploaded_at: string;
}

export interface DisciplineEvent {
  id: number;
  stage: CaseStage;
  stage_display: string;
  event_date: string;
  recorded_at: string;
  notes: string;
  assigned_guidance_name: string; // GUIDANCE_REFERRED'da sevk edilen rehberin ad-soyadı
  guidance_outcome: string;
  principal_decisions: PrincipalDecision[] | null;
  committee_decision_type: number | null;
  committee_decision_type_name: string | null;
  committee_decision_text: string;
  is_override: boolean;
  override_reason: string;
}

// Liste + detay birleşimi: detay ekstra alanları (events/attachments/petitioner FK/
// kapanış uygunluğu) yalnız retrieve'de döner; liste tam künyeyi zaten içerir.
export interface DisciplineCase {
  id: number;
  case_no: string;
  petition_date: string;
  petitioner_name: string;
  petitioner_role: PetitionerRole;
  summary: string;
  current_stage: CaseStage;
  current_stage_display: string;
  closed_at: string | null;
  students: CaseStudent[];
  // Yalnız detay görünümünde:
  petitioner_user?: number | null;
  petitioner_student?: number | null;
  events?: DisciplineEvent[];
  attachments?: DisciplineAttachment[];
  // Dosya elle kapatılabilir mi + en erken uygun gün (yalnız detay; md. 169/171).
  close_eligible?: boolean | null;
  close_eligible_on?: string | null;
  close_eligible_reason?: string;
}

export interface DisciplineDecisionType {
  id: number;
  code: string;
  name: string;
  description: string;
  is_active: boolean;
  sort_order: number;
}

// --- Form payload'ları ---

export interface DisciplineCaseCreateBody {
  petition_date: string; // ISO date (YYYY-MM-DD)
  petitioner_name: string;
  petitioner_role: PetitionerRole;
  summary: string;
  student_ids: number[];
  // Role'a göre opsiyonel FK (personel/öğrenci autocomplete'ten seçilen).
  petitioner_user_id?: number | null;
  petitioner_student_id?: number | null;
}

export interface DisciplineCasePatchBody {
  petition_date?: string;
  petitioner_name?: string;
  petitioner_role?: PetitionerRole;
  summary?: string;
}

export interface DisciplineEventCreateBody {
  stage: CaseStage;
  event_date: string; // YYYY-MM-DD
  notes?: string;
  assigned_guidance_name?: string; // GUIDANCE_REFERRED zorunlu (serbest metin)
  guidance_outcome?: string; // GUIDANCE_RETURNED zorunlu
  principal_decisions?: PrincipalDecision[]; // DECIDED zorunlu (en az 1)
  committee_decision_type_id?: number | null; // COMMITTEE_DONE zorunlu
  committee_decision_text?: string; // COMMITTEE_DONE zorunlu
  override?: boolean;
  override_reason?: string; // override=true ise zorunlu
}

export interface DecisionTypeCreateBody {
  code: string;
  name: string;
  description?: string;
  is_active?: boolean;
  sort_order?: number;
}

// --- Türkçe etiketler ---

export const STAGE_TR: Record<CaseStage, string> = {
  PETITION: "Dilekçe alındı",
  GUIDANCE_REFERRED: "Rehberliğe sevk",
  GUIDANCE_RETURNED: "Rehberlikten döndü",
  DECIDED: "Müdür değerlendirmesi / sevk",
  COMMITTEE_DONE: "Kurul kararı",
  CLOSED: "Kapatıldı",
};

export const PETITIONER_TR: Record<PetitionerRole, string> = {
  OGRETMEN: "Öğretmen",
  VELI: "Veli",
  OGRENCI: "Öğrenci",
  IDARE: "İdare",
  DIGER: "Diğer",
};

export const PRINCIPAL_DECISION_TR: Record<PrincipalDecision, string> = {
  WRITTEN_WARNING: "Yazılı uyarı",
  HONOR_COMMITTEE: "Onur Kuruluna sevk",
  DISCIPLINE_COMMITTEE: "Disiplin Kuruluna sevk",
};

export const ATTACHMENT_TYPE_TR: Record<AttachmentType, string> = {
  PETITION_SCAN: "Dilekçe taraması",
  GUIDANCE_FORM: "Rehberlik formu",
  PRINCIPAL_DECISION: "Müdür değerlendirme/sevk belgesi",
  COMMITTEE_DECISION: "Kurul kararı belgesi",
  OTHER: "Diğer",
};

// =============================================================================
// Disiplin kurulu tanımı. serializers.py ile birebir. Veli üyeler FK'sız
// `member_name` snapshot'ı ile tutulur (tasarım §4.2 — veli sicili yok).
// =============================================================================

export type CommitteeMemberType = "TEACHER" | "STUDENT" | "PARENT";

export const COMMITTEE_MEMBER_TYPE_TR: Record<CommitteeMemberType, string> = {
  TEACHER: "Öğretmen",
  STUDENT: "Öğrenci",
  PARENT: "Veli",
};

export interface CommitteeMember {
  id: number;
  member_type: CommitteeMemberType;
  member_type_display: string;
  is_substitute: boolean;
  order: number;
  title: string;
  member_name: string;
  member_user: number | null;
  member_student: number | null;
}

export interface DisciplineCommittee {
  id: number;
  school_year: number;
  chair: number | null;
  chair_name: string;
  notes: string;
  members: CommitteeMember[];
}

export interface DisciplineMeeting {
  id: number;
  event: number | null;
  meeting_date: string;
  notes: string;
  attendees: number[]; // kurul üyesi id'leri
  attendee_names: string[];
}

// --- Kurul form payload'ları ---

export interface CommitteeCreateBody {
  school_year_id: number;
  chair_id: number;
  notes?: string;
}

export interface CommitteeChairUpdateBody {
  chair_id: number;
}

export interface CommitteeMemberCreateBody {
  member_type: CommitteeMemberType;
  person_id?: number | null; // TEACHER/STUDENT zorunlu
  member_name?: string; // PARENT zorunlu (snapshot; veli sicili yok)
  is_substitute?: boolean;
  order?: number;
  title?: string;
}

export interface MeetingCreateBody {
  meeting_date: string; // YYYY-MM-DD
  attendee_member_ids: number[];
  notes?: string;
}

// =============================================================================
// Rollü katılımcı + müdür uyarısı + triaj. serializers.py / models ile birebir.
// =============================================================================

export type ParticipantRole = "ACCUSED" | "VICTIM" | "WITNESS";
export type ParticipantPersonType = "STUDENT" | "STAFF" | "EXTERNAL";

export const PARTICIPANT_ROLE_TR: Record<ParticipantRole, string> = {
  ACCUSED: "Hakkında İşlem Yapılan",
  VICTIM: "Mağdur",
  WITNESS: "Tanık",
};

export const PARTICIPANT_PERSON_TYPE_TR: Record<ParticipantPersonType, string> = {
  STUDENT: "Öğrenci",
  STAFF: "Personel",
  EXTERNAL: "Dış kişi",
};

export interface DisciplineParticipant {
  id: number;
  role: ParticipantRole;
  role_display: string;
  person_type: ParticipantPersonType;
  person_type_display: string;
  student: number | null;
  user: number | null;
  external_name: string;
  external_title: string;
  name_snapshot: string;
  notes: string;
}

export interface ParticipantCreateBody {
  role: ParticipantRole;
  person_type: ParticipantPersonType;
  person_id?: number | null; // STUDENT/STAFF zorunlu
  external_name?: string; // EXTERNAL zorunlu
  external_title?: string;
  notes?: string;
}

export interface DisciplineWarning {
  id: number;
  student: number;
  student_name: string;
  warning_date: string;
  summary: string;
}

export interface WarningCreateBody {
  student_id: number;
  warning_date: string; // YYYY-MM-DD
  summary: string;
}

// Triaj önerisi (md. 157/7, 166): suçlanan öğrenci başına geçmiş + kurul önerisi.
export interface TriageStudent {
  student_id: number;
  warning_count: number;
  penalty_count: number;
  should_route_to_committee: boolean;
}

export interface TriageSuggestion {
  students: TriageStudent[];
  should_route_to_committee: boolean;
}

// =============================================================================
// Resmî karar + itiraz + EK-1 anlatı. serializers.py / models ile birebir. md. 163-172.
// =============================================================================

export type PenaltyType =
  "REPRIMAND" | "SHORT_TERM_SUSPENSION" | "SCHOOL_CHANGE" | "EXPULSION" | "NO_PENALTY";

export type ApprovalAuthority = "PRINCIPAL" | "DISTRICT_BOARD" | "PROVINCIAL_BOARD" | "UPPER_BOARD";

export type DecisionApprovalStatus = "PENDING" | "APPROVED" | "RETURNED" | "REFERRED" | "REJECTED";

export type AppealFiledByRole = "PRINCIPAL" | "STUDENT_ADULT" | "PARENT";

export type AppealResult = "PENDING" | "UPHELD" | "REDUCED" | "OVERTURNED";

export const PENALTY_TYPE_TR: Record<PenaltyType, string> = {
  REPRIMAND: "Kınama",
  SHORT_TERM_SUSPENSION: "Okuldan kısa süreli uzaklaştırma",
  SCHOOL_CHANGE: "Okul değiştirme",
  EXPULSION: "Örgün eğitim dışına çıkarma",
  // Kurul ceza vermek zorunda değil (md. 191); davranış puanı 0.
  NO_PENALTY: "Ceza verilmesine yer olmadığı",
};

export const APPROVAL_AUTHORITY_TR: Record<ApprovalAuthority, string> = {
  PRINCIPAL: "Okul müdürü",
  DISTRICT_BOARD: "İlçe öğrenci disiplin kurulu",
  PROVINCIAL_BOARD: "İl öğrenci disiplin kurulu",
  UPPER_BOARD: "Öğrenci üst disiplin kurulu",
};

export const DECISION_APPROVAL_STATUS_TR: Record<DecisionApprovalStatus, string> = {
  PENDING: "Onay bekliyor",
  APPROVED: "Onaylandı",
  RETURNED: "Kurula iade edildi",
  REFERRED: "İlçe kuruluna gönderildi",
  REJECTED: "Kaldırıldı (itiraz bozdu)",
};

export const APPEAL_FILED_BY_ROLE_TR: Record<AppealFiledByRole, string> = {
  PRINCIPAL: "Okul müdürü",
  STUDENT_ADULT: "Öğrenci (18 yaşını tamamlamış)",
  PARENT: "Veli",
};

export const APPEAL_RESULT_TR: Record<AppealResult, string> = {
  PENDING: "İnceleniyor",
  UPHELD: "Onandı (ceza aynen)",
  REDUCED: "Hafifletildi/değiştirildi",
  OVERTURNED: "Bozuldu (ceza kaldırıldı)",
};

export interface DisciplineAppeal {
  id: number;
  decision: number;
  filed_on: string;
  filed_by_role: AppealFiledByRole;
  filed_by_name: string;
  within_deadline: boolean;
  appeal_authority: ApprovalAuthority;
  appeal_authority_display: string;
  forward_deadline: string | null;
  forwarded_on: string | null;
  result: AppealResult;
  result_display: string;
  resulted_on: string | null;
  result_notes: string;
}

// EK-1 anlatı alanları (md. 168 takdir + md. 193 ifade/delil).
export interface DecisionNarrative {
  accused_statement_summary: string;
  witness_statement_summary: string;
  other_evidence: string;
  mitigating_aggravating: string;
  committee_opinion: string;
  psychosocial_summary: string;
  // EK-1 öğrenci-bağlam alanları — resmî EK-1 "ÖĞRENCİNİN" bloğu (serbest metin).
  boarding_status: string;
  academic_standing: string;
  health_status: string;
  family_economic_status: string;
  lives_with_family: string;
  parents_alive: string;
  parents_biological: string;
  studies_near_family: string;
  upbringing_environment: string;
  family_residence_area: string;
  incident_place: string;
  prior_penalties_summary: string;
}

export interface DisciplineDecision extends DecisionNarrative {
  id: number;
  student: number;
  student_name: string;
  event: number | null;
  meeting: number | null;
  penalty_type: PenaltyType;
  penalty_type_display: string;
  statute_ref: string;
  penalty_detail: string;
  decision_no: string;
  decision_date: string;
  suspension_days: number | null;
  enforcement_start_date: string | null; // uzaklaştırma uygulama başlangıcı (md. 164/2)
  incident_date: string | null; // EK-1: davranışın yapıldığı tarih
  behavior_point_deduction: number;
  approval_authority: ApprovalAuthority;
  approval_authority_display: string;
  approval_status: DecisionApprovalStatus;
  approval_status_display: string;
  approved_at: string | null;
  // md. 197 — kurula iade / ilçeye sevk gerekçesi + tarihi (RETURNED/REFERRED durumları).
  return_reason: string;
  returned_at: string | null;
  notified_at: string | null;
  notification_method: string;
  appeal_deadline: string | null;
  e_school_processed_on?: string | null;
  is_enforced: boolean;
  // Karar kesinleşti mi (md. 169/3-4; backend decision_is_final):
  // e-Okul uyarı rozeti + Form-16/17 üretim kilidi UI ipucu.
  is_final: boolean;
  // Sicildeki doğum tarihi — EK-1 anlatı formunda prefill.
  student_birth_date: string | null;
  notes: string;
  deleted_at: string | null;
  appeals: DisciplineAppeal[];
}

// GET cases/<id>/decisions/ → kararlar + öğrenci başına davranış puanı (md. 170).
export interface DecisionsResponse {
  decisions: DisciplineDecision[];
  behavior_points: Record<number, number>;
}

export interface DecisionCreateBody {
  student_id: number;
  penalty_type: PenaltyType;
  decision_date: string; // YYYY-MM-DD
  suspension_days?: number | null; // yalnız kısa süreli uzaklaştırma (1-5)
  enforcement_start_date?: string | null; // uzaklaştırma uygulama başlangıcı (md. 164/2)
  statute_ref?: string;
  penalty_detail?: string;
  decision_no?: string;
  notes?: string;
}

// Karar düzenleme gövdesi (yalnız PENDING; öğrenci bağı değişmez).
export type DecisionEditBody = Omit<DecisionCreateBody, "student_id">;

// Aşama geri alma gövdesi (seçilen daha erken aşamaya).
export interface StageRevertBody {
  target_stage: CaseStage;
  reason: string;
}

export interface CaseCloseBody {
  // Erken kapatma (uygunluk geçidini atla) — gerekçe zorunlu (backend zorlar).
  override?: boolean;
  override_reason?: string;
}

export interface DecisionApprovalBody {
  approval_status: DecisionApprovalStatus;
  approved_on?: string | null;
}

// md. 197 — müdürün kurula iade (RETURN) / ilçeye sevk (REFER) girdisi.
export interface DecisionReviewBody {
  action: "RETURN" | "REFER";
  reason: string;
  decided_on: string; // YYYY-MM-DD
}

export interface DecisionNotifyBody {
  notified_on: string;
  notification_method?: string;
}

export interface DecisionESchoolBody {
  processed_on: string;
}

// Tüm alanlar opsiyonel (kısmi güncelleme; backend whitelist). Uzaklaştırma uygulama
// başlangıcı (md. 164/2) da bu uçtan post-hoc set/temizlenebilir.
export type DecisionNarrativeBody = Partial<DecisionNarrative> & {
  enforcement_start_date?: string | null;
  incident_date?: string | null; // EK-1: davranışın yapıldığı tarih
  // Karara değil öğrenci SİCİLİNE yazılır (okul.update_student);
  // null/gönderilmemiş → sicile dokunulmaz.
  student_birth_date?: string | null;
};

export interface AppealCreateBody {
  filed_on: string;
  filed_by_role: AppealFiledByRole;
  filed_by_name?: string;
}

export interface AppealForwardBody {
  forwarded_on: string;
}

export interface AppealResolveBody {
  result: AppealResult;
  resulted_on: string;
  result_notes?: string;
}

// =============================================================================
// Kurul karar süresi + uzatma + tedbir. serializers.py / models ile birebir.
// md. 175, 192/3.
// =============================================================================

export interface DisciplineDeadlineExtension {
  id: number;
  requested_days: number;
  reason: string;
  decided_on: string;
  approved_by_principal: boolean;
  approved_on: string | null;
  original_deadline: string | null;
  new_deadline: string | null;
  notes: string;
}

// GET cases/<id>/extensions/ → uzatmalar + kurula geliş/karar son günü izleme (md. 192/3).
export interface ExtensionsResponse {
  extensions: DisciplineDeadlineExtension[];
  committee_referred_on: string | null;
  committee_decision_deadline: string | null;
}

export interface ExtensionCreateBody {
  requested_days: number;
  reason: string;
  decided_on: string; // YYYY-MM-DD
  notes?: string;
}

export interface ExtensionApproveBody {
  approved_on: string;
}

export type PrecautionStatus = "ACTIVE" | "LIFTED" | "EXPIRED";

export const PRECAUTION_STATUS_TR: Record<PrecautionStatus, string> = {
  ACTIVE: "Yürürlükte",
  LIFTED: "Kaldırıldı",
  EXPIRED: "Kendiliğinden kalktı",
};

export interface DisciplinePrecaution {
  id: number;
  student: number;
  student_name: string;
  event: number | null;
  start_date: string;
  requested_days: number;
  end_date: string | null;
  process_start_deadline: string | null;
  mne_notified: boolean;
  extension_count: number;
  status: PrecautionStatus;
  status_display: string;
  lifted_on: string | null;
  reason: string;
  notes: string;
}

export interface PrecautionCreateBody {
  student_id: number;
  start_date: string; // YYYY-MM-DD
  requested_days: number; // 1-10 (md. 175/1)
  reason?: string;
  mne_notified?: boolean;
  notes?: string;
}

export interface PrecautionLiftBody {
  lifted_on: string;
  expired?: boolean; // true → kendiliğinden kalktı (EXPIRED), aksi LIFTED
}

export interface PrecautionExtendBody {
  additional_days: number; // 1-9 (toplam ≤ 10, en fazla 2 kez)
  mne_notified?: boolean;
}

// =============================================================================
// Evrak üretimi + kütük zaman çizelgesi. serializers.py / models / documents.py
// ile birebir.
// =============================================================================

export type DocumentType =
  | "STATEMENT_CALL"
  | "STATEMENT_RECORD"
  | "INFO_GATHERING"
  | "DEFENSE_CALL"
  | "DEFENSE_RECORD"
  | "MEETING_CALL"
  | "DEADLINE_EXTENSION"
  | "COMMITTEE_DECISION"
  | "INDEX_SHEET"
  | "PENALTY_NOTICE"
  | "PENALTY_DAYS_NOTICE"
  | "APPEAL_LETTER"
  | "WARNING_LETTER"
  | "PRECAUTION_NOTICE"
  | "BOARD_DECISION_NOTICE"
  | "OTHER";

// Tüm belge türleri → Türkçe etiket (backend DocumentType ile birebir). Manuel belge
// ekleme + kütük gösterimi için (üretilemeyen türler de dahil).
export const ALL_DOCUMENT_TYPES_TR: Record<DocumentType, string> = {
  STATEMENT_CALL: "İfadeye çağrı pusulası (Form-3)",
  STATEMENT_RECORD: "İfade tutanağı (Form-4/5/6)",
  INFO_GATHERING: "Bilgi toplama formu (Form-7/8)",
  DEFENSE_CALL: "Savunmaya çağrı (Form-9)",
  DEFENSE_RECORD: "Savunma tutanağı (Form-11)",
  MEETING_CALL: "Kurul toplantı çağrısı (Form-10)",
  DEADLINE_EXTENSION: "Süre uzatma (Form-12/13)",
  COMMITTEE_DECISION: "Kurul kararı (EK-1)",
  INDEX_SHEET: "Dizi pusulası",
  PENALTY_NOTICE: "Ceza/Karar tebliği (Form-14/15)",
  PENALTY_DAYS_NOTICE: "Ceza günleri tebliği (Form-16/17)",
  APPEAL_LETTER: "İl/İlçe itiraz yazısı (Form-18)",
  WARNING_LETTER: "Müdür uyarısı yazısı (Form-01/02)",
  PRECAUTION_NOTICE: "Tedbir bildirimi (md. 175)",
  BOARD_DECISION_NOTICE: "Üst kurul kararı tebliği (md. 169/2-4)",
  OTHER: "Diğer",
};

// Üretilen/yazdırılan bir disiplin belgesinin kütük kaydı.
// PDF içeriği bu JSON'a konmaz; yalnız kopya varlığı/boyutu bildirilir.
export interface GeneratedDocument {
  id: number;
  student: number | null;
  document_type: DocumentType;
  document_type_display: string;
  title: string;
  document_no: string;
  // "Kimden" snapshot — ifade/savunma: rol (Hakkında İşlem Yapılan/Mağdur/Tanık);
  // bilgi alma: kaynak (Rehberlik Servisi/…). Dizi pusulasında görünür.
  source_label: string;
  source_name: string;
  generated_on: string;
  notes: string;
  page_count: number; // sayfa sayısı
  has_stored_pdf: boolean;
  stored_pdf_size: number;
  stored_filename: string;
  parent_document: number | null; // doluysa alt/destekleyici evrak
  sort_order: number; // dizi pusulası sırası
  sub_documents?: GeneratedDocument[]; // alt/destekleyici evraklar (yalnız ana evrakta)
  deleted_at?: string | null;
  created_at: string;
}

// Dizi pusulası kategori gruplaması (backend documents.DOC_CATEGORIES ile birebir).
// Belge türü → kategori başlığı; sabit sıra. INDEX_SHEET listelenmez (kapak).
const OTHER_CATEGORY_LABEL = "Diğer Evrak";
export const DOCUMENT_CATEGORIES: { label: string; types: DocumentType[] }[] = [
  { label: "İfadeler", types: ["STATEMENT_RECORD"] },
  { label: "Savunmalar", types: ["DEFENSE_RECORD"] },
  { label: "Bilgi Alma Tutanakları", types: ["INFO_GATHERING"] },
  { label: "Çağrı / Davet Yazıları", types: ["STATEMENT_CALL", "DEFENSE_CALL", "MEETING_CALL"] },
  { label: "Müdür Uyarısı", types: ["WARNING_LETTER"] },
  { label: "Tedbir / Süre Uzatma", types: ["PRECAUTION_NOTICE", "DEADLINE_EXTENSION"] },
  { label: "Kurul Kararı", types: ["COMMITTEE_DECISION"] },
  { label: "Tebliğler", types: ["PENALTY_NOTICE", "PENALTY_DAYS_NOTICE", "BOARD_DECISION_NOTICE"] },
  { label: "İtiraz", types: ["APPEAL_LETTER"] },
  { label: OTHER_CATEGORY_LABEL, types: ["OTHER"] },
];

// Belgeleri sabit-sıralı kategorilere böler; boş kategori atlanır, eşlenmemiş tür "Diğer Evrak".
export function categorizeDocuments(
  docs: GeneratedDocument[],
): { label: string; documents: GeneratedDocument[] }[] {
  const typeToCat: Partial<Record<DocumentType, string>> = {};
  for (const cat of DOCUMENT_CATEGORIES) for (const t of cat.types) typeToCat[t] = cat.label;
  const buckets: Record<string, GeneratedDocument[]> = {};
  for (const cat of DOCUMENT_CATEGORIES) buckets[cat.label] = [];
  for (const d of docs) {
    const bucket = buckets[typeToCat[d.document_type] ?? OTHER_CATEGORY_LABEL];
    if (bucket) bucket.push(d);
  }
  return DOCUMENT_CATEGORIES.map((c) => ({
    label: c.label,
    documents: buckets[c.label] ?? [],
  })).filter((c) => c.documents.length > 0);
}

// Bir belgenin dizi pusulasında görünen ADI: katılımcı belgelerinde "kimden"
// (source_label[: source_name]); diğerlerinde sade başlık.
export function documentDisplayName(d: GeneratedDocument): string {
  if (d.source_label) return d.source_name ? `${d.source_label}: ${d.source_name}` : d.source_label;
  return d.title;
}

// Manuel belge / alt evrak kütük kaydı girdisi.
export interface DocumentLogBody {
  document_type: DocumentType;
  title: string;
  generated_on: string; // YYYY-MM-DD
  document_no?: string;
  student_id?: number | null;
  source_label?: string;
  source_name?: string;
  page_count?: number; // varsayılan 1
  parent_document_id?: number | null; // doluysa alt/destekleyici evrak
  notes?: string;
}

// Kütük kaydı metadata düzenleme (sayfa/başlık/açıklama + kimden).
export interface DocumentUpdateBody {
  page_count?: number;
  title?: string;
  notes?: string;
  source_label?: string; // "kimden" sıfat/kaynak
  source_name?: string; // "kimden" ad
}

// Tebliğ alıcısı — Form-14↔15 (ceza tebliği) ve Form-16↔17 (ceza günleri) ikizlerini ayırır.
export type DocumentRecipient = "student" | "parent";

// Form-7/8 bilgi toplama varyantı (öğrenciden / öğretmenden).
// student/teacher: INFO_GATHERING (Form-7/8); record/petition: DEADLINE_EXTENSION (F-12/13).
export type DocumentVariant = "student" | "teacher" | "record" | "petition";

export interface DocumentGenerateBody {
  document_type: DocumentType;
  generated_on: string; // YYYY-MM-DD
  recipient?: DocumentRecipient; // yalnız recipientSelectable türlerde anlamlı
  student_id?: number | null; // STUDENT_REQUIRED türlerde zorunlu
  // Dal B ifade/savunma/bilgi formları — hedef katılımcı + GEÇİCİ alanlar
  // (tarih/saat/yer + variant); bunlar yalnız PDF'e basılır, DB'ye yazılmaz.
  participant_id?: number | null; // PARTICIPANT_REQUIRED türlerde zorunlu
  statement_date?: string | null; // çağrı/toplantı tarihi (YYYY-MM-DD)
  statement_time?: string; // saat (serbest metin, örn. "10:30")
  statement_place?: string; // yer
  // İfade tutanağı (Form-4/5/6) dolu-bas: konu/sorular + ifade gövdesi.
  // GEÇİCİ — yalnız PDF'e basılır, DB'ye YAZILMAZ ve loglanmaz (no-trace; içerik saklanmaz).
  statement_subject?: string;
  statement_body?: string;
  // Form-02 davranış özeti: tırnak içine basılır. GEÇİCİ — DB'ye yazılmaz,
  // loglanmaz; boşsa backend uyarı kaydının özetine düşer, ikisi de boşsa 400 döner.
  behavior_summary?: string;
  variant?: DocumentVariant; // yalnız INFO_GATHERING (Form-7/8) + DEADLINE_EXTENSION
  source_label?: string; // bilgi alma "kaynak" seçimi; diğerlerinde yok sayılır
  document_no?: string;
  title?: string;
  // Üst kurul kararı tebliği (BOARD_DECISION_NOTICE) — hepsi GEÇİCİ:
  // üst kurul karar no/tarihi DB'de tutulmaz, yalnız PDF'e basılır. Merci/sonuç boş
  // bırakılırsa backend karardan / en son sonuçlanmış itirazdan türetir.
  notice_kind?: NoticeKind;
  board_authority?: BoardAuthority | "";
  board_decision_no?: string;
  board_decision_date?: string | null;
  board_outcome?: BoardOutcome | "";
  result_summary?: string;
}

// Üst kurul tebliği senaryoları + merci/sonuç eksenleri.
export type NoticeKind = "approval" | "appeal_result";
export type BoardAuthority = "DISTRICT_BOARD" | "PROVINCIAL_BOARD" | "UPPER_BOARD";
export type BoardOutcome = "APPROVED" | "MODIFIED" | "UPHELD" | "REDUCED" | "OVERTURNED";

// Üretim motoru şablonu OLAN türler (documents.py DOC_TEMPLATES + BY_RECIPIENT).
// Diğer DocumentType değerleri kütükte geçerli ama PDF üretilemez (backend hatası).
export interface GeneratableDocType {
  value: DocumentType;
  label: string;
  studentRequired: boolean; // documents.py STUDENT_REQUIRED
  recipientSelectable?: boolean; // öğrenci/veli sürümü olan ikiz belgeler
  // Alıcı seçici etiketleri: verilmezse Form-14/16↔15/17 varsayılanı kullanılır.
  recipientOptions?: { value: DocumentRecipient; label: string }[];
  // Form-02 davranış özeti girişi: textarea + uyarı kaydından prefill.
  behaviorSummary?: boolean;
  // Dal B formları: documents.py PARTICIPANT_REQUIRED.
  participantRequired?: boolean; // hedef katılımcı (suçlanan/mağdur/tanık) seçilir
  participantRoleFilter?: ParticipantRole[]; // yalnız bu rollerdeki katılımcılar (boşsa hepsi)
  scheduling?: boolean; // tarih/saat/yer alanları (çağrı/toplantı)
  // Dolu-bas (ifade + savunma): konu/olay + gövde textarea'ları.
  // İçerik GEÇİCİ (no-trace) — yalnız PDF'e basılır, kaydedilmez.
  freeformStatement?: boolean;
  // Dolu-bas alan etiketleri: verilmezse ifade tutanağı varsayılanları.
  freeformStatementLabels?: { subject: string; body: string };
  // Üst kurul kararı tebliği alan grubu: senaryo/merci/sonuç + karar no/tarihi.
  boardDecisionNotice?: boolean;
  // Variant ekseni olan belgeler (INFO_GATHERING Form-7/8; DEADLINE_EXTENSION F-12/13).
  variantOptions?: { value: DocumentVariant; label: string }[];
  variantLabel?: string; // variant seçici etiketi
  // "Kimden / kaynak" seçimi — dizi pusulasında görünen source_label.
  // INFO_GATHERING için (Rehberlik Servisi/Sınıf Öğretmeni/…); diğerlerinde rol otomatik.
  sourceOptions?: string[];
  description: string;
}

// Bilgi alma (INFO_GATHERING) "kaynak" seçenekleri (backend INFO_GATHERING_SOURCES).
export const INFO_GATHERING_SOURCES: string[] = [
  "Rehberlik Servisi",
  "Sınıf Öğretmeni",
  "Müdür Yardımcısı",
  "Ders Öğretmeni",
  "Veli",
  "Diğer",
];

export const GENERATABLE_DOCUMENT_TYPES: GeneratableDocType[] = [
  // --- Dal B ifade/savunma/bilgi formları — süreç sırasıyla ---
  {
    value: "STATEMENT_CALL",
    label: "İfadeye çağrı pusulası (Form-3)",
    studentRequired: false,
    participantRequired: true,
    scheduling: true,
    description:
      "Katılımcıyı (mağdur/suçlanan/tanık) ifade vermeye çağırır; tarih/saat/yer girilir, tebliğ-tebellüğ ile öğrenciye verilir (md. 194-195).",
  },
  {
    value: "STATEMENT_RECORD",
    label: "İfade tutanağı (Form-4/5/6)",
    studentRequired: false,
    participantRequired: true,
    freeformStatement: true,
    description:
      "Seçilen katılımcının rolüne göre (mağdur/suçlanan/tanık) ön-doldurulmuş tutanak. Konu/sorular + ifade ekrandan yazılırsa DOLU basılır (boşsa elle yazım için boş kalır); içerik KAYDEDİLMEZ (no-trace, md. 194).",
  },
  {
    value: "INFO_GATHERING",
    label: "Bilgi toplama formu (Form-7/8)",
    studentRequired: false,
    participantRequired: true,
    participantRoleFilter: ["ACCUSED"],
    variantLabel: "Form sürümü",
    variantOptions: [
      { value: "student", label: "Öğrenciden (Form-7)" },
      { value: "teacher", label: "Öğretmenden (Form-8)" },
    ],
    sourceOptions: INFO_GATHERING_SOURCES,
    description:
      "Suçlanan öğrenci hakkında öğrenciden (Form-7) veya öğretmenden (Form-8) bilgi toplama formu (md. 193). 'Kaynak' dizi pusulasında kimden olduğunu gösterir.",
  },
  {
    value: "DEFENSE_CALL",
    label: "Savunmaya çağrı (Form-9)",
    studentRequired: false,
    participantRequired: true,
    participantRoleFilter: ["ACCUSED"],
    scheduling: true,
    description:
      "Suçlanan öğrenciyi savunma vermeye çağırır; tarih/saat/yer girilir, tebliğ-tebellüğ (md. 194).",
  },
  {
    value: "MEETING_CALL",
    label: "Kurul toplantı çağrısı (Form-10)",
    studentRequired: false,
    scheduling: true,
    description:
      "Aktif disiplin kurulu üyelerini toplantıya çağırır; toplantı tarih/saat/yer girilir (md. 190-191).",
  },
  {
    value: "DEFENSE_RECORD",
    label: "Savunma tutanağı (Form-11)",
    studentRequired: false,
    participantRequired: true,
    participantRoleFilter: ["ACCUSED"],
    scheduling: true,
    freeformStatement: true,
    freeformStatementLabels: { subject: "Olay / Konu", body: "Savunma metni" },
    description:
      "Hakkında işlem yapılan öğrencinin savunma tutanağı; künye ön-dolu, kurul imza ızgarası. Olay + savunma ekrandan yazılırsa DOLU basılır (boşsa elle yazım için boş kalır); içerik KAYDEDİLMEZ (no-trace, md. 194).",
  },
  {
    value: "DEADLINE_EXTENSION",
    label: "Süre uzatma (Form-12/13)",
    studentRequired: false,
    variantLabel: "Form sürümü",
    variantOptions: [
      { value: "record", label: "Kurul ara karar tutanağı (Form-12)" },
      { value: "petition", label: "Müdürlüğe dilekçe (Form-13)" },
    ],
    description:
      "Kurul karar süresi uzatması (md. 192/3); veriler dosyanın süre uzatma kaydından gelir. Ara karar tutanağı üye+başkan imzalı; dilekçe başkandan müdürlüğe (EK: tutanak).",
  },
  // --- Karar/tebliğ/itiraz aşaması formları ---
  {
    value: "COMMITTEE_DECISION",
    label: "Kurul kararı (EK-1)",
    studentRequired: true,
    description: "Kimlik + karar + anlatı alanları + imzalar (tam otomatik, md. 163-170).",
  },
  {
    value: "PENALTY_NOTICE",
    label: "Ceza/Karar tebliği (Form-14/15)",
    studentRequired: true,
    recipientSelectable: true,
    description: "Karar + itiraz son günü (öğrenci/veli sürümü, ön-doldurulmuş, md. 169/5).",
  },
  {
    value: "PENALTY_DAYS_NOTICE",
    label: "Ceza günleri tebliği (Form-16/17)",
    studentRequired: true,
    recipientSelectable: true,
    description: "Kısa süreli uzaklaştırma gün tebliği (öğrenci/veli sürümü, md. 172).",
  },
  {
    value: "APPEAL_LETTER",
    label: "İl/İlçe itiraz yazısı (Form-18)",
    studentRequired: true,
    description: "Karar + veli itiraz dilekçesi → üst kurula sevk yazısı (md. 169/3).",
  },
  {
    value: "BOARD_DECISION_NOTICE",
    label: "Üst kurul kararı tebliği",
    studentRequired: true,
    recipientSelectable: true,
    boardDecisionNotice: true,
    description:
      "İlçe/il/üst kurulun onay (md. 169/2) veya itiraz sonucu (md. 169/3-4) kararının öğrenci/veli tebliği. Merci karar no/tarihi elle girilir; içerik KAYDEDİLMEZ (yalnız PDF).",
  },
  {
    value: "WARNING_LETTER",
    label: "Müdür uyarısı yazısı (Form-02)",
    studentRequired: true,
    recipientSelectable: true,
    recipientOptions: [
      { value: "student", label: "Öğrenciye (Form-02)" },
      { value: "parent", label: "Veliye (bilgilendirme yazısı)" },
    ],
    behaviorSummary: true,
    description:
      "Kusurlu davranışa yönelik yazılı uyarı (ceza değil, md. 157/7). Veli sürümü bilgilendirme amaçlıdır.",
  },
  {
    value: "PRECAUTION_NOTICE",
    label: "Tedbir bildirimi (md. 175)",
    studentRequired: true,
    description: "Geçici uzaklaştırma bildirimi (mevzuattan türetilmiş; resmî MEB formu yok).",
  },
];

// --- State machine: bir sonraki olası aşamalar (UI butonu için) ---
// Backend state_machine.py ile birebir. Override ek olarak PETITION→DECIDED'i açar.

export function nextAllowedStages(current: CaseStage | undefined): CaseStage[] {
  if (!current) return ["PETITION"];
  switch (current) {
    case "PETITION":
      return ["GUIDANCE_REFERRED"]; // DECIDED yalnız override ile
    case "GUIDANCE_REFERRED":
      return ["GUIDANCE_RETURNED"];
    case "GUIDANCE_RETURNED":
      return ["DECIDED"];
    case "DECIDED":
      return ["COMMITTEE_DONE", "CLOSED"];
    case "COMMITTEE_DONE":
      return ["CLOSED"];
    case "CLOSED":
      return [];
  }
}

export function isTerminalStage(stage: CaseStage): boolean {
  return stage === "CLOSED";
}

// --- API çağrıları ---

const BASE = "/discipline";

export const disiplinApi = {
  listCases: async (
    params: {
      stage?: CaseStage | "";
      onlyOpen?: boolean;
      search?: string;
      studentId?: number;
    } = {},
  ): Promise<DisciplineCase[]> => {
    // stage/search/student sunucu-taraflı; onlyOpen istemci-taraflı (uç parametresi yok).
    const parts = ["limit=200"];
    if (params.stage) parts.push(`stage=${encodeURIComponent(params.stage)}`);
    if (params.search) parts.push(`search=${encodeURIComponent(params.search)}`);
    if (params.studentId !== undefined) parts.push(`student=${params.studentId}`);
    const data = await api.get<Paginated<DisciplineCase> | DisciplineCase[]>(
      `${BASE}/cases/?${parts.join("&")}`,
    );
    let items = unwrap(data);
    if (params.onlyOpen) items = items.filter((c) => !c.closed_at);
    return items;
  },

  getCase: (id: number) => api.get<DisciplineCase>(`${BASE}/cases/${id}/`),

  // Aşama geri al (seçilen daha erken aşamaya) — güncel dosya detayını döner.
  revertStage: (caseId: number, body: StageRevertBody) =>
    api.post<DisciplineCase>(`${BASE}/cases/${caseId}/revert-stage/`, body),

  // Dosyayı kapat. Uygunluk + erken-kapatma (override + gerekçe) serviste;
  // uygun değilse 400 (en erken gün mesajda).
  closeCase: (caseId: number, body: CaseCloseBody = {}) =>
    api.post<DisciplineCase>(`${BASE}/cases/${caseId}/close/`, body),

  createCase: (body: DisciplineCaseCreateBody) => api.post<DisciplineCase>(`${BASE}/cases/`, body),

  patchCase: (id: number, body: DisciplineCasePatchBody) =>
    api.patch<DisciplineCase>(`${BASE}/cases/${id}/`, body),

  addEvent: (id: number, body: DisciplineEventCreateBody) => {
    // Tel anahtarı: FE `committee_decision_type_id` → backend `committee_decision_type`.
    const { committee_decision_type_id, ...rest } = body;
    return api.post<DisciplineEvent>(`${BASE}/cases/${id}/events/`, {
      ...rest,
      ...(committee_decision_type_id !== undefined
        ? { committee_decision_type: committee_decision_type_id }
        : {}),
    });
  },

  uploadAttachment: async (
    id: number,
    file: File,
    fileType: AttachmentType,
    eventId?: number,
  ): Promise<DisciplineAttachment & { is_duplicate: boolean }> => {
    const fd = new FormData();
    fd.append("file", file);
    fd.append("file_type", fileType);
    if (eventId !== undefined) fd.append("event", String(eventId));
    return api.postForm<DisciplineAttachment & { is_duplicate: boolean }>(
      `${BASE}/cases/${id}/attachments/`,
      fd,
    );
  },

  downloadAttachment: (id: number, attachmentId: number) =>
    api.getBlob(`${BASE}/cases/${id}/attachments/${attachmentId}/download/`),

  deleteAttachment: (id: number, attachmentId: number) =>
    api.del<void>(`${BASE}/cases/${id}/attachments/${attachmentId}/`),

  // --- Karar tipleri (lookup) ---

  // Varsayılan yalnız aktif tipler (dosya formlarında seçilebilecek olanlar).
  // `includeInactive` yönetim ekranı içindir: pasifleştirilen tip listeden de
  // düşerse geri açılamaz — backend `?all=1` ile hepsini verir.
  listDecisionTypes: async (
    options: { includeInactive?: boolean } = {},
  ): Promise<DisciplineDecisionType[]> => {
    const query = options.includeInactive ? "?limit=200&all=1" : "?limit=200";
    const data = await api.get<Paginated<DisciplineDecisionType> | DisciplineDecisionType[]>(
      `${BASE}/decision-types/${query}`,
    );
    return unwrap(data);
  },

  createDecisionType: (body: DecisionTypeCreateBody) =>
    api.post<DisciplineDecisionType>(`${BASE}/decision-types/`, body),

  patchDecisionType: (id: number, body: Partial<DecisionTypeCreateBody>) =>
    api.patch<DisciplineDecisionType>(`${BASE}/decision-types/${id}/`, body),

  // --- Disiplin kurulu tanımı (aktif ders yılı) ---
  // Backend tekil obje döndürür; kurul tanımsızsa 204 (boş gövde). OYS bileşen
  // sözleşmesi `{ committee: ... | null }` zarfıdır — çeviri burada.

  getCommittee: async (): Promise<{ committee: DisciplineCommittee | null }> => {
    const committee = await api.get<DisciplineCommittee | undefined>(`${BASE}/committee/`);
    return { committee: committee ?? null };
  },

  createCommittee: (body: CommitteeCreateBody) =>
    api.post<DisciplineCommittee>(`${BASE}/committee/`, {
      school_year: body.school_year_id,
      chair: body.chair_id,
      ...(body.notes !== undefined ? { notes: body.notes } : {}),
    }),

  // Backend'de POST (OYS'de PUT idi); gövde model alanı `chair`.
  setCommitteeChair: (body: CommitteeChairUpdateBody) =>
    api.post<DisciplineCommittee>(`${BASE}/committee/chair/`, { chair: body.chair_id }),

  // Üye ekleme güncel kurulun tamamını döner (OYS tek üye dönerdi).
  addCommitteeMember: (body: CommitteeMemberCreateBody) =>
    api.post<DisciplineCommittee>(`${BASE}/committee/members/`, body),

  removeCommitteeMember: (memberId: number) =>
    api.del<void>(`${BASE}/committee/members/${memberId}/`),

  // --- Kurul toplantısı (dosya başına; katılanlar kurul üyelerinden) ---

  listMeetings: (caseId: number) =>
    api.get<DisciplineMeeting[]>(`${BASE}/cases/${caseId}/meeting/`),

  recordMeeting: (caseId: number, body: MeetingCreateBody) =>
    api.post<DisciplineMeeting>(`${BASE}/cases/${caseId}/meeting/`, body),

  // --- Rollü katılımcı + müdür uyarısı + triaj ---

  listParticipants: (caseId: number) =>
    api.get<DisciplineParticipant[]>(`${BASE}/cases/${caseId}/participants/`),

  addParticipant: (caseId: number, body: ParticipantCreateBody) =>
    api.post<DisciplineParticipant>(`${BASE}/cases/${caseId}/participants/`, body),

  removeParticipant: (caseId: number, participantId: number) =>
    api.del<void>(`${BASE}/cases/${caseId}/participants/${participantId}/`),

  listWarnings: (caseId: number) =>
    api.get<DisciplineWarning[]>(`${BASE}/cases/${caseId}/warnings/`),

  addWarning: (caseId: number, body: WarningCreateBody) =>
    api.post<DisciplineWarning>(`${BASE}/cases/${caseId}/warnings/`, {
      student: body.student_id,
      warning_date: body.warning_date,
      summary: body.summary,
    }),

  // Backend öğrenci başına düz liste döner; OYS zarfı (`should_route_to_committee`
  // özet bayrağı, herhangi biri true → true) burada türetilir (OYS view paritesi).
  triageSuggestion: async (caseId: number): Promise<TriageSuggestion> => {
    const students = await api.get<TriageStudent[]>(`${BASE}/cases/${caseId}/triage-suggestion/`);
    return {
      students,
      should_route_to_committee: students.some((s) => s.should_route_to_committee),
    };
  },

  // --- Resmî karar + itiraz + EK-1 anlatı ---

  listDecisions: (caseId: number) =>
    api.get<DecisionsResponse>(`${BASE}/cases/${caseId}/decisions/`),

  createDecision: (caseId: number, body: DecisionCreateBody) => {
    const { student_id, ...rest } = body;
    return api.post<DisciplineDecision>(`${BASE}/cases/${caseId}/decisions/`, {
      ...rest,
      student: student_id,
    });
  },

  // Beklemedeki kararı düzenle / soft-delete / geri yükle / silinmiş-liste.
  updateDecision: (caseId: number, decisionId: number, body: DecisionEditBody) =>
    api.patch<DisciplineDecision>(`${BASE}/cases/${caseId}/decisions/${decisionId}/`, body),

  deleteDecision: (caseId: number, decisionId: number) =>
    api.del<void>(`${BASE}/cases/${caseId}/decisions/${decisionId}/`),

  restoreDecision: (caseId: number, decisionId: number) =>
    api.post<DisciplineDecision>(`${BASE}/cases/${caseId}/decisions/${decisionId}/restore/`),

  listDeletedDecisions: (caseId: number) =>
    api.get<DisciplineDecision[]>(`${BASE}/cases/${caseId}/decisions/deleted/`),

  approveDecision: (caseId: number, decisionId: number, body: DecisionApprovalBody) =>
    api.post<DisciplineDecision>(`${BASE}/cases/${caseId}/decisions/${decisionId}/approve/`, body),

  // md. 197 — kurula iade / ilçe kuruluna gönderme.
  reviewDecision: (caseId: number, decisionId: number, body: DecisionReviewBody) =>
    api.post<DisciplineDecision>(`${BASE}/cases/${caseId}/decisions/${decisionId}/review/`, body),

  notifyDecision: (caseId: number, decisionId: number, body: DecisionNotifyBody) =>
    api.post<DisciplineDecision>(`${BASE}/cases/${caseId}/decisions/${decisionId}/notify/`, body),

  confirmESchoolEntry: (caseId: number, decisionId: number, body: DecisionESchoolBody) =>
    api.post<DisciplineDecision>(`${BASE}/cases/${caseId}/decisions/${decisionId}/e-school/`, body),

  updateDecisionNarrative: (caseId: number, decisionId: number, body: DecisionNarrativeBody) =>
    api.post<DisciplineDecision>(
      `${BASE}/cases/${caseId}/decisions/${decisionId}/narrative/`,
      body,
    ),

  // İtiraz LİSTESİ ayrı çekilmez: `listDecisions` her kararın `appeals` dizisini
  // gömülü döndürür (DecisionSerializer). Ayrı bir liste istemcisi ölü yüzeydi.
  fileAppeal: (caseId: number, decisionId: number, body: AppealCreateBody) =>
    api.post<DisciplineAppeal>(`${BASE}/cases/${caseId}/decisions/${decisionId}/appeals/`, body),

  forwardAppeal: (caseId: number, appealId: number, body: AppealForwardBody) =>
    api.post<DisciplineAppeal>(`${BASE}/cases/${caseId}/appeals/${appealId}/forward/`, body),

  resolveAppeal: (caseId: number, appealId: number, body: AppealResolveBody) =>
    api.post<DisciplineAppeal>(`${BASE}/cases/${caseId}/appeals/${appealId}/resolve/`, body),

  // --- Kurul karar süresi + uzatma + tedbir ---

  listExtensions: (caseId: number) =>
    api.get<ExtensionsResponse>(`${BASE}/cases/${caseId}/extensions/`),

  createExtension: (caseId: number, body: ExtensionCreateBody) =>
    api.post<DisciplineDeadlineExtension>(`${BASE}/cases/${caseId}/extensions/`, body),

  approveExtension: (caseId: number, extensionId: number, body: ExtensionApproveBody) =>
    api.post<DisciplineDeadlineExtension>(
      `${BASE}/cases/${caseId}/extensions/${extensionId}/approve/`,
      body,
    ),

  listPrecautions: (caseId: number) =>
    api.get<DisciplinePrecaution[]>(`${BASE}/cases/${caseId}/precautions/`),

  createPrecaution: (caseId: number, body: PrecautionCreateBody) => {
    const { student_id, ...rest } = body;
    return api.post<DisciplinePrecaution>(`${BASE}/cases/${caseId}/precautions/`, {
      ...rest,
      student: student_id,
    });
  },

  liftPrecaution: (caseId: number, precautionId: number, body: PrecautionLiftBody) =>
    api.post<DisciplinePrecaution>(
      `${BASE}/cases/${caseId}/precautions/${precautionId}/lift/`,
      body,
    ),

  extendPrecaution: (caseId: number, precautionId: number, body: PrecautionExtendBody) =>
    api.post<DisciplinePrecaution>(
      `${BASE}/cases/${caseId}/precautions/${precautionId}/extend/`,
      body,
    ),

  // --- Evrak üretimi + kütük zaman çizelgesi ---

  // Evrak kütüğü (üretilen belgeler) — dizi sırasına (sort_order) göre (document_timeline).
  listDocuments: (caseId: number) =>
    api.get<GeneratedDocument[]>(`${BASE}/cases/${caseId}/documents/`),

  // Sürece dışarıdan gelen evrakı (veya alt/destekleyici evrakı) manuel kütüğe ekler
  // (içerik saklanmaz). parent_document_id doluysa alt evrak.
  addDocument: (caseId: number, body: DocumentLogBody) => {
    const { student_id, parent_document_id, ...rest } = body;
    return api.post<GeneratedDocument>(`${BASE}/cases/${caseId}/documents/`, {
      ...rest,
      ...(student_id !== undefined ? { student: student_id } : {}),
      ...(parent_document_id !== undefined ? { parent_document: parent_document_id } : {}),
    });
  },

  // Kütük kaydı metadata düzenleme (sayfa/başlık/açıklama + kimden).
  updateDocument: (caseId: number, documentId: number, body: DocumentUpdateBody) =>
    api.patch<GeneratedDocument>(`${BASE}/cases/${caseId}/documents/${documentId}/`, body),

  // Belge kütük kaydını soft-delete eder (geri alınabilir). 204 döner.
  deleteDocument: (caseId: number, documentId: number) =>
    api.del<void>(`${BASE}/cases/${caseId}/documents/${documentId}/`),

  // Soft-delete edilmiş belgeyi geri yükler.
  restoreDocument: (caseId: number, documentId: number) =>
    api.post<GeneratedDocument>(`${BASE}/cases/${caseId}/documents/${documentId}/restore/`),

  // Dosyanın silinmiş belgeleri (çöp kutusu) — geri yükleme için.
  listDeletedDocuments: (caseId: number) =>
    api.get<GeneratedDocument[]>(`${BASE}/cases/${caseId}/documents/deleted/`),

  // Üretim anında veritabanında saklanan PDF kopyası; silinmiş evrakta da erişilebilir.
  downloadStoredDocument: (caseId: number, documentId: number) =>
    api.getBlob(`${BASE}/cases/${caseId}/documents/${documentId}/download/`),

  // Dizi pusulası (fihrist kapağı) PDF'i — kütüğe yazmaz, blob indirir.
  getIndexSheet: (caseId: number) => api.getBlob(`${BASE}/cases/${caseId}/documents/index-sheet/`),

  // Dizi pusulası sırasını yeniden düzenler; güncel zaman çizelgesini döner.
  reorderDocuments: (caseId: number, documentIds: number[]) =>
    api.patch<GeneratedDocument[]>(`${BASE}/cases/${caseId}/documents/reorder/`, {
      document_ids: documentIds,
    }),

  // WeasyPrint PDF üretir + kütüğe yazar (daima log=True). Yanıt: application/pdf blob.
  generateDocument: (caseId: number, body: DocumentGenerateBody) => {
    const { student_id, participant_id, ...rest } = body;
    return api.postBlob(`${BASE}/cases/${caseId}/documents/generate/`, {
      ...rest,
      ...(student_id !== undefined ? { student: student_id } : {}),
      ...(participant_id !== undefined ? { participant: participant_id } : {}),
    });
  },
};

// =============================================================================
// "Yaklaşan Süreler" paneli (backend apps/disiplin/deadlines.py). OYS'de bu iş
// günlük Celery görevindeydi; standalone'da panel açılışta bu ucu okur.
// =============================================================================

/** Panel satır önem düzeyi — backend `deadlines.Severity` değerleriyle birebir. */
export type DeadlineSeverity = "GEÇTİ" | "YAKLAŞIYOR" | "BİLGİ";

/** Sabit gösterim sırası (backend de aynı sırayla döner; FE gruplaması buna dayanır). */
export const SEVERITY_ORDER: DeadlineSeverity[] = ["GEÇTİ", "YAKLAŞIYOR", "BİLGİ"];

/** Paneldeki tek satır (deadlines.DeadlineItem ile birebir). */
export interface DeadlineItem {
  severity: DeadlineSeverity;
  case_no: string;
  title: string;
  /** ISO tarih (YYYY-MM-DD); tarihsiz BİLGİ satırlarında null. */
  due_date: string | null;
  statute_ref: string;
  /** Dosya detay rotası — backend `/disiplin/<id>` üretir. */
  link: string;
}

export const deadlinesApi = {
  /** Süre izleme satırları (düz dizi; sayfalama yok). */
  list: (): Promise<DeadlineItem[]> => api.get<DeadlineItem[]>("/disiplin/yaklasan-sureler/"),
};

// --- Kişi arama (okul modülü uçları — OYS lookup uçlarının karşılığı) ---

export interface StudentSearchRow {
  id: number;
  full_name: string;
  student_number: string;
  class_label: string;
  /** Sicilde boşsa disiplin dosyası açılırken kullanıcıdan istenir. */
  guardian_name?: string;
}

export const studentLookupApi = {
  /**
   * Seçici (autocomplete) araması — YALNIZ aktif öğrenci döner.
   *
   * `only_active=true` seçiciye özgüdür: okuldan ayrılmış öğrenciye yeni
   * dosya/katılımcı/karar bağlanmasın. Sicil (Kişiler) sayfası aynı ucu
   * süzgeçsiz çağırır; ayrılmış öğrenciler orada görünmeye devam eder.
   */
  search: async (query: string, limit = 20): Promise<StudentSearchRow[]> => {
    const data = await api.get<Paginated<StudentSearchRow>>(
      `/students/?search=${encodeURIComponent(query)}&limit=${limit}&only_active=true`,
    );
    return data.results;
  },
};

export interface PersonnelSearchRow {
  id: number;
  full_name: string;
  title: string;
  branch: string;
}

export const personnelLookupApi = {
  search: async (query: string, limit = 20): Promise<PersonnelSearchRow[]> => {
    const data = await api.get<Paginated<PersonnelSearchRow>>(
      `/personnel/?search=${encodeURIComponent(query)}&limit=${limit}`,
    );
    return data.results;
  },
};
