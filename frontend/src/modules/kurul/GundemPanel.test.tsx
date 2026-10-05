// Kurul gündemi (04.10.2026): bekleyen teklifler seçilip toplantı açılır; teklifler
// toplantıyla birlikte gündeme alınır ve açılan toplantıya (?sekme&toplanti) yönlenir.

import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, useLocation } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { SnackbarProvider } from "../../ui/SnackbarProvider";
import type { HonorCertificate } from "../odul/api";
import type { CouncilMeeting } from "./api";

const kapi = vi.hoisted(() => ({
  agendaCandidates: vi.fn(),
  listMeetings: vi.fn(),
  createMeeting: vi.fn(),
  prefill: vi.fn(() =>
    Promise.resolve({
      attendees: [
        {
          attendee_role: "VOTING_MEMBER" as const,
          person_name: "Kurul Başkanı",
          is_chair: true,
        },
      ],
    }),
  ),
  caseOptions: vi.fn(),
}));

vi.mock("./api", async (importActual) => {
  const actual = await importActual<typeof import("./api")>();
  return {
    ...actual,
    kurulApi: kapi,
    listSchoolYears: vi.fn(() =>
      Promise.resolve({
        school_years: [{ id: 1, name: "2025-2026", start_date: "", end_date: "", is_active: true }],
      }),
    ),
  };
});

import GundemPanel from "./GundemPanel";

const TEKLIF: HonorCertificate = {
  id: 11,
  student: 6,
  student_name: "Ayşe Yılmaz",
  school_year: 1,
  status: "HONOR_BOARD_RECOMMENDED",
  status_display: "Onur kurulu uygun gördü",
  proposer_role: "TEACHER",
  proposer_role_display: "Öğretmen",
  proposer_name: "",
  criteria: ["ATTENDANCE"],
  justification: "Düzenli devam.",
  recommended_at: "2026-05-25",
  awarded_at: null,
  rejection_reason: "",
  rejected_at: null,
};

function Konum() {
  const location = useLocation();
  return <div data-testid="konum">{location.search}</div>;
}

function ekran() {
  return render(
    <SnackbarProvider>
      <MemoryRouter initialEntries={["/odul-disiplin-kurulu?sekme=gundem"]}>
        <GundemPanel councilType="DISCIPLINE" meetingsTab="toplantilar" />
        <Konum />
      </MemoryRouter>
    </SnackbarProvider>,
  );
}

afterEach(() => vi.clearAllMocks());

describe("GundemPanel", () => {
  it("seçilen tekliflerle toplantı açar ve toplantıya yönlenir", async () => {
    const user = userEvent.setup();
    kapi.agendaCandidates.mockResolvedValue([TEKLIF]);
    kapi.listMeetings.mockResolvedValue([]);
    kapi.createMeeting.mockResolvedValue({ id: 42, meeting_no_display: "T003" } as CouncilMeeting);
    ekran();

    expect(await screen.findByText("Ayşe Yılmaz")).toBeInTheDocument();
    expect(screen.getByText(/Onur Kurulu uygun görüşü: 25.05.2026/)).toBeInTheDocument();
    const ac = screen.getByRole("button", { name: /Seçilenlerle toplantı aç/ });
    expect(ac).toBeDisabled();
    await user.click(screen.getByRole("checkbox"));
    await user.click(ac);

    expect(await screen.findByText(/Gündeme alınacak teklifler \(1\)/)).toBeInTheDocument();
    await user.type(screen.getByLabelText("Toplantı Tarihi"), "2026-06-01");
    await user.click(screen.getByRole("button", { name: "Toplantıyı aç" }));

    expect(kapi.createMeeting).toHaveBeenCalledWith(
      expect.objectContaining({
        council_type: "DISCIPLINE",
        meeting_date: "2026-06-01",
        honor_certificate_ids: [11],
      }),
    );
    expect(await screen.findByTestId("konum")).toHaveTextContent("sekme=toplantilar&toplanti=42");
  });

  it("karar bekleyen toplantıları listeler; boş gündemde bilgi verir", async () => {
    kapi.agendaCandidates.mockResolvedValue([]);
    kapi.listMeetings.mockResolvedValue([
      {
        id: 7,
        council_type: "DISCIPLINE",
        meeting_no_display: "T002",
        meeting_date: "2026-06-01",
        agenda_items: [{ outcome: "PENDING" }, { outcome: "FAVORABLE" }],
      },
      { id: 8, council_type: "DISCIPLINE", meeting_no_display: "T001", agenda_items: [] },
    ]);
    ekran();
    expect(await screen.findByText(/Karar bekleyen toplantılar \(1\)/)).toBeInTheDocument();
    expect(screen.getByText(/1 madde karar bekliyor/)).toBeInTheDocument();
    expect(screen.getByText(/kurul kararı bekleyen öneri yok/)).toBeInTheDocument();
  });
});
