// Ayarlar sayfası testi (F4-D4): ders yılı listesi + aktifleştirme onayı, oluşturma
// formunda backend 400'ünün alan altında görünmesi, tatil listesinin aktif ders yılına
// göre süzülmesi + tür/tahmini rozetleri, tatil silme onayı, resmî tatil yükleme
// sonucu, okul künyesinin PUT gövdesi ve yükleme hatası bandı.

import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "../../lib/api";
import { ConfirmProvider } from "../../ui/ConfirmProvider";
import { SnackbarProvider } from "../../ui/SnackbarProvider";

const okul = vi.hoisted(() => ({
  listSchoolYears: vi.fn(),
  createSchoolYear: vi.fn(),
  listSchoolTerms: vi.fn(),
  configureSchoolTerms: vi.fn(),
  activateSchoolYear: vi.fn(),
  listHolidays: vi.fn(),
  createHoliday: vi.fn(),
  deleteHoliday: vi.fn(),
  seedHolidays: vi.fn(),
  getSchoolConfig: vi.fn(),
  updateSchoolConfig: vi.fn(),
}));

vi.mock("../okul/api", () => ({
  okulApi: okul,
  HOLIDAY_KIND_TR: {
    OFFICIAL: "Resmî tatil",
    RELIGIOUS: "Dini bayram",
    OTHER: "İdari/diğer",
  },
}));

import AyarlarPage from "./AyarlarPage";

const YEARS = [
  { id: 1, name: "2026-2027", start_date: "2026-09-01", end_date: "2027-06-30", is_active: true },
  { id: 2, name: "2025-2026", start_date: "2025-09-01", end_date: "2026-06-30", is_active: false },
];

const HOLIDAYS = [
  {
    id: 10,
    name: "29 Ekim Cumhuriyet Bayramı",
    start_date: "2026-10-29",
    end_date: "2026-10-29",
    kind: "OFFICIAL" as const,
    is_estimated: false,
  },
  {
    id: 11,
    name: "Ramazan Bayramı",
    start_date: "2027-03-20",
    end_date: "2027-03-22",
    kind: "RELIGIOUS" as const,
    is_estimated: true,
  },
  {
    // Aktif ders yılının (01.09.2026 – 30.06.2027) DIŞINDA — süzülüp gizlenmeli.
    id: 12,
    name: "Eski yıl tatili",
    start_date: "2025-10-29",
    end_date: "2025-10-29",
    kind: "OFFICIAL" as const,
    is_estimated: false,
  },
];

const CONFIG = {
  school_name: "Test Anadolu Lisesi",
  province: "İstanbul",
  district: "Kadıköy",
  principal_name: "Ali Müdür",
  setup_completed: true,
};

function renderPage() {
  return render(
    <SnackbarProvider>
      <ConfirmProvider>
        <MemoryRouter>
          <AyarlarPage />
        </MemoryRouter>
      </ConfirmProvider>
    </SnackbarProvider>,
  );
}

/** Ortak mutlu-yol mock'ları (her test kendi sapmasını üstüne yazar). */
function mockHappyPath() {
  okul.listSchoolYears.mockResolvedValue(YEARS);
  okul.listHolidays.mockResolvedValue(HOLIDAYS);
  okul.getSchoolConfig.mockResolvedValue(CONFIG);
}

afterEach(() => {
  vi.clearAllMocks();
});

