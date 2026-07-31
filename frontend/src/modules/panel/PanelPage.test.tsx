// Panel (ana ekran) testi (F4-D4): özet sayım kartları, önem düzeyine göre
// gruplanmış "Yaklaşan Süreler" listesi + satır bağlantısı, boş durum ve
// yükleme hatası. İki istemci (disiplin süre uçları + okul kurulum durumu)
// vi.mock ile taklit edilir — ağ çağrısı yapılmaz.
//
// Auth yok: rol/yetki senaryosu YOKTUR (tek kullanıcılı masaüstü).

import { render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "../../lib/api";
import type { DeadlineItem } from "../disiplin/api";
import type { SetupStatus } from "../okul/api";

const deadlines = vi.hoisted(() => ({ list: vi.fn() }));
const disciplineCases = vi.hoisted(() => ({ listCases: vi.fn() }));
const okul = vi.hoisted(() => ({ getSetupStatus: vi.fn() }));

vi.mock("../disiplin/api", () => ({
  deadlinesApi: deadlines,
  disiplinApi: disciplineCases,
  SEVERITY_ORDER: ["GEÇTİ", "YAKLAŞIYOR", "BİLGİ"],
}));

vi.mock("../okul/api", () => ({ okulApi: okul }));

import PanelPage from "./PanelPage";

const STATUS: SetupStatus = {
  setup_completed: true,
  school_name: "Örnek Anadolu Lisesi",
  has_active_school_year: true,
  student_count: 482,
  personnel_count: 37,
  holiday_count: 14,
};

const ITEMS: DeadlineItem[] = [
  {
    severity: "GEÇTİ",
    case_no: "2025/1",
    title: "İtiraz üst kurula sevk edilmeli (başvuru + 5 iş günü)",
    due_date: "2026-03-05",
    statute_ref: "md. 169/3",
    link: "/disiplin/7",
  },
  {
    severity: "YAKLAŞIYOR",
    case_no: "2025/4",
    title: "Kurul karar süresi doluyor (kurula geliş + 10 iş günü)",
    due_date: "2026-03-20",
    statute_ref: "md. 192/3",
    link: "/disiplin/9",
  },
  {
    severity: "BİLGİ",
    case_no: "2025/2",
    title: "Karar tebliğ bekliyor (Ayşe Yılmaz)",
    due_date: null,
    statute_ref: "md. 169/5",
    link: "/disiplin/8",
  },
];

function renderPage() {
  return render(
    <MemoryRouter>
      <PanelPage />
    </MemoryRouter>,
  );
}

/** Bir özet kartının (etiket → kart kabı) içindeki değeri okur. */
function statValue(label: string): string {
  const tile = screen.getByText(label).parentElement;
  return within(tile as HTMLElement).getByText(/^[0-9.,—]+$/).textContent ?? "";
}

beforeEach(() => {
  okul.getSetupStatus.mockResolvedValue(STATUS);
  deadlines.list.mockResolvedValue(ITEMS);
  disciplineCases.listCases.mockResolvedValue([]);
});

afterEach(() => {
  vi.clearAllMocks();
});

describe("PanelPage", () => {
  it("özet sayımları ve okul adını gösterir", async () => {
    renderPage();

    expect(await screen.findByText(/Örnek Anadolu Lisesi/)).toBeInTheDocument();
    expect(statValue("Öğrenci")).toBe("482");
    expect(statValue("Personel")).toBe("37");
    expect(statValue("Tatil günü")).toBe("14");
    // GEÇTİ / YAKLAŞIYOR sayıları listeden türetilir.
    expect(statValue("Süresi geçmiş")).toBe("1");
    expect(statValue("Süresi yaklaşan")).toBe("1");
  });

  it("süreleri önem düzeyine göre gruplar; satır dosya detayına bağlanır", async () => {
    renderPage();

    expect(await screen.findByText("Süresi geçmiş (1)")).toBeInTheDocument();
    expect(screen.getByText("Süresi yaklaşan (1)")).toBeInTheDocument();
    expect(screen.getByText("Bilgi (1)")).toBeInTheDocument();

    // Tarih GÖRÜNTÜSÜ gg.aa.yyyy; tarihsiz BİLGİ satırı "—".
    expect(screen.getByText("Son gün: 05.03.2026")).toBeInTheDocument();
    expect(screen.getByText("Son gün: —")).toBeInTheDocument();
    expect(screen.getByText("md. 192/3")).toBeInTheDocument();

    const row = screen.getByRole("link", { name: /İtiraz üst kurula sevk edilmeli/ });
    expect(row).toHaveAttribute("href", "/disiplin/7");
  });

  it("süre yoksa boş durum, kurulum tamamlanmadıysa uyarı bandı gösterir", async () => {
    deadlines.list.mockResolvedValue([]);
    okul.getSetupStatus.mockResolvedValue({ ...STATUS, setup_completed: false });
    renderPage();

    expect(await screen.findByText("Takipte gecikmiş veya yaklaşan süre yok")).toBeInTheDocument();
    expect(await screen.findByText(/Kurulum sihirbazı henüz tamamlanmadı/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Ayarlar'a git" })).toHaveAttribute("href", "/ayarlar");
  });

  it("yükleme hatasında Türkçe hata bandı gösterir, boş durum basmaz", async () => {
    deadlines.list.mockRejectedValue(
      new ApiError(500, "server_error", "Süre listesi hesaplanamadı."),
    );
    renderPage();

    expect(await screen.findByText("Süre listesi hesaplanamadı.")).toBeInTheDocument();
    expect(screen.queryByText("Takipte gecikmiş veya yaklaşan süre yok")).not.toBeInTheDocument();
  });
});
