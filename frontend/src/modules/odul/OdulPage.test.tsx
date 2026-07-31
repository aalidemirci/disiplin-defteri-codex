// Onur Kurulu sayfası testi: başlık + dört sekme + mevzuat notu + sekme içeriklerinin
// (Toplantılar → HONOR tutanak listesi, Kurul Kararı → gerçek karar paneli) bağlanması.
//
// OYS `modules/odul/OdulPage.test.tsx`'ten UYARLANDI (F4-D3); sapmalar: auth mock'u ve rol
// gating senaryoları kalktı (Kurul Üyeleri sekmesi daima görünür), `sistem/api` ders yılı
// mock'u yerine bir şey gerekmiyor; Teklifler/Kurul Üyeleri panelleri (TutanakListesi gibi)
// mock'lanır — sayfa testi sekme kabuğuna odaklanır, panellerin kendi testleri vardır.

import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

const odul = vi.hoisted(() => ({
  listCertificates: vi.fn(() => Promise.resolve([])),
  recommendCertificate: vi.fn(),
  awardCertificate: vi.fn(),
  rejectCertificate: vi.fn(),
  recommendationRecord: vi.fn(() => Promise.resolve(new Blob())),
  awardRecord: vi.fn(() => Promise.resolve(new Blob())),
}));

// Gerçek TR sabitlerini/tipleri koru; yalnız ağ çağrısı objesini mock'la.
vi.mock("./api", async (importActual) => {
  const actual = await importActual<typeof import("./api")>();
  return { ...actual, odulApi: odul };
});

// Kardeş paneller kendi testlerinde doğrulanır; sayfa testi sekme kabuğuna odaklanır.
vi.mock("./OnurBelgeleriPanel", () => ({
  default: () => <div data-testid="teklifler-paneli" />,
}));
vi.mock("./OnurKuruluPanel", () => ({
  default: () => <div data-testid="kurul-uyeleri-paneli" />,
}));
vi.mock("../kurul/TutanakListesi", () => ({
  default: ({ councilType }: { councilType: string }) => (
    <div data-testid="tutanak-listesi">{councilType}</div>
  ),
}));

import OdulPage from "./OdulPage";

function renderPage() {
  return render(
    <MemoryRouter>
      <OdulPage />
    </MemoryRouter>,
  );
}

afterEach(() => vi.clearAllMocks());

describe("OdulPage — sekmeler (authsuz)", () => {
  it("başlık 'Onur Kurulu' + dört sekme (rol kapısı yok)", async () => {
    renderPage();
    expect(await screen.findByRole("heading", { name: "Onur Kurulu" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /Teklifler/ })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /Kurul Kararı/ })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /Toplantılar/ })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /Kurul Üyeleri/ })).toBeInTheDocument();
  });

  it("varsayılan sekme Teklifler panelidir", async () => {
    renderPage();
    expect(await screen.findByTestId("teklifler-paneli")).toBeInTheDocument();
  });

  it("Toplantılar sekmesi: HONOR tutanak listesi gömülü", async () => {
    const user = userEvent.setup();
    renderPage();
    await user.click(await screen.findByRole("tab", { name: /Toplantılar/ }));
    expect(await screen.findByTestId("tutanak-listesi")).toHaveTextContent("HONOR");
  });

  it("Kurul Kararı sekmesi: karar paneli yüklenir (teklif yokken boş mesaj)", async () => {
    const user = userEvent.setup();
    renderPage();
    await user.click(await screen.findByRole("tab", { name: /Kurul Kararı/ }));
    expect(await screen.findByText("Karar bekleyen teklif yok.")).toBeInTheDocument();
  });

  it("Kurul Üyeleri sekmesi rol kapısı olmadan açılır", async () => {
    const user = userEvent.setup();
    renderPage();
    await user.click(await screen.findByRole("tab", { name: /Kurul Üyeleri/ }));
    expect(await screen.findByTestId("kurul-uyeleri-paneli")).toBeInTheDocument();
  });

  it("mevzuat notu: onur listesi e-Okul'da üretilir", async () => {
    renderPage();
    expect(await screen.findByText(/Onur listesi e-Okul'da otomatik üretilir/)).toBeInTheDocument();
  });
});
