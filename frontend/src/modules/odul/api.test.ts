// Ödül/Onur API katmanı — uç yolları + tel-anahtarı çevirileri (smoke).
// Backend apps/disiplin/urls.py (honor/*) + views.py ile birebir hizalı olduğunu doğrular.
// OYS api.test.ts uyarlaması (F4-D3): honors-lite'ta kalkan uçların (proposal-window/
// proposal-quota/proposal-limit, reject-student, mark-delivered, certificates/batch)
// testleri kalktı; kalanlarda `student_id`→`student`, `chair_id`→`chair`,
// `school_year_id`→`school_year` çevirileri + 204 zarf şimi BURADA pinlenir.

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
  criteriaDisplay,
  groupProposalsByProposer,
  HONOR_CRITERION_TR,
  HONOR_STATUS_TR,
  odulApi,
} from "./api";

afterEach(() => vi.clearAllMocks());

describe("odulApi — onur kurulu uçları (md. 180-184)", () => {
  it("getBoard → GET /honor/board/; 204 → {board: null} zarfı", async () => {
    apiMock.get.mockResolvedValueOnce(undefined as never);
    const out = await odulApi.getBoard();
    expect(apiMock.get).toHaveBeenCalledWith("/honor/board/");
    expect(out).toEqual({ board: null });
  });

  it("getBoard → tanımlı kurul zarfa sarılır", async () => {
    apiMock.get.mockResolvedValueOnce({ id: 3, school_year: 1, chair: 7, members: [] });
    const out = await odulApi.getBoard();
    expect(out.board?.id).toBe(3);
  });

  it("createBoard → model alan adlarıyla gövde (school_year/chair)", () => {
    odulApi.createBoard({ school_year_id: 1, chair_id: 7, notes: "n" });
    expect(apiMock.post).toHaveBeenCalledWith("/honor/board/", {
      school_year: 1,
      chair: 7,
      notes: "n",
    });
  });

  it("createBoard → notes verilmezse anahtar gönderilmez", () => {
    odulApi.createBoard({ school_year_id: 2, chair_id: 8 });
    expect(apiMock.post).toHaveBeenCalledWith("/honor/board/", { school_year: 2, chair: 8 });
  });

  it("setBoardChair → POST /honor/board/chair/ {chair} (OYS PUT idi)", () => {
    odulApi.setBoardChair({ chair_id: 9 });
    expect(apiMock.post).toHaveBeenCalledWith("/honor/board/chair/", { chair: 9 });
    expect(apiMock.put).not.toHaveBeenCalled();
  });

  it("addBoardMember → POST /honor/board/members/; student_id teli 'student' olur", () => {
    odulApi.addBoardMember({
      student_id: 12,
      grade_level: 11,
      is_second_chair: true,
      title: "İkinci başkan",
    });
    expect(apiMock.post).toHaveBeenCalledWith("/honor/board/members/", {
      student: 12,
      grade_level: 11,
      is_second_chair: true,
      title: "İkinci başkan",
    });
  });

  it("removeBoardMember → DELETE /honor/board/members/<id>/", () => {
    odulApi.removeBoardMember(42);
    expect(apiMock.del).toHaveBeenCalledWith("/honor/board/members/42/");
  });
});

describe("odulApi — onur belgesi uçları (md. 161 + 183/b)", () => {
  it("listCertificates → GET /honor/certificates/?limit=200 (filtresiz, sayfalı yanıt)", async () => {
    apiMock.get.mockResolvedValueOnce({ count: 0, next: null, previous: null, results: [] });
    const out = await odulApi.listCertificates();
    expect(apiMock.get).toHaveBeenCalledWith("/honor/certificates/?limit=200");
    expect(out).toEqual([]);
  });

  it("listCertificates → durum + öğrenci + yıl filtresi query'ye eklenir (student_id → student)", async () => {
    apiMock.get.mockResolvedValueOnce({ count: 0, next: null, previous: null, results: [] });
    await odulApi.listCertificates({ status: "AWARDED", studentId: 5, schoolYearId: 2 });
    expect(apiMock.get).toHaveBeenCalledWith(
      "/honor/certificates/?limit=200&status=AWARDED&student=5&school_year=2",
    );
  });

  it("getCertificate → GET /honor/certificates/<id>/", () => {
    odulApi.getCertificate(8);
    expect(apiMock.get).toHaveBeenCalledWith("/honor/certificates/8/");
  });

  it("proposeCertificate → student_id teli 'student' olur (tek kriter, md. 161)", () => {
    odulApi.proposeCertificate({
      student_id: 12,
      proposer_role: "TEACHER",
      criteria: ["LANGUAGE"],
      justification: "Gerekçe",
      proposer_name: "Ali Örnek",
    });
    expect(apiMock.post).toHaveBeenCalledWith("/honor/certificates/", {
      student: 12,
      proposer_role: "TEACHER",
      criteria: ["LANGUAGE"],
      justification: "Gerekçe",
      proposer_name: "Ali Örnek",
    });
  });

  it("proposeCertificate → school_year_id teli 'school_year' olur; null ise gönderilmez", () => {
    odulApi.proposeCertificate({
      student_id: 1,
      proposer_role: "STUDENT",
      criteria: ["MANNERS"],
      school_year_id: 4,
    });
    expect(apiMock.post).toHaveBeenLastCalledWith("/honor/certificates/", {
      student: 1,
      proposer_role: "STUDENT",
      criteria: ["MANNERS"],
      school_year: 4,
    });

    odulApi.proposeCertificate({
      student_id: 1,
      proposer_role: "STUDENT",
      criteria: ["MANNERS"],
      school_year_id: null,
    });
    expect(apiMock.post).toHaveBeenLastCalledWith("/honor/certificates/", {
      student: 1,
      proposer_role: "STUDENT",
      criteria: ["MANNERS"],
    });
  });

  it("recommendCertificate → POST /honor/certificates/<id>/recommend/", () => {
    odulApi.recommendCertificate(8, { recommended_on: "2026-05-26" });
    expect(apiMock.post).toHaveBeenCalledWith("/honor/certificates/8/recommend/", {
      recommended_on: "2026-05-26",
    });
  });

  it("awardCertificate → POST /honor/certificates/<id>/award/", () => {
    odulApi.awardCertificate(8, { awarded_on: "2026-05-27" });
    expect(apiMock.post).toHaveBeenCalledWith("/honor/certificates/8/award/", {
      awarded_on: "2026-05-27",
    });
  });

  it("rejectCertificate → POST /honor/certificates/<id>/reject/", () => {
    odulApi.rejectCertificate(8, { reason: "Yetersiz", decided_on: "2026-05-27" });
    expect(apiMock.post).toHaveBeenCalledWith("/honor/certificates/8/reject/", {
      reason: "Yetersiz",
      decided_on: "2026-05-27",
    });
  });
});

