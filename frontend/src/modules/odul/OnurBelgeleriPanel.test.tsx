// Onur belgesi teklifleri paneli — M8 (kullanıcı kararı 26.09.2026): müdür onayından önceki
// son adım gerekçeyle geri alınır; müdürün onayladığı belgede geri alma düğmesi yoktur.

import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { HonorCertificate } from "./api";

const odul = vi.hoisted(() => ({
  listCertificates: vi.fn(),
  undoCertificateStep: vi.fn<(id: number, body: { reason: string }) => Promise<unknown>>(() =>
    Promise.resolve({}),
  ),
}));
const okul = vi.hoisted(() => ({
  listSchoolYears: vi.fn(() => Promise.resolve([{ id: 1, name: "2025-2026", is_active: true }])),
  listSchoolTerms: vi.fn(() =>
    Promise.resolve([
      { id: 7, name: "1. dönem", sequence: 1, start_date: "2000-01-01", end_date: "2999-12-31" },
    ]),
  ),
}));

vi.mock("./api", async (importActual) => {
  const actual = await importActual<typeof import("./api")>();
  return { ...actual, odulApi: odul };
});
vi.mock("../okul/api", async (importActual) => {
  const actual = await importActual<typeof import("../okul/api")>();
  return { ...actual, okulApi: okul };
});

import OnurBelgeleriPanel from "./OnurBelgeleriPanel";

const BASE: HonorCertificate = {
  id: 1,
  student: 5,
  student_name: "Ali Veli",
  school_year: 1,
  status: "AWARDED",
  status_display: "Ödül ve disiplin kurulu kabul etti",
  proposer_role: "TEACHER",
  proposer_role_display: "Öğretmen",
  proposer_name: "",
  criteria: ["LANGUAGE"],
  justification: "",
  recommended_at: "2026-05-25",
  awarded_at: "2026-06-01",
  rejection_reason: "",
  rejected_at: null,
};

afterEach(() => vi.clearAllMocks());

describe("OnurBelgeleriPanel — son adımı geri al (M8)", () => {
  it("kurul kabulünü gerekçeyle geri alır; gerekçesiz göndermez", async () => {
    const user = userEvent.setup();
    odul.listCertificates.mockResolvedValue([BASE]);
    render(<OnurBelgeleriPanel />);
    await user.click(await screen.findByRole("button", { name: /Son adımı geri al/ }));
    await user.click(screen.getByRole("button", { name: /^undo Geri al$|^Geri al$/ }));
    expect(await screen.findByText("Geri alma gerekçesi zorunludur.")).toBeInTheDocument();
    expect(odul.undoCertificateStep).not.toHaveBeenCalled();

    await user.type(screen.getByLabelText(/Geri alma gerekçesi/), "Yanlış öğrenci.");
    await user.click(screen.getByRole("button", { name: /^undo Geri al$|^Geri al$/ }));
    await waitFor(() =>
      expect(odul.undoCertificateStep).toHaveBeenCalledWith(1, { reason: "Yanlış öğrenci." }),
    );
    await waitFor(() => expect(odul.listCertificates).toHaveBeenCalledTimes(2));
  });

  it("müdür onaylı belgede ve teklif aşamasında geri alma yok", async () => {
    odul.listCertificates.mockResolvedValue([
      { ...BASE, id: 2, status: "PRINCIPAL_APPROVED", status_display: "Okul müdürü onayladı" },
      { ...BASE, id: 3, status: "PROPOSED", status_display: "Teklif edildi", student_name: "Can" },
    ]);
    render(<OnurBelgeleriPanel />);
    const list = await screen.findByRole("list");
    expect(within(list).getByText("Can")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Son adımı geri al/ })).not.toBeInTheDocument();
  });
});
