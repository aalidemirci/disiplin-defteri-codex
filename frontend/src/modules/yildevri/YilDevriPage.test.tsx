// Yıl devri sihirbazı testi (F5-D3): beş adımın mutlu yolu + geri alınamaz
// adımların onay kapısı + kapanmamış dosyaların ENGEL DEĞİL uyarı olması.
// `./api` (yıl devri uçları), `../disiplin/api` (kapanmamış dosyalar + kurul) ve
// `../odul/api` (onur kurulu) vi.mock ile taklit edilir; onay diyaloğu GERÇEK
// ConfirmProvider üzerinden çalışır (native confirm kullanılmaz).

import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "../../lib/api";
import { ConfirmProvider } from "../../ui/ConfirmProvider";
import { SnackbarProvider } from "../../ui/SnackbarProvider";
import type { PromotionReport, RolloverResult, YearRolloverStatus } from "./api";

const yapi = vi.hoisted(() => ({
  getStatus: vi.fn(),
  createSchoolYear: vi.fn(),
  promoteStudents: vi.fn(),
}));
const dapi = vi.hoisted(() => ({
  listCases: vi.fn(),
  getCommittee: vi.fn(),
}));
const oapi = vi.hoisted(() => ({
  getBoard: vi.fn(),
}));

vi.mock("./api", () => ({ yilDevriApi: yapi }));
vi.mock("../disiplin/api", () => ({ disiplinApi: dapi }));
vi.mock("../odul/api", () => ({ odulApi: oapi }));

import YilDevriPage from "./YilDevriPage";

const DURUM: YearRolloverStatus = {
  active_school_year: {
    id: 1,
    name: "2025-2026",
    start_date: "2025-09-08",
    end_date: "2026-06-26",
    is_active: true,
  },
  suggested_year: { name: "2026-2027", start_date: "2026-09-08", end_date: "2027-06-26" },
  active_student_count: 42,
  students_without_level: 1,
  level_counts: [
    { level: 9, count: 10 },
    { level: 12, count: 8 },
  ],
};

const DEVIR_SONUCU: RolloverResult = {
  school_year: {
    id: 2,
    name: "2026-2027",
    start_date: "2026-09-08",
    end_date: "2027-06-26",
    is_active: true,
  },
  previous_school_year_name: "2025-2026",
  holidays_created: 7,
  holidays_skipped: 1,
};

const ONIZLEME: PromotionReport = {
  applied: false,
  graduate_final_level: true,
  promoted: 30,
  graduated: 8,
  final_level_kept: 0,
  skipped_inactive: 2,
  skipped_no_level: 1,
  skipped_out_of_range: 0,
  moves: [
    { from_level: 9, to_level: 10, count: 10 },
    { from_level: 10, to_level: 11, count: 12 },
    { from_level: 11, to_level: 12, count: 8 },
  ],
};

function sayfaCiz() {
  return render(
    <SnackbarProvider>
      <ConfirmProvider>
        <MemoryRouter>
          <YilDevriPage />
        </MemoryRouter>
      </ConfirmProvider>
    </SnackbarProvider>,
  );
}

/** Adım gezinme yardımcıları — "İleri" düğmesi sayfanın altındadır. */
async function ileri(user: ReturnType<typeof userEvent.setup>, kez = 1) {
  for (let i = 0; i < kez; i += 1) {
    await user.click(screen.getByRole("button", { name: /İleri/ }));
  }
}

beforeEach(() => {
  yapi.getStatus.mockResolvedValue(DURUM);
  yapi.createSchoolYear.mockResolvedValue(DEVIR_SONUCU);
  yapi.promoteStudents.mockResolvedValue(ONIZLEME);
  dapi.listCases.mockResolvedValue([]);
  dapi.getCommittee.mockResolvedValue({ committee: null });
  oapi.getBoard.mockResolvedValue({ board: null });
});

afterEach(() => {
  vi.clearAllMocks();
});