describe("odulApi — onur evrak uçları (3 PDF)", () => {
  it("proposalFormBlank → GET(blob) /honor/documents/proposal-form-blank/", () => {
    odulApi.proposalFormBlank();
    expect(apiMock.getBlob).toHaveBeenCalledWith("/honor/documents/proposal-form-blank/");
  });

  it("proposalForm → POST(blob) /honor/documents/proposal-form/ + id'ler", () => {
    odulApi.proposalForm([1, 2]);
    expect(apiMock.postBlob).toHaveBeenCalledWith("/honor/documents/proposal-form/", {
      certificate_ids: [1, 2],
    });
  });

  it("proposalForm → teklif eden adı verilirse gövdeye eklenir", () => {
    odulApi.proposalForm([1], "Ayşe Yılmaz");
    expect(apiMock.postBlob).toHaveBeenCalledWith("/honor/documents/proposal-form/", {
      certificate_ids: [1],
      proposer_name: "Ayşe Yılmaz",
    });
  });

  it("recommendationRecord → POST(blob) /honor/documents/recommendation-record/ + id'ler", () => {
    odulApi.recommendationRecord([3]);
    expect(apiMock.postBlob).toHaveBeenCalledWith("/honor/documents/recommendation-record/", {
      certificate_ids: [3],
    });
  });

  it("awardRecord → POST(blob) /honor/documents/award-record/ + id'ler", () => {
    odulApi.awardRecord([4, 5]);
    expect(apiMock.postBlob).toHaveBeenCalledWith("/honor/documents/award-record/", {
      certificate_ids: [4, 5],
    });
  });
});

describe("odul etiket/yardımcıları", () => {
  it("HONOR_STATUS_TR — lite durum makinesi (SUPERSEDED yok)", () => {
    expect(Object.keys(HONOR_STATUS_TR)).toEqual([
      "PROPOSED",
      "HONOR_BOARD_RECOMMENDED",
      "AWARDED",
      "PRINCIPAL_APPROVED",
      "PRINCIPAL_REJECTED",
      "REJECTED",
    ]);
  });

  it("criteriaDisplay — kodları Türkçe metne çevirir (backend criteria_display yok)", () => {
    expect(criteriaDisplay(["LANGUAGE", "SAFETY"])).toEqual([
      HONOR_CRITERION_TR.LANGUAGE,
      HONOR_CRITERION_TR.SAFETY,
    ]);
  });

  it("criteriaDisplay — tanınmayan kod olduğu gibi geçer", () => {
    expect(criteriaDisplay(["BILINMEYEN"])).toEqual(["BILINMEYEN"]);
  });
});

describe("groupProposalsByProposer — dolu teklif formu imza doğruluğu (md. 161)", () => {
  it("farklı teklif edenler ayrı gruplara düşer; ilk görülme sırası korunur", () => {
    expect(
      groupProposalsByProposer([
        { id: 1, proposer_name: "Ayşe Yılmaz" },
        { id: 2, proposer_name: "Mehmet Demir" },
        { id: 3, proposer_name: "Ayşe Yılmaz" },
      ]),
    ).toEqual([
      { proposerName: "Ayşe Yılmaz", ids: [1, 3] },
      { proposerName: "Mehmet Demir", ids: [2] },
    ]);
  });

  it("aynı teklif edenin tüm teklifleri tek formda kalır (ad kırpılır)", () => {
    expect(
      groupProposalsByProposer([
        { id: 7, proposer_name: " Ayşe Yılmaz " },
        { id: 9, proposer_name: "Ayşe Yılmaz" },
      ]),
    ).toEqual([{ proposerName: "Ayşe Yılmaz", ids: [7, 9] }]);
  });

  it("adsız teklifler kendi grubunda toplanır (imza satırı boş basılır)", () => {
    expect(
      groupProposalsByProposer([
        { id: 4, proposer_name: "" },
        { id: 5, proposer_name: "Ayşe Yılmaz" },
        { id: 6, proposer_name: "   " },
      ]),
    ).toEqual([
      { proposerName: "", ids: [4, 6] },
      { proposerName: "Ayşe Yılmaz", ids: [5] },
    ]);
  });

  it("boş liste → grup yok (indirilecek form yok)", () => {
    expect(groupProposalsByProposer([])).toEqual([]);
  });
});
