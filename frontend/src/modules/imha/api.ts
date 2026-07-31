// md. 157/7 imha aracı API katmanı — backend apps/disiplin/views_purge.py 1:1 yansıması.
//
// Akış (backend services/purge.py): önizleme → tutanak (BİRİNCİ onay, jeton döner)
// → uygula (İKİNCİ onay, jetonla). Tutanak ucu PDF döndürür ve jetonu
// `X-Imha-Token` BAŞLIĞINDA taşır; `lib/api.ts::postBlob` başlıkları açığa
// çıkarmadığından burada küçük bir `fetch` sarmalayıcı kullanılır (ApiError
// sözleşmesi aynen korunur).

import { api, API_BASE, ApiError } from "../../lib/api";

// --- Veri modelleri (backend payload'larıyla birebir) ---

export interface PurgeCaseItem {
  case_id: number;
  case_no: string;
  petition_date: string;
  closed_on: string | null;
  students: string[];
  warning_count: number;
  warning_letter_count: number;
  document_count: number;
  event_count: number;
  attachment_count: number;
  participant_count: number;
  /** Dilekçe tarihi HÂLÂ SÜREN ders yılına düşüyor — md. 157/7-d "ders yılı sonunda" uyarısı. */
  in_active_school_year: boolean;
}

export interface PurgeStudentSummary {
  student_id: number;
  full_name: string;
  class_label: string;
  status: string;
  warning_count: number;
}

export interface PurgePreview {
  cases: PurgeCaseItem[];
  students: PurgeStudentSummary[];
  totals: { cases: number; warnings: number; documents: number; attachments: number };
  active_school_year_name: string;
  active_school_year_end: string | null;
}

export interface PurgeWarningItem {
  warning_id: number;
  case_id: number;
  case_no: string;
  student_id: number;
  student_name: string;
  warning_date: string;
  warning_letter_count: number;
  whole_case_purgeable: boolean;
}

export interface StudentPurgePreview {
  student_id: number;
  student_name: string;
  class_label: string;
  warnings: PurgeWarningItem[];
  whole_case_ids: number[];
  totals: { warnings: number; documents: number; cases: number };
  transfer_date: string | null;
  /** md. 157/7-d: nakil tarihi + 5 iş günü. Nakil tarihi girilmezse null. */
  purge_deadline: string | null;
  working_days_left: number | null;
  overdue: boolean;
}

export interface PurgeRecordResult {
  blob: Blob;
  filename: string;
  /** İkinci onayı açan imzalı jeton — tutanak üretilmeden imha YAPILAMAZ. */
  token: string;
  storedPath: string;
}

export interface PurgeExecuteResult {
  purged_cases: number;
  purged_warnings: number;
  purged_documents: number;
  purged_events: number;
  purged_attachments: number;
  purged_participants: number;
  record_path: string;
  case_numbers: string[];
}

interface RecordBody {
  case_ids?: number[];
  student_id?: number;
  nakil_tarihi?: string;
  imha_tarihi?: string;
}

/** Tutanak ucu: PDF gövdesi + `X-Imha-Token` başlığı birlikte okunur. */
async function postRecord(body: RecordBody): Promise<PurgeRecordResult> {
  const resp = await fetch(`${API_BASE}/disiplin/imha/tutanak/`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ...body, onay: true }),
  });
  if (!resp.ok) {
    let code = String(resp.status);
    let message = "İmha tutanağı üretilemedi.";
    let fields: Record<string, unknown> = {};
    try {
      const d = (await resp.json()) as {
        code?: string;
        message?: string;
        fields?: Record<string, unknown>;
      };
      code = d.code ?? code;
      message = d.message ?? message;
      fields = d.fields ?? {};
    } catch {
      /* boş gövde */
    }
    throw new ApiError(resp.status, code, message, fields);
  }
  const token = resp.headers.get("X-Imha-Token") ?? "";
  const storedPath = resp.headers.get("X-Imha-Tutanak-Yolu") ?? "";
  const blob = await resp.blob();
  const disposition = resp.headers.get("Content-Disposition") ?? "";
  const match = /filename="([^"]+)"/.exec(disposition);
  return { blob, token, storedPath, filename: match?.[1] ?? "imha-tutanagi.pdf" };
}

export const imhaApi = {
  /** Ders yılı sonu (toplu) imha önizlemesi. */
  preview: () => api.get<PurgePreview>("/disiplin/imha/onizleme/"),

  /** Nakil eden öğrencinin tekil imha önizlemesi (+5 iş günü göstergesi). */
  previewStudent: (studentId: number, transferDate?: string) => {
    const query = transferDate ? `?nakil_tarihi=${encodeURIComponent(transferDate)}` : "";
    return api.get<StudentPurgePreview>(`/disiplin/imha/onizleme/ogrenci/${studentId}/${query}`);
  },

  /** BİRİNCİ onay: tutanak PDF'i üretir (jetonla döner). */
  recordForCases: (caseIds: number[]) => postRecord({ case_ids: caseIds }),

  /** BİRİNCİ onay (nakil): tek öğrencinin izleri için tutanak. */
  recordForStudent: (studentId: number, transferDate?: string) =>
    postRecord({
      student_id: studentId,
      ...(transferDate ? { nakil_tarihi: transferDate } : {}),
    }),

  /** İKİNCİ onay: jetonla imhayı uygular (geri alınamaz). */
  execute: (token: string) =>
    api.post<PurgeExecuteResult>("/disiplin/imha/uygula/", { token, onay: true }),
};