describe("YilDevriPage — 1. Hazırlık", () => {
  it("mevcut durumu ve kapanmamış dosya yokluğunu gösterir", async () => {
    sayfaCiz();
    expect(await screen.findByText("1. Hazırlık")).toBeInTheDocument();
    expect(screen.getByText("2025-2026")).toBeInTheDocument();
    expect(screen.getByText("42")).toBeInTheDocument();
    expect(await screen.findByText(/Kapanmamış dosya yok/)).toBeInTheDocument();
  });

  it("kapanmamış dosyaları ENGEL DEĞİL uyarı olarak listeler", async () => {
    dapi.listCases.mockResolvedValue([
      {
        id: 7,
        case_no: "2025-2026-0003",
        petition_date: "2026-05-20",
        petitioner_name: "İdare",
        petitioner_role: "IDARE",
        summary: "…",
        current_stage: "PETITION",
        current_stage_display: "Dilekçe",
        closed_at: null,
        students: [],
      },
    ]);
    sayfaCiz();

    const uyari = await screen.findByText(/engel değildir/);
    expect(uyari).toBeInTheDocument();
    expect(screen.getByText("2025-2026-0003")).toBeInTheDocument();
    // Uyarı kalıcıdır; ileri gitme düğmesi ASLA kilitlenmez.
    expect(screen.getByRole("button", { name: /İleri/ })).toBeEnabled();
  });

  it("dosya listesi okunamazsa hata bandı gösterir, sihirbaz çalışmaya devam eder", async () => {
    dapi.listCases.mockRejectedValue(new ApiError(500, "server_error", "Dosyalar okunamadı."));
    sayfaCiz();
    expect(await screen.findByText("Dosyalar okunamadı.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /İleri/ })).toBeEnabled();
  });
});

describe("YilDevriPage — 2. Yeni ders yılı", () => {
  it("öneriyi forma doldurur, onaydan sonra devreder ve sonucu özetler", async () => {
    const user = userEvent.setup();
    sayfaCiz();
    await screen.findByText("1. Hazırlık");
    await ileri(user);

    expect(await screen.findByText("2. Yeni ders yılı")).toBeInTheDocument();
    expect(screen.getByLabelText(/Ders yılı adı/)).toHaveValue("2026-2027");

    await user.click(screen.getByRole("button", { name: /Yeni yıla devret/ }));

    // Onay diyaloğu: geri alınamazlık + numaralama açıkça söylenir.
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText(/geri alınamaz/)).toBeInTheDocument();
    expect(within(dialog).getByText(/2026-2027-0001/)).toBeInTheDocument();
    await user.click(within(dialog).getByRole("button", { name: "Devret" }));

    await waitFor(() =>
      expect(yapi.createSchoolYear).toHaveBeenCalledWith({
        name: "2026-2027",
        start_date: "2026-09-08",
        end_date: "2027-06-26",
        first_term_end: "2027-01-16",
        second_term_start: "2027-02-02",
        seed_holidays: true,
      }),
    );
    // Devir sonrası tatil adımına geçilir ve sonuç özetlenir.
    expect(await screen.findByText("3. Tatil takvimi")).toBeInTheDocument();
    expect(screen.getByText(/7 tatil eklendi/)).toBeInTheDocument();
  });

  it("onay reddedilirse hiçbir şey yazılmaz", async () => {
    const user = userEvent.setup();
    sayfaCiz();
    await screen.findByText("1. Hazırlık");
    await ileri(user);
    await user.click(await screen.findByRole("button", { name: /Yeni yıla devret/ }));

    const dialog = await screen.findByRole("dialog");
    await user.click(within(dialog).getByRole("button", { name: "Vazgeç" }));

    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(yapi.createSchoolYear).not.toHaveBeenCalled();
  });

  it("backend alan hatasını ilgili alanın altında gösterir", async () => {
    yapi.createSchoolYear.mockRejectedValue(
      new ApiError(400, "validation_error", "Doğrulama hatası.", {
        name: ["'2026-2027' adında bir ders yılı zaten var; farklı bir ad girin."],
      }),
    );
    const user = userEvent.setup();
    sayfaCiz();
    await screen.findByText("1. Hazırlık");
    await ileri(user);
    await user.click(await screen.findByRole("button", { name: /Yeni yıla devret/ }));
    const dialog = await screen.findByRole("dialog");
    await user.click(within(dialog).getByRole("button", { name: "Devret" }));

    expect(await screen.findByText(/adında bir ders yılı zaten var/)).toBeInTheDocument();
  });
});

describe("YilDevriPage — 4. Kurullar", () => {
  it("yeni yılda kurul TANIMSIZ ise görünür kılar ve ekrana yönlendirir", async () => {
    const user = userEvent.setup();
    sayfaCiz();
    await screen.findByText("1. Hazırlık");
    await ileri(user, 3);

    expect(await screen.findByText("4. Kurullar")).toBeInTheDocument();
    await waitFor(() => expect(screen.getAllByText("tanımsız")).toHaveLength(2));
    expect(screen.getByRole("link", { name: /Kurulu tanımla/ })).toHaveAttribute(
      "href",
      "/disiplin/kurul",
    );
    expect(screen.getByRole("link", { name: /Onur kurulunu tanımla/ })).toHaveAttribute(
      "href",
      "/odul",
    );
    // Kurul KOPYALANMAZ — üyeler her yıl yeniden belirlenir (md. 185-188).
    expect(screen.getByText(/her ders yılı yeniden belirlenir/)).toBeInTheDocument();
  });
});

describe("YilDevriPage — 5. Öğrenciler", () => {
  it("önerilen yolu (yeniden import) önce sunar, önizlemeyi otomatik yükler", async () => {
    const user = userEvent.setup();
    sayfaCiz();
    await screen.findByText("1. Hazırlık");
    await ileri(user, 4);

    expect(await screen.findByText("5. Öğrenci listesi")).toBeInTheDocument();
    expect(screen.getByText(/Önerilen: güncel Excel şablonunu yeniden aktar/)).toBeInTheDocument();
    await waitFor(() =>
      expect(yapi.promoteStudents).toHaveBeenCalledWith({
        apply: false,
        graduateFinalLevel: true,
      }),
    );
    expect(await screen.findByText("9. sınıf → 10. sınıf")).toBeInTheDocument();
  });

  it("toplu yükseltme onay ister ve geri alınamazlığı söyler", async () => {
    yapi.promoteStudents.mockImplementation(
      ({ apply }: { apply: boolean; graduateFinalLevel: boolean }) =>
        Promise.resolve({ ...ONIZLEME, applied: apply }),
    );
    const user = userEvent.setup();
    sayfaCiz();
    await screen.findByText("1. Hazırlık");
    await ileri(user, 4);
    await screen.findByText("5. Öğrenci listesi");

    await user.click(await screen.findByRole("button", { name: /Toplu yükseltmeyi uygula/ }));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText(/GERİ ALINAMAZ/)).toBeInTheDocument();
    expect(within(dialog).getByText(/Ayrıldı/)).toBeInTheDocument();
    await user.click(within(dialog).getByRole("button", { name: "Yükselt" }));

    await waitFor(() =>
      expect(yapi.promoteStudents).toHaveBeenCalledWith({ apply: true, graduateFinalLevel: true }),
    );
    expect(await screen.findByText(/30 öğrenci yükseltildi/)).toBeInTheDocument();
  });

  it("12'leri mezun etme seçeneği kapatılınca önizleme yeniden alınır", async () => {
    const user = userEvent.setup();
    sayfaCiz();
    await screen.findByText("1. Hazırlık");
    await ileri(user, 4);
    await screen.findByText("5. Öğrenci listesi");
    await waitFor(() => expect(yapi.promoteStudents).toHaveBeenCalled());

    yapi.promoteStudents.mockResolvedValue({
      ...ONIZLEME,
      graduate_final_level: false,
      graduated: 0,
      final_level_kept: 8,
    });
    await user.click(screen.getByLabelText(/12\. sınıfları mezun say/));

    await waitFor(() =>
      expect(yapi.promoteStudents).toHaveBeenLastCalledWith({
        apply: false,
        graduateFinalLevel: false,
      }),
    );
    expect(await screen.findByText(/12\. sınıf → değişmez/)).toBeInTheDocument();
  });
});
