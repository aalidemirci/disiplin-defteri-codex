// Disiplin API katmanı — uç yolları + tel-anahtarı çevirileri (smoke).
// Backend apps/disiplin/urls.py + views.py ile birebir hizalı olduğunu doğrular.
// OYS api.test.ts uyarlaması: kurul gövdesi model alanlarıyla (school_year/chair),
// `student_id`→`student`, `participant_id`→`participant`, `parent_document_id`→
// `parent_document`, `committee_decision_type_id`→`committee_decision_type`
// çevirileri ve 204/zarf şimleri BURADA pinlenir.

import { afterEach, describe, expect, it, vi } from "vitest";

const apiMock = vi.hoisted(() => ({
  get: vi.fn(() => Promise.resolve({})),
  post: vi.fn(() => Promise.resolve({})),
  put: vi.fn(() => Promise.resolve({})),
  patch: vi.fn(() => Promise.resolve({})),
  del: vi.fn(() => Promise.resolve(undefined)),
  postForm: vi.fn(() => Promise.resolve({})),
  getBlob: vi.fn(() => Promise.resolve(new Blob())),
  postBlob: vi.fn(() => Promise.resolve(new Blob())),
}));

vi.mock("../../lib/api", () => ({
  api: apiMock,
  ApiError: class ApiError extends Error {},
}));

import {
  categorizeDocuments,
  disiplinApi,
  documentDisplayName,
  GENERATABLE_DOCUMENT_TYPES,
  INFO_GATHERING_SOURCES,
  personnelLookupApi,
  studentLookupApi,
} from "./api";
import type { DocumentType, GeneratedDocument } from "./api";

afterEach(() => vi.clearAllMocks());

// Test için minimal GeneratedDocument üreticisi (kategori/kimden testleri).
function doc(
  over: Partial<GeneratedDocument> & { document_type: DocumentType },
): GeneratedDocument {
  return {
    id: 1,
    student: null,
    document_type_display: "x",
    title: "Başlık",
    document_no: "",
    source_label: "",
    source_name: "",
    generated_on: "2026-05-26",
    notes: "",
    page_count: 1,
    has_stored_pdf: false,
    stored_pdf_size: 0,
    stored_filename: "",
    parent_document: null,
    sort_order: 0,
    created_at: "2026-05-26",
    ...over,
  };
}

describe("disiplinApi — dosya + liste uçları", () => {
  it("listCases → GET /discipline/cases/ sunucu-taraflı stage/search filtresi", async () => {
    apiMock.get.mockResolvedValueOnce({ count: 0, next: null, previous: null, results: [] });
    await disiplinApi.listCases({ stage: "PETITION", search: "ali" });
    expect(apiMock.get).toHaveBeenCalledWith(
      "/discipline/cases/?limit=200&stage=PETITION&search=ali",
    );
  });

  it("listCases onlyOpen → kapalı dosyalar istemcide süzülür", async () => {
    apiMock.get.mockResolvedValueOnce({
      count: 2,
      next: null,
      previous: null,
      results: [
        { id: 1, closed_at: null },
        { id: 2, closed_at: "2026-05-26T10:00:00Z" },
      ],
    });
    const items = await disiplinApi.listCases({ onlyOpen: true });
    expect(items.map((c) => c.id)).toEqual([1]);
  });

  it("addEvent → committee_decision_type_id teli committee_decision_type olur", () => {
    disiplinApi.addEvent(5, {
      stage: "COMMITTEE_DONE",
      event_date: "2026-05-26",
      committee_decision_type_id: 3,
      committee_decision_text: "Kınama verildi.",
    });
    expect(apiMock.post).toHaveBeenCalledWith("/discipline/cases/5/events/", {
      stage: "COMMITTEE_DONE",
      event_date: "2026-05-26",
      committee_decision_type: 3,
      committee_decision_text: "Kınama verildi.",
    });
  });

  it("addEvent → rehberlik sevki assigned_guidance_name serbest metniyle gider", () => {
    disiplinApi.addEvent(5, {
      stage: "GUIDANCE_REFERRED",
      event_date: "2026-05-20",
      assigned_guidance_name: "Ayşe Yılmaz",
    });
    expect(apiMock.post).toHaveBeenCalledWith("/discipline/cases/5/events/", {
      stage: "GUIDANCE_REFERRED",
      event_date: "2026-05-20",
      assigned_guidance_name: "Ayşe Yılmaz",
    });
  });

  it("uploadAttachment → multipart 'event' anahtarı + düz yanıt", async () => {
    const file = new File(["x"], "dilekce.pdf", { type: "application/pdf" });
    await disiplinApi.uploadAttachment(5, file, "PETITION_SCAN", 9);
    const [path, fd] = apiMock.postForm.mock.calls[0] as unknown as [string, FormData];
    expect(path).toBe("/discipline/cases/5/attachments/");
    expect(fd.get("file_type")).toBe("PETITION_SCAN");
    expect(fd.get("event")).toBe("9");
  });
});

