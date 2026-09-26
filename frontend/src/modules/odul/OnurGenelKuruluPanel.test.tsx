// Onur genel kurulu paneli — md. 181/1 uyarısı (kullanıcı kararı 26.09.2026): disiplin
// cezası alan aktif temsilcide "üyeliği düşmeli" uyarısı görünür, program üyeliği kendisi
// sonlandırmaz; "Görevi sonlandır" gerekçeye md. 181/1 atfını yazar.

import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ConfirmProvider } from "../../ui/ConfirmProvider";
import { SnackbarProvider } from "../../ui/SnackbarProvider";
import type { HonorGeneralAssemblyMember } from "./api";

const odul = vi.hoisted(() => ({
  listGeneralAssemblyMembers: vi.fn(),
  getHonorCompliance: vi.fn(() => Promise.resolve({ configured: false, terms: [] })),
  endGeneralAssemblyMember: vi.fn<(id: number, body: { reason: string }) => Promise<unknown>>(() =>
    Promise.resolve({}),
  ),
  addGeneralAssemblyMember: vi.fn(),
}));
const okul = vi.hoisted(() => ({
  listSchoolYears: vi.fn(() => Promise.resolve([{ id: 1, name: "2025-2026", is_active: true }])),
  listSchoolTerms: vi.fn(() => Promise.resolve([])),
}));

vi.mock("./api", async (importActual) => {
  const actual = await importActual<typeof import("./api")>();
  return { ...actual, odulApi: odul };
});
vi.mock("../okul/api", async (importActual) => {
  const actual = await importActual<typeof import("../okul/api")>();
  return { ...actual, okulApi: okul };
});

import OnurGenelKuruluPanel from "./OnurGenelKuruluPanel";

function member(over: Partial<HonorGeneralAssemblyMember> = {}): HonorGeneralAssemblyMember {
  return {
    id: 5,
    school_year: 1,
    member_student: 9,
    member_name: "Ayşe Kaya",
    class_level: 11,
    class_section: "A",
    effective_from: "2025-09-08",
    effective_until: null,
    end_reason: "",
    replaced_member: null,
    is_active: true,
    md181_penalty: null,
    ...over,
  };
}

function renderPanel() {
  return render(
    <SnackbarProvider>
      <ConfirmProvider>
        <OnurGenelKuruluPanel />
      </ConfirmProvider>
    </SnackbarProvider>,
  );
}

afterEach(() => vi.clearAllMocks());

describe("OnurGenelKuruluPanel — md. 181/1", () => {
  it("cezasız temsilcide uyarı yok", async () => {
    odul.listGeneralAssemblyMembers.mockResolvedValue([member()]);
    renderPanel();
    expect(await screen.findByText("Ayşe Kaya")).toBeInTheDocument();
    expect(screen.queryByText(/md. 181\/1/)).not.toBeInTheDocument();
  });

  it("cezalı temsilcide uyarı görünür; sonlandırma gerekçesi md. 181/1 atfı taşır", async () => {
    const user = userEvent.setup();
    odul.listGeneralAssemblyMembers.mockResolvedValue([
      member({
        md181_penalty: {
          penalty_type_display: "Kınama",
          decision_no: "2025-2026/0003",
          decision_date: "2026-05-20",
        },
      }),
    ]);
    renderPanel();
    expect(await screen.findByText(/md. 181\/1: Kınama cezası aldı/)).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Görevi sonlandır" }));
    const dialog = await screen.findByRole("dialog");
    await user.click(
      Array.from(dialog.querySelectorAll("button")).find(
        (b) => b.textContent === "Görevi sonlandır",
      )!,
    );
    await waitFor(() => expect(odul.endGeneralAssemblyMember).toHaveBeenCalled());
    expect(odul.endGeneralAssemblyMember.mock.calls[0][1]).toMatchObject({
      reason: "md. 181/1: disiplin cezası (2025-2026/0003)",
    });
  });
});
