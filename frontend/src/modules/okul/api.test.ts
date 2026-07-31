// `okul` API katmanı testi — uç yolları, sorgu dizeleri, FormData anahtarları,
// tel-anahtarı çevirileri (`schoolYearId` → `school_year`) ve sayfalama zarfı
// çözümü BURADA pinlenir. Backend `apps/okul/urls.py` ile hizanın kaçmasını
// (sessiz 404 / boş liste) bu testler yakalar.

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
  HOLIDAY_KIND_TR,
  importCounts,
  okulApi,
  PERSONNEL_TEMPLATE_FILENAME,
  STUDENT_TEMPLATE_FILENAME,
} from "./api";
import type { PersonnelImportReport, StudentImportReport } from "./api";

const EMPTY_PAGE = { count: 0, next: null, previous: null, results: [] };

afterEach(() => vi.clearAllMocks());

describe("okulApi — kurulum sihirbazı", () => {
  it("getSetupStatus → GET /setup/status/", () => {
    okulApi.getSetupStatus();
    expect(apiMock.get).toHaveBeenCalledWith("/setup/status/");
  });

  it("getSchoolConfig / updateSchoolConfig → /setup/school-config/ (PUT kısmi gövde)", () => {
    okulApi.getSchoolConfig();
    expect(apiMock.get).toHaveBeenCalledWith("/setup/school-config/");

    okulApi.updateSchoolConfig({ school_name: "Örnek Anadolu Lisesi" });
    expect(apiMock.put).toHaveBeenCalledWith("/setup/school-config/", {
      school_name: "Örnek Anadolu Lisesi",
    });
  });

  it("completeSetup → POST /setup/complete/", () => {
    okulApi.completeSetup();
    expect(apiMock.post).toHaveBeenCalledWith("/setup/complete/");
  });

  it("getGradeLevels → GET /grade-levels/", () => {
    okulApi.getGradeLevels();
    expect(apiMock.get).toHaveBeenCalledWith("/grade-levels/");
  });
});

describe("okulApi — ders yılları", () => {
  it("listSchoolYears → GET /school-years/?limit=200 + zarf çözümü", async () => {
    apiMock.get.mockResolvedValueOnce({
      count: 1,
      next: null,
      previous: null,
      results: [{ id: 1 }],
    } as never);
    const out = await okulApi.listSchoolYears();
    expect(apiMock.get).toHaveBeenCalledWith("/school-years/?limit=200");
    expect(out).toEqual([{ id: 1 }]);
  });

  it("createSchoolYear / activateSchoolYear → uç yolları", () => {
    okulApi.createSchoolYear({
      name: "2026-2027",
      start_date: "2026-09-01",
      end_date: "2027-06-30",
    });
    expect(apiMock.post).toHaveBeenCalledWith("/school-years/", {
      name: "2026-2027",
      start_date: "2026-09-01",
      end_date: "2027-06-30",
    });

    okulApi.activateSchoolYear(4);
    expect(apiMock.post).toHaveBeenLastCalledWith("/school-years/4/activate/");
  });
});

describe("okulApi — sınıf sorumlulukları", () => {
  it("listeleme aktif yıl veya seçilen yıl yolunu kullanır", async () => {
    apiMock.get.mockResolvedValue(EMPTY_PAGE as never);

    await okulApi.listClassResponsibilities();
    expect(apiMock.get).toHaveBeenCalledWith("/class-responsibilities/?limit=500");

    await okulApi.listClassResponsibilities(7);
    expect(apiMock.get).toHaveBeenLastCalledWith(
      "/class-responsibilities/?school_year=7&limit=500",
    );
  });

  it("oluşturma, güncelleme ve silme uçları hizalıdır", () => {
    const body = {
      school_year: 7,
      class_level: 10,
      class_section: "A",
      guidance_teacher: 4,
    };
    okulApi.createClassResponsibility(body);
    expect(apiMock.post).toHaveBeenCalledWith("/class-responsibilities/", body);

    okulApi.updateClassResponsibility(3, { guidance_teacher: 5 });
    expect(apiMock.patch).toHaveBeenCalledWith("/class-responsibilities/3/", {
      guidance_teacher: 5,
    });

    okulApi.deleteClassResponsibility(3);
    expect(apiMock.del).toHaveBeenCalledWith("/class-responsibilities/3/");
  });
});

