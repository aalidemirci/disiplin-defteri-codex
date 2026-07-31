// `okul` modülü API istemcisi — kurum künyesi/kurulum, ders yılı, tatil takvimi,
// kişi sicilleri (öğrenci + personel), toplu içe aktarma ve şablon indirme uçları.
// Backend `apps/okul/{urls,views,serializers}.py` ile BİREBİR; tel anahtarı çevirisi
// (camelCase filtre → snake_case query/gövde, `schoolYearId` → `school_year`) ve
// sayfalama zarfı çözümü YALNIZ bu sınırda yapılır — sayfalar ham uç bilmez.

import { api } from "../../lib/api";
import { getGradeLevels as fetchGradeLevels } from "../../lib/gradeLevels";
import type { GradeLevelOption, GradeLevelsResponse } from "../../lib/gradeLevels";
import { unwrap } from "../../lib/pagination";
import type { Paginated } from "../../lib/pagination";

export type { GradeLevelOption, GradeLevelsResponse, Paginated };

// ---------------------------------------------------------------------------
// Ders yılı
// ---------------------------------------------------------------------------

/** Ders yılı — SchoolYearSerializer ile birebir (`is_active` salt-okunur). */
export interface SchoolYear {
  id: number;
  name: string;
  start_date: string;
  end_date: string;
  is_active: boolean;
}

export interface SchoolYearCreateBody {
  name: string;
  start_date: string;
  end_date: string;
}

export interface SchoolTerm {
  id: number;
  school_year: number;
  sequence: 1 | 2;
  name: string;
  start_date: string;
  end_date: string;
}

export interface SchoolTermConfigurationBody {
  first_term_end: string;
  second_term_start: string;
}

// ---------------------------------------------------------------------------
// Kurulum sihirbazı / kurum künyesi
// ---------------------------------------------------------------------------

/** `GET /setup/status/` — sihirbaz kapısı + sicil doluluk sayaçları. */
export interface SetupStatus {
  setup_completed: boolean;
  school_name: string;
  has_active_school_year: boolean;
  student_count: number;
  personnel_count: number;
  holiday_count: number;
}

/** Kurum künyesi — evrak antedi buradan çözülür (`setup_completed` salt-okunur). */
export interface SchoolConfig {
  school_name: string;
  province: string;
  district: string;
  principal_name: string;
  setup_completed: boolean;
}

/** PUT gövdesi kısmi olabilir — backend MERGE semantiği uygular. */
export type SchoolConfigBody = Partial<Omit<SchoolConfig, "setup_completed">>;

// ---------------------------------------------------------------------------
// Tatil takvimi
// ---------------------------------------------------------------------------

export type HolidayKind = "OFFICIAL" | "RELIGIOUS" | "OTHER";

export const HOLIDAY_KIND_TR: Record<HolidayKind, string> = {
  OFFICIAL: "Resmî tatil",
  RELIGIOUS: "Dini bayram",
  OTHER: "İdari/diğer",
};

export interface Holiday {
  id: number;
  name: string;
  start_date: string;
  end_date: string;
  kind: HolidayKind;
  /** Hicri takvime bağlı bayram tahmini — kullanıcı takvimden düzeltebilir. */
  is_estimated: boolean;
}

export interface HolidayCreateBody {
  name: string;
  start_date: string;
  end_date: string;
  kind?: HolidayKind;
  is_estimated?: boolean;
}

/** `POST /holidays/seed/` sonucu — eklenen ve zaten var olduğu için atlanan sayısı. */
export interface HolidaySeedResult {
  created: number;
  skipped: number;
}

// ---------------------------------------------------------------------------
// Kişi sicilleri
// ---------------------------------------------------------------------------

/** Cinsiyet — boş dize "belirtilmemiş" demektir (backend blank=True). */
export type Gender = "E" | "K" | "";
export type GuardianKinship = "ANNE" | "BABA" | "DIGER" | "";
export type StudentStatus = "ACTIVE" | "LEFT";

export const GENDER_TR: Record<"E" | "K", string> = { E: "Erkek", K: "Kız" };

export const GUARDIAN_KINSHIP_TR: Record<"ANNE" | "BABA" | "DIGER", string> = {
  ANNE: "Anne",
  BABA: "Baba",
  DIGER: "Diğer",
};