describe("disiplinApi — karar tipleri", () => {
  it("listDecisionTypes varsayılanı yalnız AKTİF tipleri ister", async () => {
    apiMock.get.mockResolvedValueOnce({ count: 0, next: null, previous: null, results: [] });
    await disiplinApi.listDecisionTypes();
    expect(apiMock.get).toHaveBeenCalledWith("/discipline/decision-types/?limit=200");
  });

  it("includeInactive → all=1 ile pasif tipler de gelir (yeniden aktifleştirme yolu)", async () => {
    apiMock.get.mockResolvedValueOnce({ count: 0, next: null, previous: null, results: [] });
    await disiplinApi.listDecisionTypes({ includeInactive: true });
    expect(apiMock.get).toHaveBeenCalledWith("/discipline/decision-types/?limit=200&all=1");
  });
});

describe("disiplinApi — kurul uçları", () => {
  it("getCommittee → GET /discipline/committee/; 204 → {committee: null} zarfı", async () => {
    apiMock.get.mockResolvedValueOnce(undefined as never);
    const out = await disiplinApi.getCommittee();
    expect(apiMock.get).toHaveBeenCalledWith("/discipline/committee/");
    expect(out).toEqual({ committee: null });
  });

  it("createCommittee → model alan adlarıyla gövde (school_year/chair)", () => {
    disiplinApi.createCommittee({ school_year_id: 1, chair_id: 7, notes: "n" });
    expect(apiMock.post).toHaveBeenCalledWith("/discipline/committee/", {
      school_year: 1,
      chair: 7,
      notes: "n",
    });
  });

  it("setCommitteeChair → POST /discipline/committee/chair/ {chair}", () => {
    disiplinApi.setCommitteeChair({ chair_id: 9 });
    expect(apiMock.post).toHaveBeenCalledWith("/discipline/committee/chair/", { chair: 9 });
  });

  it("addCommitteeMember → POST /discipline/committee/members/ (veli snapshot dahil)", () => {
    disiplinApi.addCommitteeMember({ member_type: "PARENT", member_name: "Hasan Veli" });
    expect(apiMock.post).toHaveBeenCalledWith("/discipline/committee/members/", {
      member_type: "PARENT",
      member_name: "Hasan Veli",
    });
  });

  it("removeCommitteeMember → DELETE /discipline/committee/members/<id>/", () => {
    disiplinApi.removeCommitteeMember(42);
    expect(apiMock.del).toHaveBeenCalledWith("/discipline/committee/members/42/");
  });

  it("listMeetings / recordMeeting → /discipline/cases/<id>/meeting/", () => {
    disiplinApi.listMeetings(5);
    expect(apiMock.get).toHaveBeenCalledWith("/discipline/cases/5/meeting/");
    disiplinApi.recordMeeting(5, { meeting_date: "2026-05-29", attendee_member_ids: [1, 2] });
    expect(apiMock.post).toHaveBeenCalledWith("/discipline/cases/5/meeting/", {
      meeting_date: "2026-05-29",
      attendee_member_ids: [1, 2],
    });
  });
});

