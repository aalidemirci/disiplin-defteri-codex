// TutanakListesi testi: tür-sabit liste (T-numara gösterimi), disiplin
// tarafında tutanak türü + dosya sütunu, onur tarafında sade tablo, 403 kilit kartı.
//
// OYS `modules/kurul/TutanakListesi.test.tsx`'ten UYARLANDI (F4-D3); sapmalar:
// serializer display/attendee_count/created_at alanları factory'den kalktı;
// listSchoolYears mock'u `../sistem/api` yerine `./api` üzerinden.

import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "../../lib/api";
import { ConfirmProvider } from "../../ui/ConfirmProvider";
import { SnackbarProvider } from "../../ui/SnackbarProvider";
import type { CouncilMeeting } from "./api";

const kapi = vi.hoisted(() => ({
  listMeetings: vi.fn(),
  minutes: vi.fn(),
  deleteMeeting: vi.fn(),
  prefill: vi.fn(() => Promise.resolve({ attendees: [] })),
  caseOptions: vi.fn(() => Promise.resolve({ cases: [] })),
}));

vi.mock("./api", async (importActual) => {
  const actual = await importActual<typeof import("./api")>();
  return {
    ...actual,
    kurulApi: kapi,
    listSchoolYears: vi.fn(() => Promise.resolve({ school_years: [] })),
  };
});

import TutanakListesi from "./TutanakListesi";

function meeting(overrides: Partial<CouncilMeeting>): CouncilMeeting {
  return {
    id: 1,
    school_year: 1,
    council_type: "DISCIPLINE",
    council_type_display: "Ödül ve Disiplin Kurulu (md. 185)",
    meeting_no: 1,
    meeting_no_display: "T001",
    meeting_date: "2026-05-26",
    agenda: "",
    decision_text: "",
    decision_basis: "UNANIMITY",
    notes: "",
    minutes_type: "GENERAL",
    discipline_case: null,
    discipline_case_no: null,
    attendees: [],
    ...overrides,
  };
}

function renderListe(councilType: "DISCIPLINE" | "HONOR") {
  return render(
    <SnackbarProvider>
      <ConfirmProvider>
        <MemoryRouter>
          <TutanakListesi councilType={councilType} />
        </MemoryRouter>
      </ConfirmProvider>
    </SnackbarProvider>,
  );
}

afterEach(() => vi.clearAllMocks());

describe("TutanakListesi", () => {
  it("disiplin: T-numara + tutanak türü + dosya bağlantısı gösterilir", async () => {
    kapi.listMeetings.mockResolvedValue([
      meeting({
        id: 2,
        meeting_no: 2,
        meeting_no_display: "T002",
        minutes_type: "CASE_REVIEW",
        discipline_case: 7,
        discipline_case_no: "2026-0007",
      }),
    ]);
    renderListe("DISCIPLINE");
    expect(await screen.findByText("T002")).toBeInTheDocument();
    expect(screen.getByText("Disiplin dosyası görüşme")).toBeInTheDocument();
    const link = screen.getByRole("link", { name: "2026-0007" });
    expect(link).toHaveAttribute("href", "/disiplin/7");
    expect(kapi.listMeetings).toHaveBeenCalledWith("DISCIPLINE");
  });

  it("onur: tür/dosya sütunu yok, T-numara var", async () => {
    kapi.listMeetings.mockResolvedValue([
      meeting({
        council_type: "HONOR",
        council_type_display: "Onur Kurulu (md. 180)",
        meeting_no_display: "T001",
      }),
    ]);
    renderListe("HONOR");
    expect(await screen.findByText("T001")).toBeInTheDocument();
    expect(screen.queryByText("Tür")).not.toBeInTheDocument();
    expect(screen.queryByText("Dosya")).not.toBeInTheDocument();
    expect(kapi.listMeetings).toHaveBeenCalledWith("HONOR");
  });

  it("403: kilit kartı gösterilir (backend yetki kapısı)", async () => {
    kapi.listMeetings.mockRejectedValue(new ApiError(403, "permission_denied", "Yetki yok."));
    renderListe("HONOR");
    expect(
      await screen.findByText(/toplantı tutanaklarını görüntüleme yetkiniz yok/i),
    ).toBeInTheDocument();
  });

  it("boş liste: bilgilendirme metni", async () => {
    kapi.listMeetings.mockResolvedValue([]);
    renderListe("DISCIPLINE");
    expect(await screen.findByText(/henüz tutanak bulunmuyor/i)).toBeInTheDocument();
  });
});
