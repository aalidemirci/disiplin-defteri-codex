// Kullanıcı kararı, 14.11.2026 — S7 (VEKÂLET KAYDI, md. 188 / 191/2): toplantı ayrıntısında
// "Başkan katılmadı; … başkanlık etti (md. 188)" satırı ve katılımcı düzeltmesinde vekâlet
// kutusu. Vekâletsiz toplantıda ve Onur Kurulunda (md. 182) ekran değişmez.

import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { SnackbarProvider } from "../../ui/SnackbarProvider";
import type { CouncilMeeting } from "./api";

const kapi = vi.hoisted(() => ({
  getMeeting: vi.fn(),
  updateMeeting: vi.fn(),
  actingChairOptions: vi.fn(),
}));

vi.mock("./api", async (importActual) => {
  const actual = await importActual<typeof import("./api")>();
  return { ...actual, kurulApi: kapi };
});
vi.mock("../odul/api", async (importActual) => {
  const actual = await importActual<typeof import("../odul/api")>();
  return { ...actual, odulApi: { recommendationRecord: vi.fn(), awardRecord: vi.fn() } };
});

import ToplantiDetay from "./ToplantiDetay";

function meeting(overrides: Partial<CouncilMeeting> = {}): CouncilMeeting {
  return {
    id: 5,
    school_year: 1,
    council_type: "DISCIPLINE",
    council_type_display: "Ödül ve Disiplin Kurulu (md. 185)",
    meeting_no: 5,
    meeting_no_display: "T005",
    meeting_date: "2026-05-25",
    agenda: "",
    decision_text: "",
    decision_basis: "UNANIMITY",
    notes: "",
    minutes_type: "GENERAL",
    discipline_case: null,
    discipline_case_no: null,
    chair_absent: true,
    attendees: [
      {
        id: 1,
        attendee_role: "VOTING_MEMBER",
        person_name: "İpek Öğretmen",
        title: "Öğretmen",
        is_chair: true,
        dissent_note: "",
        member_user: 71,
      },
      {
        id: 2,
        attendee_role: "VOTING_MEMBER",
        person_name: "Ilgaz Şahin",
        title: "Öğretmen",
        is_chair: false,
        dissent_note: "",
        member_user: 72,
      },
    ],
    agenda_items: [],
    quorum: { full: 3, required: 2, present: 2, ok: true, unmatched: [] },
    ...overrides,
  };
}

const SECENEKLER = {
  chair: 70,
  chair_name: "Ayşe Başkan",
  chair_conflicted: false,
  eligible: [
    { member_id: 11, member_user: 71, member_name: "İpek Öğretmen", title: "" },
    { member_id: 12, member_user: 72, member_name: "Ilgaz Şahin", title: "" },
  ],
};

function ekran() {
  return render(
    <SnackbarProvider>
      <ToplantiDetay meetingId={5} onBack={vi.fn()} />
    </SnackbarProvider>,
  );
}

afterEach(() => vi.clearAllMocks());