describe("disiplinApi — katılımcı + uyarı + triaj uçları", () => {
  it("addParticipant → POST /discipline/cases/<id>/participants/ + gövde", () => {
    disiplinApi.addParticipant(8, { role: "WITNESS", person_type: "STUDENT", person_id: 12 });
    expect(apiMock.post).toHaveBeenCalledWith("/discipline/cases/8/participants/", {
      role: "WITNESS",
      person_type: "STUDENT",
      person_id: 12,
    });
  });

  it("removeParticipant → DELETE /discipline/cases/<id>/participants/<prt>/", () => {
    disiplinApi.removeParticipant(8, 3);
    expect(apiMock.del).toHaveBeenCalledWith("/discipline/cases/8/participants/3/");
  });

  it("addWarning → student_id teli 'student' olur", () => {
    disiplinApi.addWarning(8, { student_id: 12, warning_date: "2026-05-30", summary: "uyarı" });
    expect(apiMock.post).toHaveBeenCalledWith("/discipline/cases/8/warnings/", {
      student: 12,
      warning_date: "2026-05-30",
      summary: "uyarı",
    });
  });

  it("triageSuggestion → düz liste OYS zarfına çevrilir (any → özet bayrak)", async () => {
    apiMock.get.mockResolvedValueOnce([
      { student_id: 1, warning_count: 0, penalty_count: 0, should_route_to_committee: false },
      { student_id: 2, warning_count: 2, penalty_count: 1, should_route_to_committee: true },
    ]);
    const out = await disiplinApi.triageSuggestion(8);
    expect(apiMock.get).toHaveBeenCalledWith("/discipline/cases/8/triage-suggestion/");
    expect(out.students).toHaveLength(2);
    expect(out.should_route_to_committee).toBe(true);
  });
});

