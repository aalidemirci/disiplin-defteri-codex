// Toplantı ekranı (04.10.2026, kurul işleyişi Aşama 1): kurul kararı gündem maddesinde
// verilir. Pinlenen davranışlar: Onur Kurulunda "Uygun gör / Uygun görme", Ödül ve Disiplin
// Kurulunda "Kabul et / Reddet"; olumsuz kararda gerekçe zorunlu; yeter sayı (md. 191/1)
// uyarısı; olumlu karar sonrası çizelge düğmesi; gündeme teklif ekleme.

import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { SnackbarProvider } from "../../ui/SnackbarProvider";
import type { AgendaItem, CouncilMeeting } from "./api";

const kapi = vi.hoisted(() => ({
  getMeeting: vi.fn(),
  decideAgendaItem: vi.fn(),
  removeAgendaItem: vi.fn(),
  addAgendaItems: vi.fn(),
  agendaCandidates: vi.fn(),
  updateMeeting: vi.fn(),
  minutes: vi.fn(),
}));

vi.mock("./api", async (importActual) => {
  const actual = await importActual<typeof import("./api")>();
  return { ...actual, kurulApi: kapi };
});
vi.mock("../odul/api", async (importActual) => {
  const actual = await importActual<typeof import("../odul/api")>();
  return {
    ...actual,
    odulApi: { recommendationRecord: vi.fn(), awardRecord: vi.fn() },
  };
});

import ToplantiDetay from "./ToplantiDetay";

const ITEM: AgendaItem = {
  id: 9,
  order: 1,
  item_type: "HONOR_PROPOSAL",
  honor_certificate: 3,
  student: 4,
  student_name: "Ali Veli",
  class_label: "10/A",
  criteria: ["MANNERS"],
  justification: "Görgü örnekliği.",
  proposer_role_display: "Öğretmen",
  certificate_status: "PROPOSED",
  outcome: "PENDING",
  outcome_display: "Karar bekliyor",
  decision_text: "",
  decision_basis: "UNANIMITY",
  dissent_note: "",
};

function meeting(overrides: Partial<CouncilMeeting> = {}): CouncilMeeting {
  return {
    id: 5,
    school_year: 1,
    council_type: "HONOR",
    council_type_display: "Onur Kurulu (md. 180)",
    meeting_no: 5,
    meeting_no_display: "T005",
    meeting_date: "2026-05-25",
    honor_meeting_kind: "BOARD",
    agenda: "",
    decision_text: "",
    decision_basis: "UNANIMITY",
    notes: "",
    minutes_type: "GENERAL",
    discipline_case: null,
    discipline_case_no: null,
    attendees: [
      {
        id: 1,
        attendee_role: "VOTING_MEMBER",
        person_name: "Onur Başkanı",
        title: "Onur Kurulu Başkanı",
        is_chair: true,
        dissent_note: "",
      },
    ],
    agenda_items: [ITEM],
    quorum: null,
    ...overrides,
  };
}

function ekran() {
  return render(
    <SnackbarProvider>
      <ToplantiDetay meetingId={5} onBack={vi.fn()} />
    </SnackbarProvider>,
  );
}

afterEach(() => vi.clearAllMocks());

describe("ToplantiDetay", () => {
  it("Onur Kurulu: uygun görmeme gerekçesiz verilmez; uygun görüş kaydedilir", async () => {
    const user = userEvent.setup();
    kapi.getMeeting.mockResolvedValue(meeting());
    kapi.decideAgendaItem.mockResolvedValue(
      meeting({
        agenda_items: [{ ...ITEM, outcome: "FAVORABLE", outcome_display: "Uygun görüldü" }],
      }),
    );
    ekran();

    expect(await screen.findByText(/Toplantı T005/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Uygun görme" }));
    expect(screen.getByText(/gerekçe zorunludur/)).toBeInTheDocument();
    expect(kapi.decideAgendaItem).not.toHaveBeenCalled();

    await user.click(screen.getByRole("button", { name: "Uygun gör" }));
    expect(kapi.decideAgendaItem).toHaveBeenCalledWith(5, 9, {
      outcome: "FAVORABLE",
      decision_text: "",
      decision_basis: "UNANIMITY",
      dissent_note: "",
    });
    expect(await screen.findByText("Uygun görüldü")).toBeInTheDocument();
    // Olumlu karar sonrası Ödül ve Disiplin Kuruluna sunulacak çizelge üretilebilir.
    expect(screen.getByRole("button", { name: /Teklif çizelgesi/ })).toBeInTheDocument();
  });

  it("Ödül ve Disiplin Kurulu: kabul/ret düğmeleri ve yeter sayı uyarısı", async () => {
    kapi.getMeeting.mockResolvedValue(
      meeting({
        council_type: "DISCIPLINE",
        council_type_display: "Ödül ve Disiplin Kurulu (md. 185)",
        honor_meeting_kind: undefined,
        quorum: { full: 5, required: 3, present: 2, ok: false },
      }),
    );
    ekran();
    expect(await screen.findByRole("button", { name: "Kabul et" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Reddet" })).toBeInTheDocument();
    expect(screen.getByText(/Yeter sayı yok/)).toBeInTheDocument();
    expect(screen.getByText(/en az 3 oy hakkı olan üye/)).toBeInTheDocument();
  });

  it("gündeme teklif ekler", async () => {
    const user = userEvent.setup();
    kapi.getMeeting.mockResolvedValue(meeting({ agenda_items: [] }));
    kapi.agendaCandidates.mockResolvedValue([
      {
        id: 11,
        student: 6,
        student_name: "Ayşe Yılmaz",
        school_year: 1,
        status: "PROPOSED",
        status_display: "Teklif edildi",
        proposer_role: "TEACHER",
        proposer_role_display: "Öğretmen",
        proposer_name: "",
        criteria: ["ATTENDANCE"],
        justification: "",
        recommended_at: null,
        awarded_at: null,
        rejection_reason: "",
        rejected_at: null,
      },
    ]);
    kapi.addAgendaItems.mockResolvedValue(meeting());
    ekran();

    await user.click(await screen.findByRole("button", { name: /Gündeme teklif ekle/ }));
    expect(kapi.agendaCandidates).toHaveBeenCalledWith("HONOR");
    await user.click(await screen.findByRole("checkbox", { name: /Ayşe Yılmaz/ }));
    await user.click(screen.getByRole("button", { name: "Gündeme al" }));
    expect(kapi.addAgendaItems).toHaveBeenCalledWith(5, [11]);
  });

  it("Onur Genel Kurulu toplantısında teklif görüşülmez", async () => {
    kapi.getMeeting.mockResolvedValue(
      meeting({ honor_meeting_kind: "GENERAL_ASSEMBLY", agenda_items: [] }),
    );
    ekran();
    expect(await screen.findByText(/teklifi görüşülmez/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Gündeme teklif ekle/ })).not.toBeInTheDocument();
  });
});