describe("ToplantiDetay — başkan vekâleti (S7)", () => {
  it("vekâletli toplantıda 'Başkan katılmadı; … başkanlık etti (md. 188)' satırı görünür", async () => {
    kapi.getMeeting.mockResolvedValue(meeting());
    ekran();
    expect(
      await screen.findByText(/Başkan katılmadı; İpek Öğretmen başkanlık etti \(md\. 188\)/),
    ).toBeInTheDocument();
    expect(screen.getByText("(Başkanlık eden)")).toBeInTheDocument();
  });

  it("vekâletsiz toplantıda satır yoktur; başkan 'Başkan' olarak gösterilir", async () => {
    kapi.getMeeting.mockResolvedValue(meeting({ chair_absent: false }));
    ekran();
    expect(await screen.findByText(/Toplantı T005/)).toBeInTheDocument();
    expect(screen.queryByText(/Başkan katılmadı/)).not.toBeInTheDocument();
    expect(screen.getByText("(Başkan)")).toBeInTheDocument();
  });

  it("vekâlet uyarıları (yedek çağrılmamış / dosya toplantısıyla çelişki) kartta gösterilir", async () => {
    kapi.getMeeting.mockResolvedValue(
      meeting({ chair_warnings: ["Başkan katılmadı ama katılanlar arasında yedek üye yok."] }),
    );
    ekran();
    expect(await screen.findByText(/katılanlar arasında yedek üye yok/)).toBeInTheDocument();
    expect(screen.getByText(/uyarıdır; kayıt engellenmez/)).toBeInTheDocument();
  });

  it("başkanlık eden sonradan kuruldan çıkarıldıysa katılımcı düzeltmesi kilitlenmez", async () => {
    const user = userEvent.setup();
    kapi.getMeeting.mockResolvedValue(meeting());
    // İpek Öğretmen (71) artık kurulda değil: aday listesinde yok.
    kapi.actingChairOptions.mockResolvedValue({
      ...SECENEKLER,
      eligible: SECENEKLER.eligible.filter((c) => c.member_user !== 71),
    });
    kapi.updateMeeting.mockResolvedValue(meeting());
    ekran();
    await user.click(await screen.findByRole("button", { name: /Katılımcıları düzenle/ }));
    await screen.findByRole("checkbox", { name: /Başkan toplantıya katılmadı/ });
    // Kayıtlı başkanlık eden seçim kutusunda adıyla görünür ("Seçin…" değil).
    expect(screen.getByRole("option", { name: "İpek Öğretmen (kayıtlı)" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Katılımcıları kaydet" }));
    expect(kapi.updateMeeting).toHaveBeenCalledTimes(1);
    const body = kapi.updateMeeting.mock.calls[0][1] as {
      attendees: { person_name: string; is_chair: boolean }[];
    };
    expect(body.attendees.filter((a) => a.is_chair).map((a) => a.person_name)).toEqual([
      "İpek Öğretmen",
    ]);
  });

  // G1 (14.11.2026): S7 öncesi kaydedilmiş, başkanı şikâyetçi / zarar gören dosyanın
  // tutanağı düzenlenirken vekâlet ZORLANMAZ — kullanıcı başka bir satırı düzeltebilmelidir
  // (uygun öğretmen üye olmasa bile); zorlama yalnız YENİ kayıtta (ToplantiForm).
  it("eski tutanakta başkan şikâyetçi olsa da kutu zorlanmaz; başkan satırı korunarak kaydedilir", async () => {
    const user = userEvent.setup();
    const eski = meeting({
      chair_absent: false,
      minutes_type: "CASE_REVIEW",
      discipline_case: 9,
      discipline_case_no: "2025-2026-0002",
      chair_warnings: [
        "Kurul başkanı bu tutanağın dosyasında şikâyetçi/zarar gören (md. 191/2) ama tutanak başkan katılmış olarak kayıtlı.",
      ],
      attendees: [
        {
          id: 1,
          attendee_role: "VOTING_MEMBER",
          person_name: "Ayşe Başkan",
          title: "Kurul Başkanı",
          is_chair: true,
          dissent_note: "",
          member_user: 70,
        },
        {
          id: 2,
          attendee_role: "VOTING_MEMBER",
          person_name: "Ilgaz Şahin",
          title: "Öğretmen",
          is_chair: false,
          dissent_note: "",
          member_user: 72,
        },
      ],
    });
    kapi.getMeeting.mockResolvedValue(eski);
    // Uygun öğretmen üye de yok: eski davranışta kayıt hiç yapılamıyordu (tek yönlü kapan).
    kapi.actingChairOptions.mockResolvedValue({
      ...SECENEKLER,
      chair_conflicted: true,
      eligible: [],
    });
    kapi.updateMeeting.mockResolvedValue(eski);
    ekran();
    // Kalıcı uyarı sunucudan gelir ve ekran okuyucuya duyurulur.
    const uyari = await screen.findByText(/tutanak başkan katılmış olarak kayıtlı/);
    expect(uyari.closest('[role="status"]')).not.toBeNull();

    await user.click(screen.getByRole("button", { name: /Katılımcıları düzenle/ }));
    const kutu = await screen.findByRole("checkbox", { name: /Başkan toplantıya katılmadı/ });
    expect(kutu).not.toBeChecked();
    expect(kutu).toBeEnabled();
    // Başkan satırı silinmedi.
    expect(screen.getByDisplayValue("Ayşe Başkan")).toBeInTheDocument();
    // Neden uyarıldığı düzenleme alanında da yazılıdır (zorlama değil, bilgi).
    expect(screen.getByText(/Bu kayıt kendiliğinden değiştirilmez/)).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Katılımcıları kaydet" }));
    expect(kapi.updateMeeting).toHaveBeenCalledTimes(1);
    const body = kapi.updateMeeting.mock.calls[0][1] as {
      chair_absent: boolean;
      attendees: { person_name: string; is_chair: boolean }[];
    };
    expect(body.chair_absent).toBe(false);
    expect(body.attendees.filter((a) => a.is_chair).map((a) => a.person_name)).toEqual([
      "Ayşe Başkan",
    ]);
  });

  // G2 (14.11.2026): "başkan katılmadı" kayıtlı toplantıda bugünkü başkanla eşleştiği için
  // sayılmayan satır sessizce düşmez — yeter sayı kartında nedeniyle görünür.
  it("yeter sayıya girmeyen 'bugünkü başkan' satırı nedeniyle listelenir", async () => {
    kapi.getMeeting.mockResolvedValue(
      meeting({
        quorum: {
          full: 3,
          required: 2,
          present: 1,
          ok: false,
          unmatched: [],
          chair_skipped: ["İpek Öğretmen"],
        },
      }),
    );
    ekran();
    expect(
      await screen.findByText(/İpek Öğretmen bugün kurul başkanı olarak kayıtlı/),
    ).toBeInTheDocument();
    expect(screen.getByText(/başkan değişikliğinin geçmişi tutulmaz/)).toBeInTheDocument();
  });

  it("Onur Kurulu toplantısının katılımcı düzeltmesinde vekâlet kutusu sorulmaz", async () => {
    const user = userEvent.setup();
    kapi.getMeeting.mockResolvedValue(
      meeting({ council_type: "HONOR", chair_absent: false, quorum: null }),
    );
    ekran();
    await user.click(await screen.findByRole("button", { name: /Katılımcıları düzenle/ }));
    expect(kapi.actingChairOptions).not.toHaveBeenCalled();
    expect(screen.queryByRole("checkbox", { name: /Başkan toplantıya katılmadı/ })).toBeNull();
  });

  it("katılımcı düzeltmesinde başkanlık eden değiştirilir ve chair_absent gönderilir", async () => {
    const user = userEvent.setup();
    kapi.getMeeting.mockResolvedValue(meeting());
    kapi.actingChairOptions.mockResolvedValue(SECENEKLER);
    kapi.updateMeeting.mockResolvedValue(meeting());
    ekran();
    await user.click(await screen.findByRole("button", { name: /Katılımcıları düzenle/ }));
    const kutu = await screen.findByRole("checkbox", { name: /Başkan toplantıya katılmadı/ });
    expect(kutu).toBeChecked();
    const secim = screen.getByLabelText(/Başkanlık eden öğretmen üye/);
    expect(secim).toHaveValue("11");
    await user.selectOptions(secim, "12");
    await user.click(screen.getByRole("button", { name: "Katılımcıları kaydet" }));
    expect(kapi.updateMeeting).toHaveBeenCalledWith(
      5,
      expect.objectContaining({ chair_absent: true }),
    );
    const body = kapi.updateMeeting.mock.calls[0][1] as {
      attendees: { person_name: string; is_chair: boolean }[];
    };
    expect(body.attendees.filter((a) => a.is_chair).map((a) => a.person_name)).toEqual([
      "Ilgaz Şahin",
    ]);
  });
});