describe("disiplinApi — karar + itiraz + anlatı uçları", () => {
  it("createDecision → student_id teli 'student' olur", () => {
    disiplinApi.createDecision(8, {
      student_id: 12,
      penalty_type: "REPRIMAND",
      decision_date: "2026-05-30",
    });
    expect(apiMock.post).toHaveBeenCalledWith("/discipline/cases/8/decisions/", {
      student: 12,
      penalty_type: "REPRIMAND",
      decision_date: "2026-05-30",
    });
  });

  it("listDecisions → GET /discipline/cases/<id>/decisions/ ({decisions, behavior_points})", () => {
    disiplinApi.listDecisions(8);
    expect(apiMock.get).toHaveBeenCalledWith("/discipline/cases/8/decisions/");
  });

  it("updateDecision → PATCH /discipline/cases/<id>/decisions/<did>/", () => {
    disiplinApi.updateDecision(8, 3, { penalty_type: "REPRIMAND", decision_date: "2026-05-30" });
    expect(apiMock.patch).toHaveBeenCalledWith("/discipline/cases/8/decisions/3/", {
      penalty_type: "REPRIMAND",
      decision_date: "2026-05-30",
    });
  });

  it("delete/restore/deleted → karar çöp kutusu uçları", () => {
    disiplinApi.deleteDecision(8, 3);
    expect(apiMock.del).toHaveBeenCalledWith("/discipline/cases/8/decisions/3/");
    disiplinApi.restoreDecision(8, 3);
    expect(apiMock.post).toHaveBeenCalledWith("/discipline/cases/8/decisions/3/restore/");
    disiplinApi.listDeletedDecisions(8);
    expect(apiMock.get).toHaveBeenCalledWith("/discipline/cases/8/decisions/deleted/");
  });

  it("revertStage → POST /discipline/cases/<id>/revert-stage/", () => {
    disiplinApi.revertStage(8, { target_stage: "PETITION", reason: "Düzeltme." });
    expect(apiMock.post).toHaveBeenCalledWith("/discipline/cases/8/revert-stage/", {
      target_stage: "PETITION",
      reason: "Düzeltme.",
    });
  });

  it("closeCase → POST /discipline/cases/<id>/close/ (override gövdesi dahil)", () => {
    disiplinApi.closeCase(8);
    expect(apiMock.post).toHaveBeenCalledWith("/discipline/cases/8/close/", {});
    disiplinApi.closeCase(8, { override: true, override_reason: "PTT tebligatı." });
    expect(apiMock.post).toHaveBeenCalledWith("/discipline/cases/8/close/", {
      override: true,
      override_reason: "PTT tebligatı.",
    });
  });

  it("approve/review/notify/narrative → karar eylem uçları", () => {
    disiplinApi.approveDecision(8, 3, { approval_status: "APPROVED", approved_on: "2026-05-30" });
    expect(apiMock.post).toHaveBeenCalledWith("/discipline/cases/8/decisions/3/approve/", {
      approval_status: "APPROVED",
      approved_on: "2026-05-30",
    });
    disiplinApi.reviewDecision(8, 3, {
      action: "RETURN",
      reason: "Gerekçe.",
      decided_on: "2026-05-30",
    });
    expect(apiMock.post).toHaveBeenCalledWith("/discipline/cases/8/decisions/3/review/", {
      action: "RETURN",
      reason: "Gerekçe.",
      decided_on: "2026-05-30",
    });
    disiplinApi.notifyDecision(8, 3, { notified_on: "2026-05-30" });
    expect(apiMock.post).toHaveBeenCalledWith("/discipline/cases/8/decisions/3/notify/", {
      notified_on: "2026-05-30",
    });
    disiplinApi.updateDecisionNarrative(8, 3, { committee_opinion: "kanaat" });
    expect(apiMock.post).toHaveBeenCalledWith("/discipline/cases/8/decisions/3/narrative/", {
      committee_opinion: "kanaat",
    });
  });

  it("itiraz uçları → file/forward/resolve", () => {
    disiplinApi.fileAppeal(8, 3, { filed_on: "2026-05-30", filed_by_role: "PARENT" });
    expect(apiMock.post).toHaveBeenCalledWith("/discipline/cases/8/decisions/3/appeals/", {
      filed_on: "2026-05-30",
      filed_by_role: "PARENT",
    });
    disiplinApi.forwardAppeal(8, 5, { forwarded_on: "2026-05-31" });
    expect(apiMock.post).toHaveBeenCalledWith("/discipline/cases/8/appeals/5/forward/", {
      forwarded_on: "2026-05-31",
    });
    disiplinApi.resolveAppeal(8, 5, { result: "UPHELD", resulted_on: "2026-06-01" });
    expect(apiMock.post).toHaveBeenCalledWith("/discipline/cases/8/appeals/5/resolve/", {
      result: "UPHELD",
      resulted_on: "2026-06-01",
    });
  });

  it("itiraz listesi ayrı uçtan ÇEKİLMEZ — karar yanıtına gömülü gelir", () => {
    // `listDecisions` her kararın `appeals` dizisini döndürür (serializer'da
    // AppealSerializer gömülü); ayrı bir listAppeals istemcisi ölü yüzeydi.
    expect(disiplinApi).not.toHaveProperty("listAppeals");
  });
});