describe("AyarlarPage — ders yılları", () => {
  it("yılları listeler, aktif olanı rozetler ve karar tipleri bağlantısını gösterir", async () => {
    mockHappyPath();
    renderPage();

    expect(await screen.findByText("2026-2027")).toBeInTheDocument();
    expect(screen.getByText("2025-2026")).toBeInTheDocument();
    expect(screen.getByText("Aktif")).toBeInTheDocument();
    // Aktif yılda "Aktifleştir" butonu çıkmaz → yalnız pasif yıl için bir tane.
    expect(screen.getAllByRole("button", { name: /Aktifleştir/ })).toHaveLength(1);
    expect(screen.getByRole("link", { name: /Disiplin karar tipleri/ })).toHaveAttribute(
      "href",
      "/disiplin/karar-tipleri",
    );
    expect(screen.getByRole("link", { name: /Sınıf sorumluları/ })).toHaveAttribute(
      "href",
      "/ayarlar/sinif-sorumlulari",
    );
  });

  it("aktifleştirme onaylanınca API çağrılır ve liste tazelenir", async () => {
    mockHappyPath();
    okul.activateSchoolYear.mockResolvedValue({ ...YEARS[1], is_active: true });
    const user = userEvent.setup();
    renderPage();

    await screen.findByText("2025-2026");
    await user.click(screen.getByRole("button", { name: /Aktifleştir/ }));

    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText(/yalnız bir yıl aktif olabilir/)).toBeInTheDocument();
    await user.click(within(dialog).getByRole("button", { name: "Aktifleştir" }));

    await waitFor(() => expect(okul.activateSchoolYear).toHaveBeenCalledWith(2));
    // İlk yük + aktivasyon sonrası tazeleme.
    await waitFor(() => expect(okul.listSchoolYears).toHaveBeenCalledTimes(2));
  });

  it("oluşturma 400'ünde alan hatası ilgili alanın altında gösterilir", async () => {
    mockHappyPath();
    okul.createSchoolYear.mockRejectedValue(
      new ApiError(400, "validation_error", "Gönderilen veride hatalar var.", {
        end_date: ["Bitiş tarihi başlangıçtan sonra olmalıdır."],
      }),
    );
    const user = userEvent.setup();
    renderPage();

    await screen.findByText("2026-2027");
    await user.type(screen.getByLabelText(/Ders yılı adı/), "2027-2028");
    await user.type(screen.getByLabelText(/^Başlangıç/), "2027-09-01");
    await user.type(screen.getByLabelText(/^Bitiş/), "2027-08-01");
    await user.type(screen.getByLabelText(/1. dönem bitişi/), "2028-01-16");
    await user.type(screen.getByLabelText(/2. dönem başlangıcı/), "2028-02-02");
    await user.click(screen.getByRole("button", { name: /Ders yılı oluştur/ }));

    expect(
      await screen.findByText("Bitiş tarihi başlangıçtan sonra olmalıdır."),
    ).toBeInTheDocument();
    expect(okul.createSchoolYear).toHaveBeenCalledWith({
      name: "2027-2028",
      start_date: "2027-09-01",
      end_date: "2027-08-01",
    });
  });

  it("ders yılları yüklenemezse hata bandı çıkar", async () => {
    okul.listSchoolYears.mockRejectedValue(
      new ApiError(500, "error", "Ders yılları okunamadı.", {}),
    );
    okul.listHolidays.mockResolvedValue([]);
    okul.getSchoolConfig.mockResolvedValue(CONFIG);
    renderPage();

    expect(await screen.findByText("Ders yılları okunamadı.")).toBeInTheDocument();
  });
});