export const STUDENT_STATUS_TR: Record<StudentStatus, string> = {
  ACTIVE: "Aktif",
  LEFT: "Ayrıldı",
};

/** Öğrenci sicili — StudentSerializer ile birebir (`full_name`/`class_label` türetilmiş). */
export interface Student {
  id: number;
  tckn: string;
  first_name: string;
  last_name: string;
  full_name: string;
  student_number: string;
  class_level: number | null;
  class_section: string;
  class_label: string;
  birth_date: string | null;
  gender: Gender;
  status: StudentStatus;
  guardian_name: string;
  guardian_kinship: GuardianKinship;
  guardian_phone: string;
  guardian_phone2: string;
  guardian_address: string;
}

/** Öğrenci yazma gövdesi — türetilmiş alanlar (full_name/class_label) gönderilmez. */
export interface StudentWriteBody {
  tckn?: string;
  first_name: string;
  last_name: string;
  student_number?: string;
  class_level?: number | null;
  class_section?: string;
  birth_date?: string | null;
  gender?: Gender;
  status?: StudentStatus;
  guardian_name?: string;
  guardian_kinship?: GuardianKinship;
  guardian_phone?: string;
  guardian_phone2?: string;
  guardian_address?: string;
}

/** Personel sicili — PersonnelSerializer ile birebir (`full_name` türetilmiş). */
export interface Personnel {
  id: number;
  first_name: string;
  last_name: string;
  title: string;
  branch: string;
  full_name: string;
}

export interface PersonnelWriteBody {
  first_name: string;
  last_name: string;
  title?: string;
  branch?: string;
}

/** Ders yılı + şube için kurumsal sorumlular. */
export interface ClassResponsibility {
  id: number;
  school_year: number;
  school_year_name: string;
  class_level: number;
  class_section: string;
  class_label: string;
  class_teacher: number | null;
  class_teacher_detail: Personnel | null;
  assistant_principal: number | null;
  assistant_principal_detail: Personnel | null;
  guidance_teacher: number | null;
  guidance_teacher_detail: Personnel | null;
}

export interface ClassResponsibilityWriteBody {
  school_year: number;
  class_level: number;
  class_section: string;
  class_teacher?: number | null;
  assistant_principal?: number | null;
  guidance_teacher?: number | null;
}

export interface StudentListParams {
  search?: string;
  classLevel?: number | null;
  classSection?: string;
  limit?: number;
  offset?: number;
}

export interface PersonnelListParams {
  search?: string;
  limit?: number;
  offset?: number;
}

// ---------------------------------------------------------------------------
// İçe aktarma (xlsx dosyası VEYA pano metni — tam olarak biri)
// ---------------------------------------------------------------------------

/** Rapordaki tek satır sorunu (uyarı veya atlanan satır). */
export interface ImportIssue {
  row_number: number;
  field: string;
  issue: string;
  raw_value: string;
}

interface ImportReportBase {
  file_hash: string;
  file_name: string;
  total_rows: number;
  processed: number;
  /** Aynı içerik daha önce aktarılmış — UYARIDIR, engel değil. */
  already_imported: boolean;
  /** Önizleme (true) hiçbir şey yazmaz; commit false döner. */
  dry_run: boolean;
  warnings: ImportIssue[];
  skipped: ImportIssue[];
}

export interface StudentImportReport extends ImportReportBase {
  created_students: number;
  updated_students: number;
  unchanged_students: number;
}

export interface PersonnelImportReport extends ImportReportBase {
  created_personnel: number;
  updated_personnel: number;
  unchanged_personnel: number;
}

export type ImportReport = StudentImportReport | PersonnelImportReport;

/** İçe aktarma girdisi — dosya yolu (multipart) veya pano metni (JSON). */
export type ImportInput = { file: File } | { text: string };

/**
 * Öğrenci/personel raporlarının farklı adlandırılmış sayaçlarını (created_students
 * ↔ created_personnel) tek şekle indirger — rapor bileşeni türden bağımsız kalır.
 */
export function importCounts(report: ImportReport): {
  created: number;
  updated: number;
  unchanged: number;
} {
  if ("created_students" in report) {
    return {
      created: report.created_students,
      updated: report.updated_students,
      unchanged: report.unchanged_students,
    };
  }
  return {
    created: report.created_personnel,
    updated: report.updated_personnel,
    unchanged: report.unchanged_personnel,
  };
}

