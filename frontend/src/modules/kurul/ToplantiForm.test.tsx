// Toplantı kaydı formu — kullanıcı kararı 14.11.2026, S5: Ödül ve Disiplin Kurulu bileşimi
// md. 185/1'e uymuyorsa toplantı kaydı ekranında UYARILIR; kayıt ENGELLENMEZ. Onur Kurulu
// toplantısında bileşim uyarısı sorulmaz (md. 185/1 yalnız Ödül ve Disiplin Kuruludur).

import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { SnackbarProvider } from "../../ui/SnackbarProvider";

const kapi = vi.hoisted(() => ({
  prefill: vi.fn(),
  compositionWarnings: vi.fn(),
  createMeeting: vi.fn(),
  caseOptions: vi.fn(),
}));

vi.mock("./api", async (importActual) => {
  const actual = await importActual<typeof import("./api")>();
  return {
    ...actual,
    kurulApi: kapi,
    listSchoolYears: vi.fn(() =>
      Promise.resolve({
        school_years: [
          {
            id: 1,
            name: "2025-2026",
            start_date: "2025-09-08",
            end_date: "2026-06-26",
            is_active: true,
          },
        ],
      }),
    ),
  };
});

import ToplantiForm from "./ToplantiForm";

const CHAIR = {
  person_name: "Ayşe Başkan",
  title: "Kurul Başkanı (Müdür Yardımcısı)",
  attendee_role: "VOTING_MEMBER",
  is_chair: true,
  member_user_id: 7,
  member_student_id: null,
  order: 0,
};

const UYARI =
  "Kurul md. 185/1-ç'ye göre eksik: okul-aile birliği temsilcisi (öğrenci velisi) tanımlı değil.";

function form(councilType: "DISCIPLINE" | "HONOR", onCreated = vi.fn()) {
  render(
    <SnackbarProvider>
      <ToplantiForm councilType={councilType} onCreated={onCreated} onCancel={vi.fn()} />
    </SnackbarProvider>,
  );
  return onCreated;
}

afterEach(() => vi.clearAllMocks());

describe("ToplantiForm — md. 185/1 bileşim uyarısı (S5)", () => {
  it("eksik bileşimde uyarı gösterilir ve toplantı yine kaydedilir", async () => {
    const user = userEvent.setup();
    kapi.prefill.mockResolvedValue({ attendees: [CHAIR] });
    kapi.compositionWarnings.mockResolvedValue([UYARI]);
    kapi.createMeeting.mockResolvedValue({ id: 3, meeting_no_display: "T003" });
    const onCreated = form("DISCIPLINE");

    expect(await screen.findByText(UYARI)).toBeInTheDocument();
    expect(screen.getByText(/kayıt ve toplantı engellenmez/)).toBeInTheDocument();
    await screen.findByDisplayValue("Ayşe Başkan");

    await user.type(screen.getByLabelText("Toplantı Tarihi"), "2026-05-25");
    await user.click(screen.getByRole("button", { name: "Tutanağı Kaydet" }));
    await waitFor(() => expect(kapi.createMeeting).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(onCreated).toHaveBeenCalled());
  });

  it("bileşim uygunsa uyarı kartı yok; uyarı yüklenemezse form yine çalışır", async () => {
    kapi.prefill.mockResolvedValue({ attendees: [CHAIR] });
    kapi.compositionWarnings.mockRejectedValue(new Error("ağ"));
    form("DISCIPLINE");
    await screen.findByDisplayValue("Ayşe Başkan");
    expect(screen.queryByText(/kayıt ve toplantı engellenmez/)).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Tutanağı Kaydet" })).toBeEnabled();
  });

  it("Onur Kurulu toplantısında bileşim uyarısı sorulmaz", async () => {
    kapi.prefill.mockResolvedValue({ attendees: [] });
    form("HONOR");
    await waitFor(() => expect(kapi.prefill).toHaveBeenCalled());
    expect(kapi.compositionWarnings).not.toHaveBeenCalled();
  });
});