describe("okulApi — tatiller", () => {
  it("listHolidays → GET /holidays/?limit=500 + zarf çözümü", async () => {
    apiMock.get.mockResolvedValueOnce({
      count: 1,
      next: null,
      previous: null,
      results: [{ id: 3 }],
    } as never);
    const out = await okulApi.listHolidays();
    expect(apiMock.get).toHaveBeenCalledWith("/holidays/?limit=500");
    expect(out).toEqual([{ id: 3 }]);
  });

  it("createHoliday / deleteHoliday → uç yolları", () => {
    okulApi.createHoliday({
      name: "Cumhuriyet Bayramı",
      start_date: "2026-10-29",
      end_date: "2026-10-29",
      kind: "OFFICIAL",
    });
    expect(apiMock.post).toHaveBeenCalledWith("/holidays/", {
      name: "Cumhuriyet Bayramı",
      start_date: "2026-10-29",
      end_date: "2026-10-29",
      kind: "OFFICIAL",
    });

    okulApi.deleteHoliday(9);
    expect(apiMock.del).toHaveBeenCalledWith("/holidays/9/");
  });

  it("seedHolidays → yıl verilmezse boş gövde; verilirse school_year teli", () => {
    okulApi.seedHolidays();
    expect(apiMock.post).toHaveBeenLastCalledWith("/holidays/seed/", {});

    okulApi.seedHolidays(null);
    expect(apiMock.post).toHaveBeenLastCalledWith("/holidays/seed/", {});

    okulApi.seedHolidays(2);
    expect(apiMock.post).toHaveBeenLastCalledWith("/holidays/seed/", { school_year: 2 });
  });

  it("HOLIDAY_KIND_TR — backend HolidayKind ile birebir", () => {
    expect(Object.keys(HOLIDAY_KIND_TR)).toEqual(["OFFICIAL", "RELIGIOUS", "OTHER"]);
  });
});

describe("okulApi — öğrenci listesi + sorgu dizesi", () => {
  it("filtresiz → GET /students/ (gereksiz '?' üretilmez)", async () => {
    apiMock.get.mockResolvedValueOnce(EMPTY_PAGE as never);
    await okulApi.listStudents();
    expect(apiMock.get).toHaveBeenCalledWith("/students/");
  });

  it("filtreler camelCase → snake_case query (sıra: search, class_level, class_section, limit, offset)", async () => {
    apiMock.get.mockResolvedValueOnce(EMPTY_PAGE as never);
    await okulApi.listStudents({
      search: "yılmaz",
      classLevel: 10,
      classSection: "A",
      limit: 25,
      offset: 50,
    });
    expect(apiMock.get).toHaveBeenCalledWith(
      `/students/?search=${encodeURIComponent("yılmaz")}&class_level=10&class_section=A&limit=25&offset=50`,
    );
  });

  it("boş/0 değerler query'ye yazılmaz (offset=0 ilk sayfadır)", async () => {
    apiMock.get.mockResolvedValueOnce(EMPTY_PAGE as never);
    await okulApi.listStudents({ search: "   ", classLevel: null, classSection: "", offset: 0 });
    expect(apiMock.get).toHaveBeenCalledWith("/students/");
  });

  it("düz dizi yanıtı da sayfalama zarfına indirgenir", async () => {
    apiMock.get.mockResolvedValueOnce([{ id: 1 }, { id: 2 }] as never);
    const page = await okulApi.listStudents();
    expect(page).toEqual({ count: 2, next: null, previous: null, results: [{ id: 1 }, { id: 2 }] });
  });

  it("tekil öğrenci uçları — get/create/patch/delete", () => {
    okulApi.getStudent(7);
    expect(apiMock.get).toHaveBeenCalledWith("/students/7/");

    okulApi.createStudent({ first_name: "Ayşe", last_name: "Yılmaz" });
    expect(apiMock.post).toHaveBeenCalledWith("/students/", {
      first_name: "Ayşe",
      last_name: "Yılmaz",
    });

    okulApi.updateStudent(7, { class_level: 11 });
    expect(apiMock.patch).toHaveBeenCalledWith("/students/7/", { class_level: 11 });

    okulApi.deleteStudent(7);
    expect(apiMock.del).toHaveBeenCalledWith("/students/7/");
  });
});