describe("disiplinApi — uzatma + tedbir uçları", () => {
  it("listExtensions / createExtension → /discipline/cases/<id>/extensions/", () => {
    disiplinApi.listExtensions(8);
    expect(apiMock.get).toHaveBeenCalledWith("/discipline/cases/8/extensions/");
    disiplinApi.createExtension(8, {
      requested_days: 10,
      reason: "gerekçe",
      decided_on: "2026-05-30",
    });
    expect(apiMock.post).toHaveBeenCalledWith("/discipline/cases/8/extensions/", {
      requested_days: 10,
      reason: "gerekçe",
      decided_on: "2026-05-30",
    });
  });

  it("approveExtension → POST /discipline/cases/<id>/extensions/<ext>/approve/", () => {
    disiplinApi.approveExtension(8, 2, { approved_on: "2026-05-31" });
    expect(apiMock.post).toHaveBeenCalledWith("/discipline/cases/8/extensions/2/approve/", {
      approved_on: "2026-05-31",
    });
  });

  it("createPrecaution → student_id teli 'student' olur", () => {
    disiplinApi.createPrecaution(8, {
      student_id: 12,
      start_date: "2026-05-30",
      requested_days: 5,
    });
    expect(apiMock.post).toHaveBeenCalledWith("/discipline/cases/8/precautions/", {
      student: 12,
      start_date: "2026-05-30",
      requested_days: 5,
    });
  });

  it("lift/extend → tedbir eylem uçları", () => {
    disiplinApi.liftPrecaution(8, 4, { lifted_on: "2026-06-02", expired: true });
    expect(apiMock.post).toHaveBeenCalledWith("/discipline/cases/8/precautions/4/lift/", {
      lifted_on: "2026-06-02",
      expired: true,
    });
    disiplinApi.extendPrecaution(8, 4, { additional_days: 3, mne_notified: true });
    expect(apiMock.post).toHaveBeenCalledWith("/discipline/cases/8/precautions/4/extend/", {
      additional_days: 3,
      mne_notified: true,
    });
  });
});