/** Şablon dosya adları — indirme sırasında tarayıcıya verilir (backend ile aynı). */
export const STUDENT_TEMPLATE_FILENAME = "sablon-ogrenci.xlsx";
export const PERSONNEL_TEMPLATE_FILENAME = "sablon-personel.xlsx";

// ---------------------------------------------------------------------------
// Yardımcılar
// ---------------------------------------------------------------------------

/** Parça yoksa yolu olduğu gibi bırakır (gereksiz "?" üretmez). */
function withQuery(path: string, parts: string[]): string {
  return parts.length > 0 ? `${path}?${parts.join("&")}` : path;
}

/** Düz dizi dönen uçları da sayfalama zarfına indirger (tek tüketim şekli). */
function asPage<T>(data: Paginated<T> | T[]): Paginated<T> {
  return Array.isArray(data)
    ? { count: data.length, next: null, previous: null, results: data }
    : data;
}

/** Dosya yolu multipart (`file`), metin yolu JSON (`text`) — backend tam olarak birini bekler. */
function importRequest<R>(path: string, input: ImportInput): Promise<R> {
  if ("file" in input) {
    const form = new FormData();
    form.append("file", input.file);
    return api.postForm<R>(path, form);
  }
  return api.post<R>(path, { text: input.text });
}

