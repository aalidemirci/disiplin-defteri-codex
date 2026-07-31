// Onur Kurulu karar paneli testi: teklif kartı + öneri/ret eylemleri, ortak toplantı
// tarihinin karara uygulanması ve önerilenler için teklif çizelgesi üretimi.
//
// OYS `modules/odul/KurulKarariPanel.test.tsx`'ten UYARLANDI (F4-D3); sapmalar: auth mock'u
// ve başkan/ADMIN gating senaryoları kalktı (eylemler koşulsuz), teslim (mark-delivered) ve
// öğrenci bazlı toplu ret (reject-student) senaryoları kalktı; fixture honors-lite
// serializer'ıyla birebir (criteria_display / karar bağlamı / teslim alanları yok).

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { SnackbarProvider } from "../../ui/SnackbarProvider";

const odul = vi.hoisted(() => ({
  listCertificates: vi.fn(),
  recommendCertificate: vi.fn(() => Promise.resolve()),
  rejectCertificate: vi.fn(() => Promise.resolve()),
  recommendationRecord: vi.fn(() => Promise.resolve(new Blob())),
}));

const okul = vi.hoisted(() => ({
  listSchoolYears: vi.fn(() =>
    Promise.resolve([
      {
        id: 1,
        name: "2025-2026",
        start_date: "2025-09-01",
        end_date: "2026-06-30",
        is_active: true,
      },
    ]),
  ),
  listSchoolTerms: vi.fn(() =>
    Promise.resolve([
      {
        id: 11,
        school_year: 1,
        sequence: 2,
        name: "2. Dönem",
        start_date: "2026-02-02",
        end_date: "2026-06-30",
      },
    ]),
  ),
}));

// Gerçek TR sabitlerini/tipleri koru; yalnız ağ çağrısı objesini mock'la.
vi.mock("./api", async (importActual) => {
  const actual = await importActual<typeof import("./api")>();
  return { ...actual, odulApi: odul };
});

vi.mock("../okul/api", () => ({ okulApi: okul }));

import KurulKarariPanel from "./KurulKarariPanel";
import type { HonorCertificate } from "./api";

const PROPOSED: HonorCertificate = {
  id: 1,
  student: 5,
  student_name: "Ali Veli",
  school_year: 1,
  status: "PROPOSED",
  status_display: "Teklif edildi",
  proposer_role: "TEACHER",
  proposer_role_display: "Öğretmen",
  proposer_name: "",
  criteria: ["LANGUAGE"],
  justification: "",
  recommended_at: null,
  awarded_at: null,
  rejection_reason: "",
  rejected_at: null,
};

const RECOMMENDED: HonorCertificate = {
  ...PROPOSED,
  id: 2,
  status: "HONOR_BOARD_RECOMMENDED",
  status_display: "Onur kurulu uygun gördü",
  recommended_at: "2026-06-02",
};

beforeEach(() => {
  odul.listCertificates.mockResolvedValue([PROPOSED]);
});
afterEach(() => vi.clearAllMocks());

function renderPanel() {
  return render(
    <SnackbarProvider>
      <KurulKarariPanel />
    </SnackbarProvider>,
  );
}

describe("KurulKarariPanel — öğrenci bazlı değerlendirme (authsuz)", () => {
  it("teklif kartında öğrenci + kriter etiketi ve öneri eylemi görünür", async () => {
    renderPanel();
    expect(await screen.findByRole("button", { name: "Uygun gör ve öner" })).toBeInTheDocument();
    expect(screen.getByText("Ali Veli")).toBeInTheDocument();
    // criteria_display yok → etiket HONOR_CRITERION_TR'den türetilir.
    expect(screen.getByText(/Türkçeyi doğru, güzel ve etkili kullanarak/)).toBeInTheDocument();
  });

  it("ortak toplantı tarihi uygun görüş kaydına uygulanır", async () => {
    const user = userEvent.setup();
    renderPanel();
    const dateInput = await screen.findByLabelText(/Onur Kurulu toplantı tarihi/);
    // jsdom'da tarih girdisine tuş tuş yazmak güvenilir değil → doğrudan change olayı.
    fireEvent.change(dateInput, { target: { value: "2026-06-10" } });
    await user.click(await screen.findByRole("button", { name: "Uygun gör ve öner" }));
    await waitFor(() =>
      expect(odul.recommendCertificate).toHaveBeenCalledWith(1, { recommended_on: "2026-06-10" }),
    );
  });

  it("önerilenler için teklif çizelgesi sunar, nihai karar eylemi sunmaz", async () => {
    odul.listCertificates.mockResolvedValue([RECOMMENDED]);
    renderPanel();
    expect(
      await screen.findByRole("button", { name: "Teklif çizelgesi üret" }),
    ).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Belge ver" })).not.toBeInTheDocument();
    expect(screen.getByText(/Nihai değerlendirme Disiplin modülündeki/)).toBeInTheDocument();
  });

  it("uygun görmeme gerekçesini zorunlu tutar ve toplantı tarihiyle reddeder", async () => {
    const user = userEvent.setup();
    renderPanel();
    const dateInput = await screen.findByLabelText(/Onur Kurulu toplantı tarihi/);
    fireEvent.change(dateInput, { target: { value: "2026-06-11" } });
    await user.click(await screen.findByRole("button", { name: "Uygun görme" }));
    expect(await screen.findByText("Uygun görmeme gerekçesi zorunludur.")).toBeInTheDocument();

    await user.type(screen.getByLabelText("Uygun görülmeme gerekçesi"), "Koşullar sağlanmadı");
    await user.click(screen.getByRole("button", { name: "Uygun görme" }));
    await waitFor(() =>
      expect(odul.rejectCertificate).toHaveBeenCalledWith(1, {
        decided_on: "2026-06-11",
        reason: "Koşullar sağlanmadı",
      }),
    );
  });

  it("önerilenler çizelgesini üretir", async () => {
    const user = userEvent.setup();
    odul.listCertificates.mockResolvedValue([RECOMMENDED]);
    renderPanel();
    await user.click(await screen.findByRole("button", { name: "Teklif çizelgesi üret" }));
    await waitFor(() => expect(odul.recommendationRecord).toHaveBeenCalledWith([2]));
  });
});