describe("AyarlarPage — tatiller", () => {
  it("aktif yılın tatillerini rozetleriyle listeler, yıl dışındakini gizler", async () => {
    mockHappyPath();
    const user = userEvent.setup();
    renderPage();

    await screen.findByText("2026-2027");
    await user.click(screen.getByRole("tab", { name: /Tatiller/ }));

    expect(await screen.findByText("29 Ekim Cumhuriyet Bayramı")).toBeInTheDocument();
    // "tahmini" kelimesi bilgi notunda da geçiyor → rozeti kendi satırında ara.
    const religiousRow = screen.getByText("Ramazan Bayramı").closest("li");
    expect(religiousRow).not.toBeNull();
    expect(within(religiousRow as HTMLElement).getByText("tahmini")).toBeInTheDocument();
    expect(within(religiousRow as HTMLElement).getByText("Dini bayram")).toBeInTheDocument();
    expect(screen.queryByText("Eski yıl tatili")).not.toBeInTheDocument();

    // Süzgeç kapatılınca yıl dışındaki kayıt da görünür.
    await user.click(screen.getByLabelText(/Aktif yıl dışındaki tatilleri de göster/));
    expect(await screen.findByText("Eski yıl tatili")).toBeInTheDocument();
  });

  it("tatil silme onaylanınca API çağrılır ve liste tazelenir", async () => {
    mockHappyPath();
    okul.deleteHoliday.mockResolvedValue(undefined);
    const user = userEvent.setup();
    renderPage();

    await screen.findByText("2026-2027");
    await user.click(screen.getByRole("tab", { name: /Tatiller/ }));
    await screen.findByText("29 Ekim Cumhuriyet Bayramı");

    await user.click(screen.getAllByRole("button", { name: /Sil/ })[0]);
    const dialog = await screen.findByRole("dialog");
    await user.click(within(dialog).getByRole("button", { name: "Sil" }));

    await waitFor(() => expect(okul.deleteHoliday).toHaveBeenCalledWith(10));
    await waitFor(() => expect(okul.listHolidays).toHaveBeenCalledTimes(2));
  });

  it("resmî tatil yükleme sonucu created/skipped olarak gösterilir", async () => {
    mockHappyPath();
    okul.seedHolidays.mockResolvedValue({ created: 12, skipped: 3 });
    const user = userEvent.setup();
    renderPage();

    await screen.findByText("2026-2027");
    await user.click(screen.getByRole("tab", { name: /Tatiller/ }));
    await screen.findByText("29 Ekim Cumhuriyet Bayramı");

    await user.click(screen.getByRole("button", { name: /Resmî tatilleri yükle/ }));

    expect(await screen.findByText("12 tatil eklendi, 3 kayıt zaten vardı.")).toBeInTheDocument();
    await waitFor(() => expect(okul.listHolidays).toHaveBeenCalledTimes(2));
  });

  it("aktif ders yılı yoksa seed hatası bantta gösterilir", async () => {
    okul.listSchoolYears.mockResolvedValue([{ ...YEARS[0], is_active: false }]);
    okul.listHolidays.mockResolvedValue([]);
    okul.getSchoolConfig.mockResolvedValue(CONFIG);
    okul.seedHolidays.mockRejectedValue(
      new ApiError(
        400,
        "validation_error",
        "Aktif ders yılı yok; önce bir ders yılı oluşturup aktifleştirin.",
        {},
      ),
    );
    const user = userEvent.setup();
    renderPage();

    await screen.findByText("2026-2027");
    await user.click(screen.getByRole("tab", { name: /Tatiller/ }));
    await user.click(await screen.findByRole("button", { name: /Resmî tatilleri yükle/ }));

    expect(
      await screen.findByText("Aktif ders yılı yok; önce bir ders yılı oluşturup aktifleştirin."),
    ).toBeInTheDocument();
  });
});

describe("AyarlarPage — okul bilgileri", () => {
  it("künyeyi yükler ve kaydedince PUT gövdesini gönderir", async () => {
    mockHappyPath();
    okul.updateSchoolConfig.mockResolvedValue({ ...CONFIG, principal_name: "Veli Müdür" });
    const user = userEvent.setup();
    renderPage();

    await screen.findByText("2026-2027");
    await user.click(screen.getByRole("tab", { name: /Okul Bilgileri/ }));

    const principal = await screen.findByLabelText(/Okul müdürü/);
    expect(screen.getByLabelText(/Okul adı/)).toHaveValue("Test Anadolu Lisesi");
    await user.clear(principal);
    await user.type(principal, "Veli Müdür");
    await user.click(screen.getByRole("button", { name: /Kaydet/ }));

    await waitFor(() =>
      expect(okul.updateSchoolConfig).toHaveBeenCalledWith({
        school_name: "Test Anadolu Lisesi",
        province: "İstanbul",
        district: "Kadıköy",
        principal_name: "Veli Müdür",
      }),
    );
  });

  it("okul adı boşken kaydetmeye çalışınca alan hatası gösterilir", async () => {
    mockHappyPath();
    const user = userEvent.setup();
    renderPage();

    await screen.findByText("2026-2027");
    await user.click(screen.getByRole("tab", { name: /Okul Bilgileri/ }));

    await user.clear(await screen.findByLabelText(/Okul adı/));
    await user.click(screen.getByRole("button", { name: /Kaydet/ }));

    expect(
      await screen.findByText("Okul adı yazılmalıdır (evrak antedinde görünür)."),
    ).toBeInTheDocument();
    expect(okul.updateSchoolConfig).not.toHaveBeenCalled();
  });
});