export const okulApi = {
  // --- Kurulum sihirbazı ---

  getSetupStatus: (): Promise<SetupStatus> => api.get<SetupStatus>("/setup/status/"),

  getSchoolConfig: (): Promise<SchoolConfig> => api.get<SchoolConfig>("/setup/school-config/"),

  /** Kısmi gövde gönderilebilir — backend MERGE eder (verilmeyen alan korunur). */
  updateSchoolConfig: (body: SchoolConfigBody): Promise<SchoolConfig> =>
    api.put<SchoolConfig>("/setup/school-config/", body),

  completeSetup: (): Promise<{ setup_completed: boolean }> =>
    api.post<{ setup_completed: boolean }>("/setup/complete/"),

  /** Öğrenim seviyeleri — sicilden türetilir; sicil boşken lise varsayılanı döner. */
  getGradeLevels: (): Promise<GradeLevelsResponse> => fetchGradeLevels(),

  // --- Ders yılları ---

  /** Ders yıllarını listeler (DRF sayfalı yanıt → düz dizi). */
  listSchoolYears: async (): Promise<SchoolYear[]> => {
    const data = await api.get<Paginated<SchoolYear>>("/school-years/?limit=200");
    return unwrap(data);
  },

  /** Yeni ders yılı oluşturur (pasif doğar; aktivasyon ayrı uçtan). */
  createSchoolYear: (body: SchoolYearCreateBody): Promise<SchoolYear> =>
    api.post<SchoolYear>("/school-years/", body),

  /** Ders yılını aktifleştirir — backend diğerlerini pasifler. */
  activateSchoolYear: (id: number): Promise<SchoolYear> =>
    api.post<SchoolYear>(`/school-years/${id}/activate/`),

  listSchoolTerms: (schoolYearId: number): Promise<SchoolTerm[]> =>
    api.get<SchoolTerm[]>(`/school-years/${schoolYearId}/terms/`),

  configureSchoolTerms: (
    schoolYearId: number,
    body: SchoolTermConfigurationBody,
  ): Promise<SchoolTerm[]> => api.put<SchoolTerm[]>(`/school-years/${schoolYearId}/terms/`, body),

  // --- Tatiller ---

  listHolidays: async (): Promise<Holiday[]> => {
    const data = await api.get<Paginated<Holiday> | Holiday[]>("/holidays/?limit=500");
    return unwrap(data);
  },

  createHoliday: (body: HolidayCreateBody): Promise<Holiday> =>
    api.post<Holiday>("/holidays/", body),

  deleteHoliday: (id: number): Promise<void> => api.del<void>(`/holidays/${id}/`),

  /** Yıl verilmezse backend aktif ders yılını kullanır (aktif yıl yoksa 400). */
  seedHolidays: (schoolYearId?: number | null): Promise<HolidaySeedResult> =>
    api.post<HolidaySeedResult>(
      "/holidays/seed/",
      schoolYearId === undefined || schoolYearId === null ? {} : { school_year: schoolYearId },
    ),

  // --- Öğrenciler ---

  listStudents: async (params: StudentListParams = {}): Promise<Paginated<Student>> => {
    const parts: string[] = [];
    if (params.search?.trim()) parts.push(`search=${encodeURIComponent(params.search.trim())}`);
    if (params.classLevel !== undefined && params.classLevel !== null) {
      parts.push(`class_level=${params.classLevel}`);
    }
    if (params.classSection?.trim()) {
      parts.push(`class_section=${encodeURIComponent(params.classSection.trim())}`);
    }
    if (params.limit !== undefined) parts.push(`limit=${params.limit}`);
    if (params.offset) parts.push(`offset=${params.offset}`);
    const data = await api.get<Paginated<Student> | Student[]>(withQuery("/students/", parts));
    return asPage(data);
  },

  getStudent: (id: number): Promise<Student> => api.get<Student>(`/students/${id}/`),

  createStudent: (body: StudentWriteBody): Promise<Student> =>
    api.post<Student>("/students/", body),

  updateStudent: (id: number, body: Partial<StudentWriteBody>): Promise<Student> =>
    api.patch<Student>(`/students/${id}/`, body),

  deleteStudent: (id: number): Promise<void> => api.del<void>(`/students/${id}/`),

  // --- Personel ---

  listPersonnel: async (params: PersonnelListParams = {}): Promise<Paginated<Personnel>> => {
    const parts: string[] = [];
    if (params.search?.trim()) parts.push(`search=${encodeURIComponent(params.search.trim())}`);
    if (params.limit !== undefined) parts.push(`limit=${params.limit}`);
    if (params.offset) parts.push(`offset=${params.offset}`);
    const data = await api.get<Paginated<Personnel> | Personnel[]>(withQuery("/personnel/", parts));
    return asPage(data);
  },

  getPersonnel: (id: number): Promise<Personnel> => api.get<Personnel>(`/personnel/${id}/`),

  createPersonnel: (body: PersonnelWriteBody): Promise<Personnel> =>
    api.post<Personnel>("/personnel/", body),

  updatePersonnel: (id: number, body: Partial<PersonnelWriteBody>): Promise<Personnel> =>
    api.patch<Personnel>(`/personnel/${id}/`, body),

  deletePersonnel: (id: number): Promise<void> => api.del<void>(`/personnel/${id}/`),

  // --- Sınıf sorumlulukları ---

  listClassResponsibilities: async (schoolYear?: number): Promise<ClassResponsibility[]> => {
    const path =
      schoolYear === undefined
        ? "/class-responsibilities/?limit=500"
        : `/class-responsibilities/?school_year=${schoolYear}&limit=500`;
    const data = await api.get<Paginated<ClassResponsibility> | ClassResponsibility[]>(path);
    return unwrap(data);
  },

  createClassResponsibility: (body: ClassResponsibilityWriteBody): Promise<ClassResponsibility> =>
    api.post<ClassResponsibility>("/class-responsibilities/", body),

  updateClassResponsibility: (
    id: number,
    body: Partial<ClassResponsibilityWriteBody>,
  ): Promise<ClassResponsibility> =>
    api.patch<ClassResponsibility>(`/class-responsibilities/${id}/`, body),

  deleteClassResponsibility: (id: number): Promise<void> =>
    api.del<void>(`/class-responsibilities/${id}/`),

  // --- İçe aktarma (önizleme hiçbir şey yazmaz; commit gerçek yazar) ---

  previewStudentImport: (input: ImportInput): Promise<StudentImportReport> =>
    importRequest<StudentImportReport>("/imports/students/preview/", input),

  commitStudentImport: (input: ImportInput): Promise<StudentImportReport> =>
    importRequest<StudentImportReport>("/imports/students/commit/", input),

  previewPersonnelImport: (input: ImportInput): Promise<PersonnelImportReport> =>
    importRequest<PersonnelImportReport>("/imports/personnel/preview/", input),

  commitPersonnelImport: (input: ImportInput): Promise<PersonnelImportReport> =>
    importRequest<PersonnelImportReport>("/imports/personnel/commit/", input),

  // --- Şablon indirme (xlsx blob) ---

  studentTemplate: (): Promise<Blob> => api.getBlob("/templates/students/"),

  personnelTemplate: (): Promise<Blob> => api.getBlob("/templates/personnel/"),
};