describe("disiplinApi — evrak üretimi + kütük", () => {
  it("generateDocument → student_id teli 'student' olur (blob)", () => {
    disiplinApi.generateDocument(8, {
      document_type: "COMMITTEE_DECISION",
      generated_on: "2026-05-30",
      student_id: 12,
    });
    expect(apiMock.postBlob).toHaveBeenCalledWith("/discipline/cases/8/documents/generate/", {
      document_type: "COMMITTEE_DECISION",
      generated_on: "2026-05-30",
      student: 12,
    });
  });

  it("generateDocument → participant_id teli 'participant'; geçici alanlar aynen", () => {
    disiplinApi.generateDocument(8, {
      document_type: "STATEMENT_RECORD",
      generated_on: "2026-05-30",
      participant_id: 4,
      statement_subject: "Olay",
      statement_body: "İfade metni",
    });
    expect(apiMock.postBlob).toHaveBeenCalledWith("/discipline/cases/8/documents/generate/", {
      document_type: "STATEMENT_RECORD",
      generated_on: "2026-05-30",
      participant: 4,
      statement_subject: "Olay",
      statement_body: "İfade metni",
    });
  });

  it("generateDocument → Form-02 behavior_summary + veli sürümü gövdede taşınır", () => {
    disiplinApi.generateDocument(8, {
      document_type: "WARNING_LETTER",
      generated_on: "2026-06-10",
      recipient: "parent",
      student_id: 12,
      behavior_summary: "Derse sürekli geç kalma.",
    });
    expect(apiMock.postBlob).toHaveBeenCalledWith("/discipline/cases/8/documents/generate/", {
      document_type: "WARNING_LETTER",
      generated_on: "2026-06-10",
      recipient: "parent",
      student: 12,
      behavior_summary: "Derse sürekli geç kalma.",
    });
  });

  it("addDocument → student_id/parent_document_id telleri model alanları olur", () => {
    disiplinApi.addDocument(8, {
      document_type: "OTHER",
      title: "delil",
      generated_on: "2026-05-30",
      page_count: 2,
      student_id: 12,
      parent_document_id: 5,
    });
    expect(apiMock.post).toHaveBeenCalledWith("/discipline/cases/8/documents/", {
      document_type: "OTHER",
      title: "delil",
      generated_on: "2026-05-30",
      page_count: 2,
      student: 12,
      parent_document: 5,
    });
  });

  it("reorderDocuments → PATCH …/documents/reorder/ + document_ids", () => {
    disiplinApi.reorderDocuments(8, [3, 1, 2]);
    expect(apiMock.patch).toHaveBeenCalledWith("/discipline/cases/8/documents/reorder/", {
      document_ids: [3, 1, 2],
    });
  });

  it("update/delete/restore/deleted → kütük yönetim uçları", () => {
    disiplinApi.updateDocument(8, 12, { page_count: 4, source_label: "Tanık" });
    expect(apiMock.patch).toHaveBeenCalledWith("/discipline/cases/8/documents/12/", {
      page_count: 4,
      source_label: "Tanık",
    });
    disiplinApi.deleteDocument(8, 5);
    expect(apiMock.del).toHaveBeenCalledWith("/discipline/cases/8/documents/5/");
    disiplinApi.restoreDocument(8, 5);
    expect(apiMock.post).toHaveBeenCalledWith("/discipline/cases/8/documents/5/restore/");
    disiplinApi.listDeletedDocuments(8);
    expect(apiMock.get).toHaveBeenCalledWith("/discipline/cases/8/documents/deleted/");
    disiplinApi.downloadStoredDocument(8, 5);
    expect(apiMock.getBlob).toHaveBeenCalledWith("/discipline/cases/8/documents/5/download/");
  });

  it("getIndexSheet → GET(blob) …/documents/index-sheet/ (kütüğe yazmaz)", () => {
    disiplinApi.getIndexSheet(8);
    expect(apiMock.getBlob).toHaveBeenCalledWith("/discipline/cases/8/documents/index-sheet/");
  });

  it("GENERATABLE_DOCUMENT_TYPES — karar-sonrası yazılar + recipient bayrağı", () => {
    const byValue = Object.fromEntries(GENERATABLE_DOCUMENT_TYPES.map((t) => [t.value, t]));
    for (const v of [
      "PENALTY_DAYS_NOTICE",
      "APPEAL_LETTER",
      "WARNING_LETTER",
      "PRECAUTION_NOTICE",
    ]) {
      expect(byValue[v]).toBeDefined();
      expect(byValue[v].studentRequired).toBe(true);
    }
    expect(byValue.PENALTY_NOTICE.recipientSelectable).toBe(true);
    expect(byValue.PENALTY_DAYS_NOTICE.recipientSelectable).toBe(true);
    expect(byValue.APPEAL_LETTER.recipientSelectable).toBeUndefined();
    // Dizi pusulası "Belge üret" akışında YOK (ayrı buton + ayrı uç).
    expect(byValue.INDEX_SHEET).toBeUndefined();
  });

  it("GENERATABLE_DOCUMENT_TYPES — Dal B ifade/savunma/bilgi formları", () => {
    const byValue = Object.fromEntries(GENERATABLE_DOCUMENT_TYPES.map((t) => [t.value, t]));
    for (const v of [
      "STATEMENT_CALL",
      "STATEMENT_RECORD",
      "INFO_GATHERING",
      "DEFENSE_CALL",
      "MEETING_CALL",
      "DEFENSE_RECORD",
    ]) {
      expect(byValue[v]).toBeDefined();
    }
    expect(byValue.STATEMENT_CALL.participantRequired).toBe(true);
    expect(byValue.STATEMENT_CALL.studentRequired).toBe(false);
    expect(byValue.STATEMENT_CALL.scheduling).toBe(true);
    expect(byValue.MEETING_CALL.scheduling).toBe(true);
    expect(byValue.MEETING_CALL.participantRequired).toBeUndefined();
    expect(byValue.INFO_GATHERING.variantOptions).toHaveLength(2);
    expect(byValue.INFO_GATHERING.participantRoleFilter).toContain("ACCUSED");
    expect(byValue.DEADLINE_EXTENSION.variantOptions).toHaveLength(2);
    expect(byValue.DEADLINE_EXTENSION.studentRequired).toBe(false);
  });

  it("STATEMENT_RECORD + DEFENSE_RECORD — dolu-bas bayrakları", () => {
    const byValue = Object.fromEntries(GENERATABLE_DOCUMENT_TYPES.map((t) => [t.value, t]));
    expect(byValue.STATEMENT_RECORD.freeformStatement).toBe(true);
    expect(byValue.STATEMENT_RECORD.freeformStatementLabels).toBeUndefined();
    expect(byValue.DEFENSE_RECORD.freeformStatement).toBe(true);
    expect(byValue.DEFENSE_RECORD.freeformStatementLabels).toEqual({
      subject: "Olay / Konu",
      body: "Savunma metni",
    });
    expect(byValue.STATEMENT_CALL.freeformStatement).toBeUndefined();
    expect(byValue.INFO_GATHERING.freeformStatement).toBeUndefined();
  });

  it("BOARD_DECISION_NOTICE — üst kurul kararı tebliği", () => {
    const byValue = Object.fromEntries(GENERATABLE_DOCUMENT_TYPES.map((t) => [t.value, t]));
    const meta = byValue.BOARD_DECISION_NOTICE;
    expect(meta).toBeDefined();
    expect(meta.studentRequired).toBe(true);
    expect(meta.recipientSelectable).toBe(true);
    expect(meta.boardDecisionNotice).toBe(true);
    const order = GENERATABLE_DOCUMENT_TYPES.map((t) => t.value);
    expect(order.indexOf("BOARD_DECISION_NOTICE")).toBe(order.indexOf("APPEAL_LETTER") + 1);
  });
});

