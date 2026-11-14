// Müdür onayı paneli (04.10.2026): Ödül ve Disiplin Kurulunun kabul kararları müdüre sunulur;
// onaylama gerekçesiz yapılamaz, onay seçilen tarihle gider (md. 196/3; M8).

import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ConfirmProvider } from "../../ui/ConfirmProvider";
import type { HonorCertificate } from "../odul/api";

const odul = vi.hoisted(() => ({
  listCertificates: vi.fn(),
  principalApproveCertificate: vi.fn(() => Promise.resolve({})),
  principalRejectCertificate: vi.fn(() => Promise.resolve({})),
}));
const okul = vi.hoisted(() => ({
  listSchoolYears: vi.fn(() => Promise.resolve([{ id: 1, name: "2025-2026", is_active: true }])),
}));

vi.mock("../odul/api", async (importActual) => {
  const actual = await importActual<typeof import("../odul/api")>();
  return { ...actual, odulApi: odul };
});
vi.mock("../okul/api", async (importActual) => {
  const actual = await importActual<typeof import("../okul/api")>();
  return { ...actual, okulApi: okul };
});

import MudurOnayiPanel from "./MudurOnayiPanel";

const KABUL: HonorCertificate = {
  id: 3,
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

function panel() {
  return render(
    <ConfirmProvider>
      <MudurOnayiPanel />
    </ConfirmProvider>,
  );
}

/** Onay diyaloğundaki düğme (satırdaki "Onayla" ile aynı adı taşır). */
function dialogButton(dialog: HTMLElement, label: string): HTMLElement {
  return Array.from(dialog.querySelectorAll("button")).find((b) => b.textContent === label)!;
}

describe("MudurOnayiPanel", () => {
  it("onaylamama gerekçe ister; onay tarihiyle gönderilir", async () => {
    const user = userEvent.setup();
    odul.listCertificates.mockImplementation((params: { status?: string }) =>
      Promise.resolve(params.status === "AWARDED" ? [KABUL] : []),
    );
    panel();

    expect(await screen.findByText("Ali Veli")).toBeInTheDocument();
    expect(screen.getByText(/Kurul kabul kararı: 01.06.2026/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Onaylama" }));
    expect(screen.getByText(/gerekçesi zorunludur/)).toBeInTheDocument();
    expect(odul.principalRejectCertificate).not.toHaveBeenCalled();

    const tarih = screen.getByLabelText("Onay tarihi");
    await user.clear(tarih);
    await user.type(tarih, "2026-06-05");
    await user.click(screen.getByRole("button", { name: "Onayla" }));
    // Müdür onayı geri alınamaz: tek tıkla gitmez, onay diyaloğu sorar.
    const dialog = await screen.findByRole("dialog");
    expect(dialog).toHaveTextContent(/geri alınamaz/);
    expect(odul.principalApproveCertificate).not.toHaveBeenCalled();
    await user.click(dialogButton(dialog, "Onayla"));
    expect(odul.principalApproveCertificate).toHaveBeenCalledWith(3, {
      decided_on: "2026-06-05",
      explanation: "",
    });
  });

  it("onay diyaloğunda vazgeçilirse onay gönderilmez", async () => {
    const user = userEvent.setup();
    odul.listCertificates.mockImplementation((params: { status?: string }) =>
      Promise.resolve(params.status === "AWARDED" ? [KABUL] : []),
    );
    panel();
    await screen.findByText("Ali Veli");
    await user.click(screen.getByRole("button", { name: "Onayla" }));
    const dialog = await screen.findByRole("dialog");
    await user.click(dialogButton(dialog, "Vazgeç"));
    expect(odul.principalApproveCertificate).not.toHaveBeenCalled();
  });

  it("onay tarihi kurul kararından önce ya da ileri tarihli olamaz", async () => {
    const user = userEvent.setup();
    odul.listCertificates.mockImplementation((params: { status?: string }) =>
      Promise.resolve(params.status === "AWARDED" ? [KABUL] : []),
    );
    panel();
    await screen.findByText("Ali Veli");
    const tarih = screen.getByLabelText("Onay tarihi");

    await user.clear(tarih);
    await user.type(tarih, "2026-05-31");
    await user.click(screen.getByRole("button", { name: "Onayla" }));
    expect(
      screen.getByText(/kurul kabul kararından \(01\.06\.2026\) önce olamaz/),
    ).toBeInTheDocument();

    await user.clear(tarih);
    await user.type(tarih, "2999-01-01");
    await user.click(screen.getByRole("button", { name: "Onayla" }));
    expect(screen.getByText(/ileri bir tarih olamaz/)).toBeInTheDocument();

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(odul.principalApproveCertificate).not.toHaveBeenCalled();
  });

  it("bekleyen yoksa bilgi verir", async () => {
    odul.listCertificates.mockResolvedValue([]);
    panel();
    expect(await screen.findByText(/Onay bekleyen kurul kararı yok/)).toBeInTheDocument();
  });
});