describe("okulApi — personel listesi + tekil uçlar", () => {
  it("arama + sayfalama query'si", async () => {
    apiMock.get.mockResolvedValueOnce(EMPTY_PAGE as never);
    await okulApi.listPersonnel({ search: "demirci", limit: 25, offset: 25 });
    expect(apiMock.get).toHaveBeenCalledWith("/personnel/?search=demirci&limit=25&offset=25");
  });

  it("tekil personel uçları — get/create/patch/delete", () => {
    okulApi.getPersonnel(3);
    expect(apiMock.get).toHaveBeenCalledWith("/personnel/3/");

    okulApi.createPersonnel({ first_name: "Mehmet", last_name: "Demirci", title: "Öğretmen" });
    expect(apiMock.post).toHaveBeenCalledWith("/personnel/", {
      first_name: "Mehmet",
      last_name: "Demirci",
      title: "Öğretmen",
    });

    okulApi.updatePersonnel(3, { branch: "Coğrafya" });
    expect(apiMock.patch).toHaveBeenCalledWith("/personnel/3/", { branch: "Coğrafya" });

    okulApi.deletePersonnel(3);
    expect(apiMock.del).toHaveBeenCalledWith("/personnel/3/");
  });
});

describe("okulApi — içe aktarma (dosya vs. metin yolu)", () => {
  it("dosya yolu → multipart FormData, anahtar 'file'", () => {
    const file = new File(["x"], "ogrenci.xlsx");
    okulApi.previewStudentImport({ file });
    expect(apiMock.postForm).toHaveBeenCalledTimes(1);
    const [path, form] = apiMock.postForm.mock.calls[0] as unknown as [string, FormData];
    expect(path).toBe("/imports/students/preview/");
    expect(form).toBeInstanceOf(FormData);
    expect(form.get("file")).toBe(file);
    expect(form.get("text")).toBeNull();
    expect(apiMock.post).not.toHaveBeenCalled();
  });

  it("metin yolu → JSON gövde {text}", () => {
    okulApi.commitStudentImport({ text: "ad\tsoyad" });
    expect(apiMock.post).toHaveBeenCalledWith("/imports/students/commit/", { text: "ad\tsoyad" });
    expect(apiMock.postForm).not.toHaveBeenCalled();
  });

  it("personel önizleme/aktarma uçları", () => {
    const file = new File(["x"], "personel.xlsx");
    okulApi.previewPersonnelImport({ file });
    const [path] = apiMock.postForm.mock.calls[0] as unknown as [string, FormData];
    expect(path).toBe("/imports/personnel/preview/");

    okulApi.commitPersonnelImport({ text: "satır" });
    expect(apiMock.post).toHaveBeenCalledWith("/imports/personnel/commit/", { text: "satır" });
  });

  it("şablon indirme → blob uçları + dosya adları", () => {
    okulApi.studentTemplate();
    expect(apiMock.getBlob).toHaveBeenCalledWith("/templates/students/");

    okulApi.personnelTemplate();
    expect(apiMock.getBlob).toHaveBeenLastCalledWith("/templates/personnel/");

    expect(STUDENT_TEMPLATE_FILENAME).toBe("sablon-ogrenci.xlsx");
    expect(PERSONNEL_TEMPLATE_FILENAME).toBe("sablon-personel.xlsx");
  });
});

describe("importCounts — öğrenci/personel sayaç adlarını tek şekle indirger", () => {
  const base = {
    file_hash: "h",
    file_name: "f.xlsx",
    total_rows: 3,
    processed: 3,
    already_imported: false,
    dry_run: true,
    warnings: [],
    skipped: [],
  };

  it("öğrenci raporu", () => {
    const report: StudentImportReport = {
      ...base,
      created_students: 2,
      updated_students: 1,
      unchanged_students: 0,
    };
    expect(importCounts(report)).toEqual({ created: 2, updated: 1, unchanged: 0 });
  });

  it("personel raporu", () => {
    const report: PersonnelImportReport = {
      ...base,
      created_personnel: 0,
      updated_personnel: 3,
      unchanged_personnel: 5,
    };
    expect(importCounts(report)).toEqual({ created: 0, updated: 3, unchanged: 5 });
  });
});