describe("disiplin — dizi pusulası kategori + kimden", () => {
  it("categorizeDocuments türe göre gruplar, boşları atlar, sabit sırayı korur", () => {
    const docs = [
      doc({ id: 1, document_type: "COMMITTEE_DECISION", title: "EK-1" }),
      doc({
        id: 2,
        document_type: "STATEMENT_RECORD",
        source_label: "Hakkında İşlem Yapılan",
        source_name: "Ahmet",
      }),
    ];
    const labels = categorizeDocuments(docs).map((c) => c.label);
    expect(labels).toContain("İfadeler");
    expect(labels).toContain("Kurul Kararı");
    expect(labels.indexOf("İfadeler")).toBeLessThan(labels.indexOf("Kurul Kararı"));
    expect(labels).not.toContain("Tebliğler");
  });

  it("documentDisplayName: kimden varsa 'sıfat: ad', source_name boşsa yalnız sıfat, yoksa başlık", () => {
    expect(
      documentDisplayName(
        doc({ document_type: "STATEMENT_RECORD", source_label: "Tanık", source_name: "Ali" }),
      ),
    ).toBe("Tanık: Ali");
    expect(
      documentDisplayName(
        doc({ document_type: "INFO_GATHERING", source_label: "Rehberlik Servisi" }),
      ),
    ).toBe("Rehberlik Servisi");
    expect(
      documentDisplayName(
        doc({ document_type: "PENALTY_NOTICE", title: "Disiplin Cezası Tebliği" }),
      ),
    ).toBe("Disiplin Cezası Tebliği");
  });

  it("INFO_GATHERING.sourceOptions — kaynak listesi", () => {
    const ig = GENERATABLE_DOCUMENT_TYPES.find((t) => t.value === "INFO_GATHERING");
    expect(ig?.sourceOptions).toEqual(INFO_GATHERING_SOURCES);
    expect(ig?.sourceOptions).toContain("Rehberlik Servisi");
  });
});

describe("kişi arama — okul modülü uçları", () => {
  it("studentLookupApi.search → GET /students/?search= + only_active süzgeci", async () => {
    // Seçiciler yalnız AKTİF öğrenci listeler (bulgu #10): okuldan ayrılmış
    // öğrenciye yeni dosya/katılımcı/karar bağlanamaz.
    apiMock.get.mockResolvedValueOnce({ count: 0, next: null, previous: null, results: [] });
    await studentLookupApi.search("ahmet ali");
    expect(apiMock.get).toHaveBeenCalledWith(
      "/students/?search=ahmet%20ali&limit=20&only_active=true",
    );
  });

  it("personnelLookupApi.search → GET /personnel/?search=", async () => {
    apiMock.get.mockResolvedValueOnce({ count: 0, next: null, previous: null, results: [] });
    await personnelLookupApi.search("yılmaz", 5);
    expect(apiMock.get).toHaveBeenCalledWith("/personnel/?search=y%C4%B1lmaz&limit=5");
  });
});
