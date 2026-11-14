// Resmî kararlar bölümü testi (F4 denetim bulguları 2/3/7/19/B3).
//
// Kapsam: (1) EK-1 anlatı panelinde girilen doğum tarihinin autosave debounce'una
// takılmadan kaydetme gövdesine girmesi, (2) "Kurula iade" edilmiş kararda onay
// durumu listesinin listede GERÇEKTEN bulunan bir değere ilklenmesi, (3) kapalı
// dosyada anlatı panelinin salt-okunur olması, (4) silinen kararı geri alınca hem
// aktif hem çöp kutusu listesinin tazelenmesi, (5) itiraz süresi mevzuat atfı.

import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "../../lib/api";
import { ConfirmProvider } from "../../ui/ConfirmProvider";
import { SnackbarProvider } from "../../ui/SnackbarProvider";
import type { DisciplineCase, DisciplineDecision, DisciplineMeeting } from "./api";

const dapi = vi.hoisted(() => ({
  listDecisions: vi.fn(),
  listMeetings: vi.fn(),
  updateDecision: vi.fn(),
  rebindDecisionMeeting: vi.fn(),
  listDeletedDecisions: vi.fn(),
  deleteDecision: vi.fn(),
  restoreDecision: vi.fn(),
  updateDecisionNarrative: vi.fn(),
  recompilePriorPenalties: vi.fn(),
  approveDecision: vi.fn(),
  confirmESchoolEntry: vi.fn(),
  createDecision: vi.fn(),
  notifyDecision: vi.fn(),
  resolveAppeal: vi.fn(),
  undoPenaltyRemoval: vi.fn(),
}));

// Yalnız tel katmanı (disiplinApi) mock'lanır; TR sözlükleri gerçek modülden gelir.
vi.mock("./api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("./api")>();
  return { ...actual, disiplinApi: dapi };
});

import DecisionsSection from "./DecisionsSection";

const EMPTY_NARRATIVE = {
  accused_statement_summary: "",
  witness_statement_summary: "",
  other_evidence: "",
  mitigating_aggravating: "",
  committee_opinion: "",
  psychosocial_summary: "",
  boarding_status: "",
  academic_standing: "",
  health_status: "",
  family_economic_status: "",
  lives_with_family: "",
  parents_alive: "",
  parents_biological: "",
  studies_near_family: "",
  upbringing_environment: "",
  family_residence_area: "",
  incident_place: "",
  prior_penalties_summary: "",
};

function makeDecision(over: Partial<DisciplineDecision> = {}): DisciplineDecision {
  return {
    ...EMPTY_NARRATIVE,
    id: 5,
    student: 3,
    student_name: "Zeynep Yılmaz",
    event: null,
    meeting: null,
    penalty_type: "REPRIMAND",
    penalty_type_display: "Kınama",
    statute_ref: "",
    penalty_detail: "",
    decision_no: "",
    decision_date: "2026-03-02",
    suspension_days: null,
    enforcement_start_date: null,
    incident_date: null,
    behavior_point_deduction: 5,
    approval_authority: "PRINCIPAL",
    approval_authority_display: "Okul müdürü",
    approval_status: "PENDING",
    approval_status_display: "Onay bekliyor",
    approved_at: null,
    return_reason: "",
    returned_at: null,
    notified_at: null,
    notification_method: "",
    appeal_deadline: null,
    is_enforced: false,
    referred_to_district: false,
    penalty_removed_on: null,
    penalty_removal_note: "",
    is_final: false,
    student_birth_date: null,
    notes: "",
    deleted_at: null,
    appeals: [],
    ...over,
  };
}

// S8: karar kayıtlı, yeter sayılı kurul toplantısına bağlı girilir.
function makeMeeting(over: Partial<DisciplineMeeting> = {}): DisciplineMeeting {
  return {
    id: 61,
    event: null,
    meeting_date: "2026-03-02",
    notes: "",
    attendees: [1, 2],
    attendee_names: ["Kemal Aksoy", "Selin Rehber"],
    chair_absent: false,
    acting_chair: null,
    acting_chair_name: "",
    quorum: { full: 3, required: 2, present: 3, ok: true },
    decisions: [],
    ...over,
  };
}

function makeCase(over: Partial<DisciplineCase> = {}): DisciplineCase {
  return {
    id: 1,
    case_no: "2026/1",
    petition_date: "2026-03-01",
    petitioner_name: "Ahmet Öğretmen",
    petitioner_role: "OGRETMEN",
    summary: "Olay özeti",
    current_stage: "DECIDED",
    current_stage_display: "Karar verildi",
    closed_at: null,
    students: [{ id: 3, full_name: "Zeynep Yılmaz", student_number: "123", class_label: "10-A" }],
    // Kurula sevkli dosya (md. 163/2 — karar girişi yalnız burada açık).
    events: [
      {
        id: 1,
        stage: "DECIDED",
        stage_display: "Müdür değerlendirmesi",
        event_date: "2026-03-01",
        recorded_at: "2026-03-01T09:00:00Z",
        notes: "",
        assigned_guidance_name: "",
        guidance_outcome: "",
        principal_decisions: ["DISCIPLINE_COMMITTEE"],
        committee_decision_type: null,
        committee_decision_type_name: null,
        committee_decision_text: "",
        is_override: false,
        override_reason: "",
      },
    ],
    ...over,
  };
}

function renderSection(caseObj: DisciplineCase = makeCase()) {
  return render(
    <SnackbarProvider>
      <ConfirmProvider>
        <DecisionsSection caseObj={caseObj} />
      </ConfirmProvider>
    </SnackbarProvider>,
  );
}

// Varsayılan: dosyada yeter sayılı TEK toplantı kayıtlı (karar girişi açık).
beforeEach(() => {
  dapi.listMeetings.mockResolvedValue([makeMeeting()]);
});

afterEach(() => {
  vi.clearAllMocks();
});

describe("DecisionsSection — S8: toplantı zorunlu", () => {
  const bos = { decisions: [], behavior_points: {} };

  it("toplantı yokken form açılmaz; önce toplantının kaydedilmesi söylenir", async () => {
    dapi.listDecisions.mockResolvedValue(bos);
    dapi.listMeetings.mockResolvedValue([]);
    renderSection();
    expect(
      await screen.findByText(/Karar girmek için önce kurul toplantısını kaydedin \(md\. 191\/1\)/),
    ).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Karar ekle" })).not.toBeInTheDocument();
  });

  it("yalnız yeter sayısız toplantı varken de karar eklenemez; çare söylenir", async () => {
    dapi.listDecisions.mockResolvedValue(bos);
    dapi.listMeetings.mockResolvedValue([
      makeMeeting({ quorum: { full: 5, required: 3, present: 2, ok: false } }),
    ]);
    renderSection();
    expect(await screen.findByText(/Kayıtlı toplantıların yeter sayısı yok/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Karar ekle" })).not.toBeInTheDocument();
  });

  it("kapalı dosyada toplantı yönlendirmesi gösterilmez", async () => {
    dapi.listDecisions.mockResolvedValue(bos);
    dapi.listMeetings.mockResolvedValue([]);
    renderSection(makeCase({ closed_at: "2026-04-01T10:00:00+03:00" }));
    expect(await screen.findByText(/Dosya kapalı; yeni resmî karar girilemez/)).toBeInTheDocument();
    expect(screen.queryByText(/önce kurul toplantısını kaydedin/)).not.toBeInTheDocument();
  });

  it("tek toplantı ön-seçilidir; karar tarihi salt-okunur toplantı tarihidir; gövdede tarih yok", async () => {
    const user = userEvent.setup();
    dapi.listDecisions.mockResolvedValue(bos);
    dapi.createDecision.mockResolvedValue(makeDecision());
    renderSection();
    await user.click(await screen.findByRole("button", { name: "Karar ekle" }));

    expect(screen.getByLabelText(/Kurul toplantısı/)).toHaveValue("61");
    const tarih = screen.getByLabelText(/Karar tarihi/);
    expect(tarih).toHaveValue("2026-03-02");
    expect(tarih).toHaveAttribute("readonly");
    expect(screen.getByText("Karar tarihi toplantı tarihidir.")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Kararı kaydet" }));
    await waitFor(() => expect(dapi.createDecision).toHaveBeenCalled());
    const body = dapi.createDecision.mock.calls[0][1];
    expect(body).toMatchObject({ student_id: 3, penalty_type: "REPRIMAND", meeting: 61 });
    expect(body).not.toHaveProperty("decision_date");
    // §7.5: karar eklenince kararlar VE toplantılar yeniden çekilir.
    await waitFor(() => expect(dapi.listMeetings).toHaveBeenCalledTimes(2));
  });

  it("birden çok toplantıda seçim zorunludur; yeter sayısız toplantı seçeneklerde yoktur", async () => {
    const user = userEvent.setup();
    dapi.listDecisions.mockResolvedValue(bos);
    dapi.listMeetings.mockResolvedValue([
      makeMeeting({ id: 62, meeting_date: "2026-03-09" }),
      makeMeeting({ id: 61 }),
      makeMeeting({
        id: 60,
        meeting_date: "2026-02-20",
        quorum: { full: 5, required: 3, present: 1, ok: false },
      }),
    ]);
    dapi.createDecision.mockResolvedValue(makeDecision());
    renderSection();
    await user.click(await screen.findByRole("button", { name: "Karar ekle" }));

    const select = screen.getByLabelText(/Kurul toplantısı/);
    expect(select).toHaveValue("");
    expect(within(select).queryByRole("option", { name: /20\.02\.2026/ })).toBeNull();
    expect(screen.getByRole("button", { name: "Kararı kaydet" })).toBeDisabled();

    await user.selectOptions(select, "62");
    expect(screen.getByLabelText(/Karar tarihi/)).toHaveValue("2026-03-09");
    await user.click(screen.getByRole("button", { name: "Kararı kaydet" }));
    await waitFor(() => expect(dapi.createDecision).toHaveBeenCalled());
    expect(dapi.createDecision.mock.calls[0][1]).toMatchObject({ meeting: 62 });
  });

  it("toplantısız girilmiş eski kararda 'Toplantı kaydı yok' bilgisi, bağlı kararda toplantı tarihi görünür", async () => {
    dapi.listDecisions.mockResolvedValue({
      decisions: [
        makeDecision(),
        makeDecision({ id: 6, student: 4, meeting: 61, meeting_date: "2026-03-02" }),
      ],
      behavior_points: {},
    });
    renderSection();
    expect(
      await screen.findByText(
        "Toplantı kaydı yok (bu karar toplantı zorunluluğundan önce girildi)",
      ),
    ).toBeInTheDocument();
    expect(screen.getByText("Toplantı: 02.03.2026")).toBeInTheDocument();
  });

  it("bağlı kararda düzenleme: tarih salt-okunur; başka toplantı seçilince gövdeye yalnız `meeting` gider", async () => {
    const user = userEvent.setup();
    dapi.listDecisions.mockResolvedValue({
      decisions: [makeDecision({ meeting: 61, meeting_date: "2026-03-02" })],
      behavior_points: {},
    });
    dapi.listMeetings.mockResolvedValue([
      makeMeeting({ id: 62, meeting_date: "2026-03-09" }),
      makeMeeting({ id: 61 }),
    ]);
    dapi.updateDecision.mockResolvedValue(makeDecision());
    renderSection();
    await user.click(await screen.findByRole("button", { name: "Düzenle" }));

    const select = screen.getByLabelText(/Kurul toplantısı/);
    expect(select).toHaveValue("61");
    // Bağ kaldırılamaz: boş seçenek sunulmaz.
    expect(within(select).queryByRole("option", { name: /Toplantıya bağlama/ })).toBeNull();
    expect(screen.getByLabelText(/Karar tarihi/)).toHaveAttribute("readonly");

    await user.selectOptions(select, "62");
    expect(screen.getByLabelText(/Karar tarihi/)).toHaveValue("2026-03-09");
    await user.click(screen.getByRole("button", { name: "Değişiklikleri kaydet" }));
    await waitFor(() => expect(dapi.updateDecision).toHaveBeenCalled());
    const body = dapi.updateDecision.mock.calls[0][2];
    expect(body).toMatchObject({ meeting: 62 });
    expect(body).not.toHaveProperty("decision_date");
  });

  it("bağlı kararda toplantı değişmeden kaydedilince gövdede ne `meeting` ne tarih vardır", async () => {
    const user = userEvent.setup();
    dapi.listDecisions.mockResolvedValue({
      decisions: [makeDecision({ meeting: 61, meeting_date: "2026-03-02" })],
      behavior_points: {},
    });
    dapi.updateDecision.mockResolvedValue(makeDecision());
    renderSection();
    await user.click(await screen.findByRole("button", { name: "Düzenle" }));
    await user.click(screen.getByRole("button", { name: "Değişiklikleri kaydet" }));
    await waitFor(() => expect(dapi.updateDecision).toHaveBeenCalled());
    const body = dapi.updateDecision.mock.calls[0][2];
    expect(body).not.toHaveProperty("meeting");
    expect(body).not.toHaveProperty("decision_date");
  });

  it("eski kararda düzenleme: tarih düzenlenebilir, toplantıya bağlama isteğe bağlıdır", async () => {
    const user = userEvent.setup();
    dapi.listDecisions.mockResolvedValue({ decisions: [makeDecision()], behavior_points: {} });
    dapi.updateDecision.mockResolvedValue(makeDecision());
    renderSection();
    await user.click(await screen.findByRole("button", { name: "Düzenle" }));

    const select = screen.getByLabelText(/Kurul toplantısı/);
    expect(select).toHaveValue(""); // toplantı ZORLANMAZ
    const tarih = screen.getByLabelText(/Karar tarihi/);
    expect(tarih).not.toHaveAttribute("readonly");
    fireEvent.change(tarih, { target: { value: "2026-03-05" } });
    await user.click(screen.getByRole("button", { name: "Değişiklikleri kaydet" }));
    await waitFor(() => expect(dapi.updateDecision).toHaveBeenCalledTimes(1));
    expect(dapi.updateDecision.mock.calls[0][2]).toMatchObject({ decision_date: "2026-03-05" });
    expect(dapi.updateDecision.mock.calls[0][2]).not.toHaveProperty("meeting");
  });

  it("eski kararda toplantı seçilirse tarih salt-okunur olur ve gövdeye `meeting` gider", async () => {
    const user = userEvent.setup();
    dapi.listDecisions.mockResolvedValue({ decisions: [makeDecision()], behavior_points: {} });
    dapi.updateDecision.mockResolvedValue(makeDecision());
    renderSection();
    await user.click(await screen.findByRole("button", { name: "Düzenle" }));
    await user.selectOptions(screen.getByLabelText(/Kurul toplantısı/), "61");
    expect(screen.getByLabelText(/Karar tarihi/)).toHaveAttribute("readonly");
    await user.click(screen.getByRole("button", { name: "Değişiklikleri kaydet" }));
    await waitFor(() => expect(dapi.updateDecision).toHaveBeenCalled());
    const body = dapi.updateDecision.mock.calls[0][2];
    expect(body).toMatchObject({ meeting: 61 });
    expect(body).not.toHaveProperty("decision_date");
  });

  const onayli = {
    approval_status: "APPROVED" as const,
    approval_status_display: "Onaylandı",
    approved_at: "2026-03-03",
  };

  it("onaylı eski karar aynı tarihli toplantıya bağlanabilir (tarih değişmez)", async () => {
    const user = userEvent.setup();
    dapi.listDecisions.mockResolvedValue({
      decisions: [makeDecision({ ...onayli })],
      behavior_points: {},
    });
    dapi.rebindDecisionMeeting.mockResolvedValue(makeDecision());
    renderSection();
    await user.click(await screen.findByRole("button", { name: "Toplantıya bağla" }));
    expect(screen.getByText(/Karar tarihi \(02\.03\.2026\) değişmez/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Bağla" }));
    await waitFor(() => expect(dapi.rebindDecisionMeeting).toHaveBeenCalledWith(1, 5, 61));
    // §7.5: bağ değişince kararlar ve toplantılar yeniden çekilir.
    await waitFor(() => expect(dapi.listDecisions).toHaveBeenCalledTimes(2));
    await waitFor(() => expect(dapi.listMeetings).toHaveBeenCalledTimes(2));
  });

  it("onaylı bağlı karar aynı tarihli BAŞKA toplantıya taşınabilir; sunucu reddi gösterilir", async () => {
    const user = userEvent.setup();
    dapi.listDecisions.mockResolvedValue({
      decisions: [makeDecision({ ...onayli, meeting: 61, meeting_date: "2026-03-02" })],
      behavior_points: {},
    });
    dapi.listMeetings.mockResolvedValue([makeMeeting({ id: 64 }), makeMeeting({ id: 61 })]);
    dapi.rebindDecisionMeeting.mockRejectedValue(
      new ApiError(400, "validation_error", "Dosya kapalı: karar değiştirilemez."),
    );
    renderSection();
    await user.click(await screen.findByRole("button", { name: "Toplantıyı değiştir" }));
    await user.click(screen.getByRole("button", { name: "Bağla" }));
    await waitFor(() => expect(dapi.rebindDecisionMeeting).toHaveBeenCalledWith(1, 5, 64));
    expect(await screen.findByText("Dosya kapalı: karar değiştirilemez.")).toBeInTheDocument();
  });

  it("aynı tarihli uygun toplantı yoksa ya da dosya kapalıysa bağlama eylemi sunulmaz", async () => {
    dapi.listDecisions.mockResolvedValue({
      decisions: [makeDecision({ ...onayli })],
      behavior_points: {},
    });
    dapi.listMeetings.mockResolvedValue([makeMeeting({ meeting_date: "2026-03-09" })]);
    const { unmount } = renderSection();
    await screen.findByRole("button", { name: "Onay durumu" });
    expect(
      screen.queryByRole("button", { name: /Toplantıya bağla|Toplantıyı değiştir/ }),
    ).toBeNull();
    unmount();

    dapi.listMeetings.mockResolvedValue([makeMeeting()]);
    renderSection(makeCase({ closed_at: "2026-04-01T10:00:00+03:00" }));
    await screen.findByText(/Toplantı kaydı yok/);
    expect(
      screen.queryByRole("button", { name: /Toplantıya bağla|Toplantıyı değiştir/ }),
    ).toBeNull();
  });

  it("geri yükleme reddi (sevkten önceki toplantı) sunucu iletisiyle gösterilir", async () => {
    const user = userEvent.setup();
    dapi.listDecisions.mockResolvedValue(bos);
    dapi.listDeletedDecisions.mockResolvedValue([
      makeDecision({ meeting: 70, meeting_date: "2026-03-02", deleted_at: "2026-03-04T10:00:00Z" }),
    ]);
    dapi.restoreDecision.mockRejectedValue(
      new ApiError(
        400,
        "validation_error",
        "Kararın bağlı olduğu toplantı (02.03.2026) dosyanın yürürlükteki kurula sevk tarihinden (10.03.2026) önce; karar geri yüklenemez.",
      ),
    );
    renderSection();
    await user.click(await screen.findByRole("button", { name: /Silinmiş kararlar/ }));
    await user.click(await screen.findByRole("button", { name: "Geri yükle" }));
    expect(
      await screen.findByText(/kurula sevk tarihinden \(10\.03\.2026\) önce/),
    ).toBeInTheDocument();
  });

  it("çöp kutusunda bağlı toplantısı silinmiş kararda 'Geri yükle' sunulmaz; nedeni yazılır", async () => {
    const user = userEvent.setup();
    dapi.listDecisions.mockResolvedValue(bos);
    dapi.listDeletedDecisions.mockResolvedValue([
      makeDecision({ meeting: 70, meeting_date: null, deleted_at: "2026-03-04T10:00:00Z" }),
    ]);
    renderSection();
    await user.click(await screen.findByRole("button", { name: /Silinmiş kararlar/ }));
    expect(
      await screen.findByText(/Bağlı toplantı kaydı silinmiş; karar geri yüklenemez/),
    ).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Geri yükle" })).not.toBeInTheDocument();
  });

  it("çöp kutusunda toplantısız girilmiş eski karar geri yüklenebilir", async () => {
    const user = userEvent.setup();
    dapi.listDecisions.mockResolvedValue(bos);
    dapi.listDeletedDecisions.mockResolvedValue([
      makeDecision({ meeting: null, meeting_date: null, deleted_at: "2026-03-04T10:00:00Z" }),
    ]);
    renderSection();
    await user.click(await screen.findByRole("button", { name: /Silinmiş kararlar/ }));
    expect(await screen.findByRole("button", { name: "Geri yükle" })).toBeInTheDocument();
  });

  it("yeter sayısız toplantıya karar bağlıysa 'silin' değil 'yeni toplantı kaydedin' denir", async () => {
    dapi.listDecisions.mockResolvedValue(bos);
    dapi.listMeetings.mockResolvedValue([
      makeMeeting({
        quorum: { full: 5, required: 3, present: 2, ok: false },
        decisions: [{ id: 9, student: 50, student_name: "Emre Can Yılmaz", decision_no: "" }],
      }),
    ]);
    renderSection();
    expect(await screen.findByText(/yeni bir toplantı kaydedin/)).toBeInTheDocument();
    expect(screen.queryByText(/toplantıyı silip/)).not.toBeInTheDocument();
  });

  it("toplantı listesi yüklenemezse hata kalır ve bağlı kararın tarihi salt-okunurdur", async () => {
    const user = userEvent.setup();
    // Önce toplantı hatası, SONRA kararların başarısı: hata iletisi silinmemeli.
    dapi.listMeetings.mockRejectedValue(new Error("ağ"));
    dapi.listDecisions.mockImplementation(
      () =>
        new Promise((resolve) =>
          setTimeout(
            () =>
              resolve({
                decisions: [makeDecision({ meeting: 61, meeting_date: "2026-03-02" })],
                behavior_points: {},
              }),
            20,
          ),
        ),
    );
    renderSection();
    await user.click(await screen.findByRole("button", { name: "Düzenle" }));
    expect(screen.getByRole("alert")).toHaveTextContent(/Kurul toplantıları yüklenemedi/);
    const tarih = screen.getByLabelText(/Karar tarihi/);
    expect(tarih).toHaveAttribute("readonly");
    expect(tarih).toHaveValue("2026-03-02");
    expect(screen.queryByLabelText(/Kurul toplantısı/)).not.toBeInTheDocument();
  });
});

describe("DecisionsSection — EK-1 anlatı", () => {
  it("doğum tarihi beklemeden kaydedilince gövdeye girer", async () => {
    dapi.listDecisions.mockResolvedValue({ decisions: [makeDecision()], behavior_points: {} });
    dapi.updateDecisionNarrative.mockResolvedValue({});
    const user = userEvent.setup();
    renderSection();

    await user.click(await screen.findByRole("button", { name: /EK-1 anlatı/ }));
    // type="date" alanında userEvent.type güvenilir değil — doğrudan change olayı.
    fireEvent.change(screen.getByLabelText(/Doğum tarihi/), { target: { value: "2009-04-15" } });
    // Autosave debounce'u (1200 ms) BEKLENMEZ: kullanıcı hemen kaydeder.
    await user.click(screen.getByRole("button", { name: /Anlatıyı kaydet/ }));

    await waitFor(() =>
      expect(dapi.updateDecisionNarrative).toHaveBeenCalledWith(
        1,
        5,
        expect.objectContaining({ student_birth_date: "2009-04-15" }),
      ),
    );
  });

  it("kapalı dosyada anlatı paneli salt-okunur", async () => {
    dapi.listDecisions.mockResolvedValue({ decisions: [makeDecision()], behavior_points: {} });
    const user = userEvent.setup();
    renderSection(makeCase({ closed_at: "2026-04-01", current_stage: "CLOSED" }));

    await user.click(await screen.findByRole("button", { name: /EK-1 anlatı/ }));

    expect(screen.getByText(/Dosya kapalı; anlatı düzenlenemez\./)).toBeInTheDocument();
    expect(screen.getByLabelText(/Doğum tarihi/)).toBeDisabled();
    expect(screen.getByLabelText(/Kurul kanaati/)).toBeDisabled();
    expect(screen.queryByRole("button", { name: /Anlatıyı kaydet/ })).not.toBeInTheDocument();
  });
});

// S11c (kullanıcı kararı 14.11.2026): EK-1 "önceki cezalar" özeti anlık kopyadır;
// kaynak cezalar değişince uyarı + onaylı "Yeniden derle" — otomatik derleme yok.
describe("DecisionsSection — önceki cezalar özeti güncel değil (S11c)", () => {
  const bayat = {
    prior_penalties_summary: "22.05.2026 — Kınama\nGenel durumu iyidir.",
    prior_penalties_stale: true,
  };
  const ozetAlani = () =>
    screen.getByLabelText(/Şimdiye kadar aldığı cezalar ve genel durumu/) as HTMLTextAreaElement;

  it("bayat özette uyarı çıkar; onaylanınca yeniden derlenir, alan ve liste tazelenir", async () => {
    dapi.listDecisions.mockResolvedValue({
      decisions: [makeDecision(bayat)],
      behavior_points: {},
    });
    dapi.recompilePriorPenalties.mockResolvedValue(
      makeDecision({ prior_penalties_summary: "", prior_penalties_stale: false }),
    );
    const user = userEvent.setup();
    renderSection();
    await user.click(await screen.findByRole("button", { name: /EK-1 anlatı/ }));

    expect(screen.getByRole("status")).toHaveTextContent(/Özet güncel değil/);
    await user.click(screen.getByRole("button", { name: "Yeniden derle" }));
    // Onay sorulmadan sunucuya gidilmez: elle düzenleme silinecek.
    const onay = await screen.findByRole("dialog");
    expect(onay).toHaveTextContent(/[Ee]lle yaptığınız düzenlemeler silinir/);
    expect(dapi.recompilePriorPenalties).not.toHaveBeenCalled();
    await user.click(within(onay).getByRole("button", { name: "Yeniden derle" }));

    await waitFor(() => expect(dapi.recompilePriorPenalties).toHaveBeenCalledWith(1, 5));
    await waitFor(() => expect(ozetAlani().value).toBe(""));
    expect(screen.queryByText(/Özet güncel değil/)).not.toBeInTheDocument();
    // §7.5: karar verisi tazelenir (ilk yükleme + yeniden derleme sonrası).
    await waitFor(() => expect(dapi.listDecisions).toHaveBeenCalledTimes(2));
    // Panel açık kalır; yeniden derlenen metin oto-kayıtla geri ezilmez.
    expect(screen.getByRole("button", { name: /Anlatıyı kaydet/ })).toBeInTheDocument();
    expect(dapi.updateDecisionNarrative).not.toHaveBeenCalled();
  });

  it("onay verilmezse özet değişmez", async () => {
    dapi.listDecisions.mockResolvedValue({
      decisions: [makeDecision(bayat)],
      behavior_points: {},
    });
    const user = userEvent.setup();
    renderSection();
    await user.click(await screen.findByRole("button", { name: /EK-1 anlatı/ }));
    await user.click(screen.getByRole("button", { name: "Yeniden derle" }));
    await user.click(
      within(await screen.findByRole("dialog")).getByRole("button", { name: /Vazgeç|İptal/ }),
    );

    expect(dapi.recompilePriorPenalties).not.toHaveBeenCalled();
    expect(ozetAlani().value).toBe(bayat.prior_penalties_summary);
    expect(screen.getByRole("status")).toHaveTextContent(/Özet güncel değil/);
  });

  it("sunucu reddederse hata gösterilir, uyarı kalır", async () => {
    dapi.listDecisions.mockResolvedValue({
      decisions: [makeDecision(bayat)],
      behavior_points: {},
    });
    dapi.recompilePriorPenalties.mockRejectedValue(
      new ApiError(400, "invalid", "Dosya kapalı: özet yeniden derlenemez."),
    );
    const user = userEvent.setup();
    renderSection();
    await user.click(await screen.findByRole("button", { name: /EK-1 anlatı/ }));
    await user.click(screen.getByRole("button", { name: "Yeniden derle" }));
    await user.click(
      within(await screen.findByRole("dialog")).getByRole("button", { name: "Yeniden derle" }),
    );

    expect(await screen.findByText(/Dosya kapalı: özet yeniden derlenemez\./)).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent(/Özet güncel değil/);
    expect(ozetAlani().value).toBe(bayat.prior_penalties_summary);
  });

  it("güncel özette uyarı ve düğme yoktur", async () => {
    dapi.listDecisions.mockResolvedValue({
      decisions: [makeDecision({ prior_penalties_stale: false })],
      behavior_points: {},
    });
    const user = userEvent.setup();
    renderSection();
    await user.click(await screen.findByRole("button", { name: /EK-1 anlatı/ }));

    expect(screen.queryByText(/Özet güncel değil/)).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Yeniden derle" })).not.toBeInTheDocument();
  });

  it("kapalı dosyada yalnız bilgi verilir, düğme yoktur", async () => {
    dapi.listDecisions.mockResolvedValue({
      decisions: [makeDecision(bayat)],
      behavior_points: {},
    });
    const user = userEvent.setup();
    renderSection(makeCase({ closed_at: "2026-04-01", current_stage: "CLOSED" }));
    await user.click(await screen.findByRole("button", { name: /EK-1 anlatı/ }));

    expect(screen.getByRole("status")).toHaveTextContent(/Özet güncel değil/);
    expect(screen.getByRole("status")).toHaveTextContent(/Dosya kapalı/);
    expect(screen.queryByRole("button", { name: "Yeniden derle" })).not.toBeInTheDocument();
  });

  // Gözden geçirme 14.11.2026: EK-1, anlatı paneli hiç açılmadan Evrak bölümünden
  // üretilebilir — uyarı yalnız panelde kalırsa kullanıcı bayat özeti görmeden basar.
  it("bayat özet karar KARTINDA da uyarılır (panel açılmadan)", async () => {
    dapi.listDecisions.mockResolvedValue({
      decisions: [makeDecision(bayat)],
      behavior_points: {},
    });
    renderSection();

    await screen.findByText("Zeynep Yılmaz"); // yükleme iskeleti de role=status taşır
    const uyari = screen.getByRole("status");
    expect(uyari).toHaveTextContent(/önceki cezalar.*özeti güncel değil/);
    expect(uyari).toHaveTextContent(/EK-1 anlatı.*panelinden yeniden derleyebilirsiniz/);
  });

  it("özet boşken de (sonradan onaylanan önceki ceza) kart uyarısı çıkar", async () => {
    dapi.listDecisions.mockResolvedValue({
      decisions: [makeDecision({ prior_penalties_summary: "", prior_penalties_stale: true })],
      behavior_points: {},
    });
    renderSection();

    await screen.findByText("Zeynep Yılmaz");
    expect(screen.getByRole("status")).toHaveTextContent(/özeti güncel değil/);
  });

  it("kapalı dosyada kart uyarısı yalnız bilgidir", async () => {
    dapi.listDecisions.mockResolvedValue({
      decisions: [makeDecision(bayat)],
      behavior_points: {},
    });
    renderSection(makeCase({ closed_at: "2026-04-01", current_stage: "CLOSED" }));

    await screen.findByText("Zeynep Yılmaz"); // yükleme iskeleti de role=status taşır
    const uyari = screen.getByRole("status");
    expect(uyari).toHaveTextContent(/Dosya kapalı olduğundan özet yeniden derlenemez/);
    expect(uyari).not.toHaveTextContent(/yeniden derleyebilirsiniz/);
  });

  it("güncel özette kart uyarısı yoktur", async () => {
    dapi.listDecisions.mockResolvedValue({
      decisions: [makeDecision({ prior_penalties_stale: false })],
      behavior_points: {},
    });
    renderSection();

    await screen.findByText("Zeynep Yılmaz");
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });

  it("panel açıkken liste tazelenip özet bayatlarsa panel uyarısı belirir (§7.5)", async () => {
    // İki karar: birinin anlatı paneli açık; diğeri silinince liste yeniden çekilir ve
    // açık paneldeki karar artık bayat döner — yerel durum prop'a eşitlenmeli.
    const acik = makeDecision({ prior_penalties_stale: false });
    const diger = makeDecision({ id: 6, student: 4, student_name: "Emre Kaya" });
    dapi.listDecisions
      .mockResolvedValueOnce({ decisions: [acik, diger], behavior_points: {} })
      .mockResolvedValue({
        decisions: [makeDecision({ prior_penalties_stale: true })],
        behavior_points: {},
      });
    dapi.listDeletedDecisions.mockResolvedValue([]);
    dapi.deleteDecision.mockResolvedValue(undefined);
    const user = userEvent.setup();
    renderSection(
      makeCase({
        students: [
          { id: 3, full_name: "Zeynep Yılmaz", student_number: "123", class_label: "10-A" },
          { id: 4, full_name: "Emre Kaya", student_number: "124", class_label: "10-A" },
        ],
      }),
    );

    await user.click((await screen.findAllByRole("button", { name: /EK-1 anlatı/ }))[0]);
    expect(screen.queryByText(/Özet güncel değil/)).not.toBeInTheDocument();

    // Paneli açık kartın eylem çubuğu gizlidir: kalan tek "Sil" diğer kararındır.
    await user.click(screen.getByRole("button", { name: "Sil" }));
    await user.click(
      within(await screen.findByRole("dialog")).getByRole("button", { name: "Sil" }),
    );

    await waitFor(() => expect(dapi.deleteDecision).toHaveBeenCalledWith(1, 6));
    expect(await screen.findByText(/Özet güncel değil/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Yeniden derle" })).toBeInTheDocument();
  });

  it("bekleyen oto-kayıt yazılamazsa yeniden derleme durur, hata gösterilir", async () => {
    // Yoksa hook'ta bekleyen ESKİ özet bir sonraki oto-kayıtta yeni derlemeyi ezerdi.
    dapi.listDecisions.mockResolvedValue({
      decisions: [makeDecision(bayat)],
      behavior_points: {},
    });
    dapi.updateDecisionNarrative.mockRejectedValue(new ApiError(500, "error", "Sunucu hatası."));
    const user = userEvent.setup();
    renderSection();
    await user.click(await screen.findByRole("button", { name: /EK-1 anlatı/ }));
    await user.type(ozetAlani(), " Elle not.");

    await user.click(screen.getByRole("button", { name: "Yeniden derle" }));
    await user.click(
      within(await screen.findByRole("dialog")).getByRole("button", { name: "Yeniden derle" }),
    );

    expect(
      await screen.findByText(
        /Bekleyen değişiklikler kaydedilemediği için özet yeniden derlenmedi/,
      ),
    ).toBeInTheDocument();
    expect(dapi.updateDecisionNarrative).toHaveBeenCalled();
    expect(dapi.recompilePriorPenalties).not.toHaveBeenCalled();
    expect(ozetAlani().value).toBe(`${bayat.prior_penalties_summary} Elle not.`);
    expect(screen.getByText(/Özet güncel değil/)).toBeInTheDocument();
  });

  it("bekleyen oto-kayıt yazılabilirse önce o yazılır, sonra yeniden derlenir", async () => {
    dapi.listDecisions.mockResolvedValue({
      decisions: [makeDecision(bayat)],
      behavior_points: {},
    });
    dapi.updateDecisionNarrative.mockResolvedValue({});
    dapi.recompilePriorPenalties.mockResolvedValue(
      makeDecision({ prior_penalties_summary: "", prior_penalties_stale: false }),
    );
    const user = userEvent.setup();
    renderSection();
    await user.click(await screen.findByRole("button", { name: /EK-1 anlatı/ }));
    await user.type(ozetAlani(), "!");
    await user.click(screen.getByRole("button", { name: "Yeniden derle" }));
    await user.click(
      within(await screen.findByRole("dialog")).getByRole("button", { name: "Yeniden derle" }),
    );

    await waitFor(() => expect(dapi.recompilePriorPenalties).toHaveBeenCalledWith(1, 5));
    expect(dapi.updateDecisionNarrative.mock.invocationCallOrder[0]).toBeLessThan(
      dapi.recompilePriorPenalties.mock.invocationCallOrder[0],
    );
    await waitFor(() => expect(ozetAlani().value).toBe(""));
  });
});

describe("DecisionsSection — onay durumu", () => {
  // Saha testi 14.11.2026 (bulgu 28): bu test eskiden formun PENDING'e ilklenip
  // dokunulmadan "Kaydet"te PENDING göndermesini sabitliyordu — o davranış md. 197
  // iadesini sessizce "onay bekliyor"a çeviriyordu. Artık form boş açılır, seçim ister.
  it("kurula iade edilmiş kararda form boş açılır; seçim yapılmadan kaydedilmez", async () => {
    dapi.listDecisions.mockResolvedValue({
      decisions: [
        makeDecision({
          approval_status: "RETURNED",
          approval_status_display: "Kurula iade edildi",
          return_reason: "Gerekçe yetersiz",
          returned_at: "2026-03-05",
        }),
      ],
      behavior_points: {},
    });
    dapi.approveDecision.mockResolvedValue({});
    const user = userEvent.setup();
    renderSection();

    await user.click(await screen.findByRole("button", { name: "Onay durumu" }));
    // Seçenekler PENDING/APPROVED ile süzülü; RETURNED listede yok → "Seçiniz…" görünmeli.
    const select = screen.getByLabelText("Onay durumu");
    expect(select).toHaveValue("");

    // Kullanıcı dokunmadan kaydedince hiçbir şey gitmemeli (iade sessizce bozulmaz).
    await user.click(screen.getByRole("button", { name: "Kaydet" }));
    expect(await screen.findByText("Onay durumunu seçin.")).toBeInTheDocument();
    expect(dapi.approveDecision).not.toHaveBeenCalled();

    // Bilinçli seçim (kurul yeniden görüşecek → onay bekliyor) kaydedilir.
    await user.selectOptions(select, "PENDING");
    await user.click(screen.getByRole("button", { name: "Kaydet" }));
    await waitFor(() =>
      expect(dapi.approveDecision).toHaveBeenCalledWith(1, 5, {
        approval_status: "PENDING",
        approved_on: null,
      }),
    );
  });
});

describe("DecisionsSection — silme/geri alma", () => {
  it("geri al: aktif liste ve çöp kutusu birlikte tazelenir", async () => {
    dapi.listDecisions.mockResolvedValue({ decisions: [makeDecision()], behavior_points: {} });
    dapi.listDeletedDecisions.mockResolvedValue([]);
    dapi.deleteDecision.mockResolvedValue(undefined);
    dapi.restoreDecision.mockResolvedValue(undefined);
    const user = userEvent.setup();
    renderSection();

    await user.click(await screen.findByRole("button", { name: "Sil" }));
    const dialog = await screen.findByRole("dialog");
    await user.click(within(dialog).getByRole("button", { name: "Sil" }));

    // Snackbar'daki "Geri al" görünür; kullanıcı ONDAN ÖNCE çöp kutusunu açıyor.
    const undo = await screen.findByRole("button", { name: "Geri al" });
    await user.click(screen.getByRole("button", { name: /Silinmiş kararlar/ }));
    await waitFor(() => expect(dapi.listDeletedDecisions).toHaveBeenCalledTimes(1));

    await user.click(undo);
    await waitFor(() => expect(dapi.restoreDecision).toHaveBeenCalledWith(1, 5));
    // Çöp kutusu açıkken geri alınan kayıt orada kalmamalı → liste yeniden çekilir.
    await waitFor(() => expect(dapi.listDeletedDecisions).toHaveBeenCalledTimes(2));
  });
});

describe("DecisionsSection — mevzuat atfı", () => {
  it("itiraz son günü md. 169/3'e atıfla anlatılır (169/5 tebliğdir)", async () => {
    dapi.listDecisions.mockResolvedValue({
      decisions: [
        makeDecision({
          approval_status: "APPROVED",
          approval_status_display: "Onaylandı",
          approved_at: "2026-03-02",
        }),
      ],
      behavior_points: {},
    });
    const user = userEvent.setup();
    renderSection();

    expect(await screen.findByText(/itiraz son günü \(md\. 169\/3\)/)).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Tebliğ kaydet" }));
    expect(
      screen.getByText(/itiraz son günü otomatik hesaplanır \(md\. 169\/3\)/),
    ).toBeInTheDocument();
  });
});

describe("DecisionsSection — mevzuat kilitleri (md. 163/2, 169/4, 197)", () => {
  it("onaysız kararda tebliğ düğmesi yok; bir kez iade edilmiş kararda yeniden iade yok", async () => {
    dapi.listDecisions.mockResolvedValue({
      decisions: [makeDecision({ returned_at: "2026-03-03" })],
      behavior_points: {},
    });
    renderSection();
    expect(await screen.findByRole("button", { name: "Onay durumu" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Tebliğ kaydet" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Kurula iade" })).not.toBeInTheDocument();
  });

  it("kurula sevksiz dosyada karar eklenemez", async () => {
    dapi.listDecisions.mockResolvedValue({ decisions: [], behavior_points: {} });
    renderSection(makeCase({ events: [] }));
    expect(
      await screen.findByText(/yalnız okul öğrenci ödül ve disiplin kuruluna sevk/),
    ).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Karar ekle" })).not.toBeInTheDocument();
  });

  it("itirazı sonuçlanmış kararda yeniden itiraz düğmesi yok", async () => {
    dapi.listDecisions.mockResolvedValue({
      decisions: [
        makeDecision({
          approval_status: "APPROVED",
          approval_status_display: "Onaylandı",
          notified_at: "2026-03-03",
          appeal_deadline: "2026-03-10",
          appeals: [
            {
              id: 9,
              decision: 5,
              filed_on: "2026-03-04",
              filed_by_role: "PARENT",
              filed_by_name: "Veli",
              within_deadline: true,
              appeal_authority: "DISTRICT_BOARD",
              appeal_authority_display: "İlçe öğrenci disiplin kurulu",
              forward_deadline: "2026-03-11",
              forwarded_on: "2026-03-05",
              result: "UPHELD",
              result_display: "Onandı (ceza aynen)",
              resulted_on: "2026-03-12",
              result_notes: "",
              previous_penalty_type: "",
              previous_suspension_days: null,
            },
          ],
        }),
      ],
      behavior_points: {},
    });
    renderSection();
    expect(await screen.findByText("Zeynep Yılmaz")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "İtiraz ekle" })).not.toBeInTheDocument();
  });
});

describe("DecisionsSection — e-Okul onayı", () => {
  it("kesinleşen cezayı hatırlatır ve işlenme tarihini kaydeder", async () => {
    dapi.listDecisions.mockResolvedValue({
      decisions: [
        makeDecision({
          is_final: true,
          approval_status: "APPROVED",
          approval_status_display: "Onaylandı",
          notified_at: "2026-03-03",
          appeal_deadline: "2026-03-10",
        }),
      ],
      behavior_points: {},
    });
    dapi.confirmESchoolEntry.mockResolvedValue({});
    const user = userEvent.setup();
    renderSection();

    expect(await screen.findByText(/Ceza kesinleşti/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "e-Okul'a işlendi" }));
    fireEvent.change(screen.getByLabelText(/e-Okul'a işlenme tarihi/), {
      target: { value: "2026-03-11" },
    });
    await user.click(screen.getByRole("button", { name: "Kaydet" }));

    await waitFor(() =>
      expect(dapi.confirmESchoolEntry).toHaveBeenCalledWith(1, 5, {
        processed_on: "2026-03-11",
      }),
    );
  });
});

describe("DecisionsSection — md. 166 aynı yılda tekrar", () => {
  const prior = {
    penalty_type: "REPRIMAND" as const,
    penalty_type_display: "Kınama",
    decision_no: "2025-2026/0001",
    decision_date: "2026-02-10",
  };

  it("aynı ceza için gerekçe ister, ağır cezada istemez; gerekçe gövdeye gider", async () => {
    const user = userEvent.setup();
    dapi.listDecisions.mockResolvedValue({
      decisions: [],
      behavior_points: {},
      md166_priors: { "3": prior },
    });
    dapi.createDecision.mockResolvedValue(makeDecision());
    renderSection();
    await user.click(await screen.findByRole("button", { name: "Karar ekle" }));

    expect(screen.getByText(/md. 166: öğrencinin bu öğretim yılında/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Kararı kaydet" }));
    expect(await screen.findByText("md. 166 gerekçesi zorunludur.")).toBeInTheDocument();
    expect(dapi.createDecision).not.toHaveBeenCalled();

    await user.selectOptions(screen.getByLabelText(/Ceza türü/), "SHORT_TERM_SUSPENSION");
    expect(screen.queryByText(/md. 166: öğrencinin bu öğretim yılında/)).not.toBeInTheDocument();

    await user.selectOptions(screen.getByLabelText(/Ceza türü/), "REPRIMAND");
    await user.type(screen.getByLabelText("md. 166 gerekçesi"), "Fiil farklı.");
    await user.click(screen.getByRole("button", { name: "Kararı kaydet" }));
    await waitFor(() => expect(dapi.createDecision).toHaveBeenCalled());
    expect(dapi.createDecision.mock.calls[0][1]).toMatchObject({
      penalty_type: "REPRIMAND",
      md166_override_reason: "Fiil farklı.",
    });
  });

  it("kararda kayıtlı md. 166 gerekçesi kartta görünür", async () => {
    dapi.listDecisions.mockResolvedValue({
      decisions: [makeDecision({ md166_override_reason: "Kurul takdiri." })],
      behavior_points: {},
    });
    renderSection();
    expect(await screen.findByText("Kurul takdiri.")).toBeInTheDocument();
  });
});

describe("DecisionsSection — 27.09.2026 denetim bulguları", () => {
  const onayli = {
    approval_status: "APPROVED" as const,
    approval_status_display: "Onaylandı",
    approved_at: "2026-03-03",
    notified_at: "2026-03-04",
    appeal_deadline: "2026-03-11",
  };

  it("itirazsız tebliğli kararda tebliğ tarihi düzeltilebilir (tek yönlü kapan yok)", async () => {
    dapi.listDecisions.mockResolvedValue({
      decisions: [makeDecision({ ...onayli, notification_method: "Elden" })],
      behavior_points: {},
    });
    dapi.notifyDecision.mockResolvedValue({});
    const user = userEvent.setup();
    renderSection();
    await user.click(await screen.findByRole("button", { name: "Tebliği düzelt" }));
    // Form mevcut tebliğ tarihiyle açılır, yeni tarih gövdeye gider.
    const tarih = screen.getByLabelText(/Tebliğ tarihi/);
    expect(tarih).toHaveValue("2026-03-04");
    fireEvent.change(tarih, { target: { value: "2026-03-05" } });
    await user.click(screen.getAllByRole("button", { name: /Tebliğ kaydet|Kaydet/ }).at(-1)!);
    await waitFor(() =>
      expect(dapi.notifyDecision).toHaveBeenCalledWith(
        1,
        5,
        expect.objectContaining({ notified_on: "2026-03-05", notification_method: "Elden" }),
      ),
    );
  });

  it("itirazlı kararda tebliğ düzeltme düğmesi yoktur (backend reddeder)", async () => {
    dapi.listDecisions.mockResolvedValue({
      decisions: [makeDecision({ ...onayli, appeals: [itiraz()] })],
      behavior_points: {},
    });
    renderSection();
    await screen.findByText(/Tebliğ: /);
    expect(screen.queryByRole("button", { name: /Tebliğ/ })).toBeNull();
  });

  it("kesin itiraz sonucu onay sorulmadan kaydedilmez (md. 169/4)", async () => {
    dapi.listDecisions.mockResolvedValue({
      decisions: [makeDecision({ ...onayli, appeals: [itiraz()] })],
      behavior_points: {},
    });
    dapi.resolveAppeal.mockResolvedValue({});
    const user = userEvent.setup();
    renderSection();
    await user.click(await screen.findByRole("button", { name: /Sonucu kaydet/ }));
    await user.click(screen.getAllByRole("button", { name: /Sonucu kaydet/ }).at(-1)!);
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText(/kesindir/)).toBeInTheDocument();
    expect(dapi.resolveAppeal).not.toHaveBeenCalled();
    await user.click(within(dialog).getByRole("button", { name: "Sonucu kaydet" }));
    await waitFor(() => expect(dapi.resolveAppeal).toHaveBeenCalledTimes(1));
  });

  it("okul değiştirmede süresinde itiraz varken 'uygulama bekletiliyor' uyarısı çıkar (md. 172/2-ç)", async () => {
    dapi.listDecisions.mockResolvedValue({
      decisions: [
        makeDecision({
          ...onayli,
          penalty_type: "SCHOOL_CHANGE",
          appeals: [itiraz()],
        } as Partial<DisciplineDecision>),
      ],
      behavior_points: {},
    });
    renderSection();
    expect(await screen.findByText(/Uygulama bekletiliyor/)).toBeInTheDocument();
  });

  it("süre dışı itirazda bekletme uyarısı çıkmaz", async () => {
    dapi.listDecisions.mockResolvedValue({
      decisions: [
        makeDecision({
          ...onayli,
          penalty_type: "SCHOOL_CHANGE",
          appeals: [{ ...itiraz(), within_deadline: false }],
        } as Partial<DisciplineDecision>),
      ],
      behavior_points: {},
    });
    renderSection();
    await screen.findByText(/Tebliğ: /);
    expect(screen.queryByText(/Uygulama bekletiliyor/)).toBeNull();
  });

  it("kapalı dosyada onay/tebliğ/düzenleme düğmeleri sunulmaz, itiraz sunulur", async () => {
    dapi.listDecisions.mockResolvedValue({
      decisions: [makeDecision({ ...onayli })],
      behavior_points: {},
    });
    renderSection(makeCase({ closed_at: "2026-04-01T10:00:00+03:00" }));
    await screen.findByText(/Tebliğ: /);
    expect(screen.queryByRole("button", { name: /Tebliği düzelt|Onay durumu|Düzenle/ })).toBeNull();
    expect(screen.getByRole("button", { name: /İtiraz/ })).toBeInTheDocument();
  });

  it("ceza kaldırmayı geri alma hatası kullanıcıya gösterilir", async () => {
    dapi.listDecisions.mockResolvedValue({
      decisions: [
        makeDecision({
          ...onayli,
          is_final: true,
          e_school_processed_on: "2026-03-20",
          penalty_removed_on: "2026-05-01",
        } as Partial<DisciplineDecision>),
      ],
      behavior_points: {},
    });
    dapi.undoPenaltyRemoval.mockRejectedValue(
      new ApiError(400, "validation", "Bu cezada kaldırma kaydı yok."),
    );
    const user = userEvent.setup();
    renderSection();
    await user.click(await screen.findByRole("button", { name: "geri al" }));
    expect(await screen.findByText(/kaldırma kaydı yok/)).toBeInTheDocument();
  });
});

describe("DecisionsSection — 14.11.2026 saha testi bulguları", () => {
  const uzaklastirma = {
    penalty_type: "SHORT_TERM_SUSPENSION" as const,
    penalty_type_display: "Okuldan kısa süreli uzaklaştırma",
    suspension_days: 5,
    behavior_point_deduction: 20,
  };
  const tebligli = {
    approval_status: "APPROVED" as const,
    approval_status_display: "Onaylandı",
    approved_at: "2026-03-03",
    notified_at: "2026-03-04",
    appeal_deadline: "2026-03-11",
  };

  async function sonucFormunuAc(user: ReturnType<typeof userEvent.setup>) {
    await user.click(await screen.findByRole("button", { name: /Sonucu kaydet/ }));
    await user.selectOptions(screen.getByLabelText("Sonuç"), "REDUCED");
  }

  it("itiraz kurulunun gün indirimi aynı ceza türüyle kaydedilir (bulgu 2)", async () => {
    dapi.listDecisions.mockResolvedValue({
      decisions: [makeDecision({ ...uzaklastirma, ...tebligli, appeals: [itiraz()] })],
      behavior_points: {},
    });
    dapi.resolveAppeal.mockResolvedValue({});
    const user = userEvent.setup();
    renderSection();
    await sonucFormunuAc(user);

    await user.selectOptions(
      screen.getByLabelText(/Kurulun verdiği yeni ceza/),
      "SHORT_TERM_SUSPENSION",
    );
    // Mevcut gün sayısı ipucu olarak görünür.
    expect(screen.getByText(/Mevcut ceza 5 gün/)).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText(/Uzaklaştırma süresi/), { target: { value: "2" } });
    await user.click(screen.getAllByRole("button", { name: /Sonucu kaydet/ }).at(-1)!);
    const dialog = await screen.findByRole("dialog");
    await user.click(within(dialog).getByRole("button", { name: "Sonucu kaydet" }));

    await waitFor(() =>
      expect(dapi.resolveAppeal).toHaveBeenCalledWith(
        1,
        9,
        expect.objectContaining({
          result: "REDUCED",
          new_penalty_type: "SHORT_TERM_SUSPENSION",
          new_suspension_days: 2,
        }),
      ),
    );
  });

  it("aynı tür + aynı gün 'değiştirildi' sayılmaz; kesin sonuç onayı sorulmaz (bulgu 2)", async () => {
    dapi.listDecisions.mockResolvedValue({
      decisions: [makeDecision({ ...uzaklastirma, ...tebligli, appeals: [itiraz()] })],
      behavior_points: {},
    });
    const user = userEvent.setup();
    renderSection();
    await sonucFormunuAc(user);

    await user.selectOptions(
      screen.getByLabelText(/Kurulun verdiği yeni ceza/),
      "SHORT_TERM_SUSPENSION",
    );
    fireEvent.change(screen.getByLabelText(/Uzaklaştırma süresi/), { target: { value: "5" } });
    await user.click(screen.getAllByRole("button", { name: /Sonucu kaydet/ }).at(-1)!);

    expect(await screen.findByText(/Gün sayısı mevcut cezayla aynı/)).toBeInTheDocument();
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(dapi.resolveAppeal).not.toHaveBeenCalled();
  });

  it("kınamada yeni ceza listesinde kınama yoktur (aynı tür yalnız uzaklaştırmada)", async () => {
    dapi.listDecisions.mockResolvedValue({
      decisions: [makeDecision({ ...tebligli, appeals: [itiraz()] })],
      behavior_points: {},
    });
    const user = userEvent.setup();
    renderSection();
    await sonucFormunuAc(user);
    const yeniCeza = screen.getByLabelText(/Kurulun verdiği yeni ceza/);
    expect(within(yeniCeza).queryByRole("option", { name: /Kınama/ })).toBeNull();
    expect(within(yeniCeza).getByRole("option", { name: /uzaklaştırma/ })).toBeInTheDocument();
  });

  it("değiştirilmiş itirazda itiraz edilen ceza gün sayısıyla görünür (bulgu 2)", async () => {
    dapi.listDecisions.mockResolvedValue({
      decisions: [
        makeDecision({
          ...uzaklastirma,
          ...tebligli,
          suspension_days: 2,
          appeals: [
            {
              ...itiraz(),
              result: "REDUCED",
              result_display: "Hafifletildi/değiştirildi",
              resulted_on: "2026-03-20",
              previous_penalty_type: "SHORT_TERM_SUSPENSION",
              previous_suspension_days: 5,
            },
          ],
        }),
      ],
      behavior_points: {},
    });
    renderSection();
    expect(
      await screen.findByText(/İtiraz edilen ceza: Okuldan kısa süreli uzaklaştırma \(5 gün\)/),
    ).toBeInTheDocument();
  });

  it("üst kurulca değişmiş kararda kurulun verdiği ceza gün sayısıyla görünür (S11b)", async () => {
    dapi.listDecisions.mockResolvedValue({
      decisions: [
        makeDecision({
          approval_status: "APPROVED",
          approved_at: "2026-03-20",
          referred_to_district: true,
          board_penalty_type: "SHORT_TERM_SUSPENSION",
          board_suspension_days: 5,
        }),
      ],
      behavior_points: {},
    });
    renderSection();
    expect(
      await screen.findByText(/Kurulun verdiği ceza: Okuldan kısa süreli uzaklaştırma \(5 gün\)/),
    ).toBeInTheDocument();
  });

  it("cezası değişmemiş kararda kurulun verdiği ceza satırı görünmez (S11b)", async () => {
    dapi.listDecisions.mockResolvedValue({
      decisions: [makeDecision({ board_penalty_type: "", board_suspension_days: null })],
      behavior_points: {},
    });
    renderSection();
    await screen.findByText("Zeynep Yılmaz");
    expect(screen.queryByText(/Kurulun verdiği ceza/)).toBeNull();
  });

  it("ceza kurulun verdiğine geri döndüyse kurulun verdiği ceza satırı görünmez (S11b)", async () => {
    // Özgün ceza kayıtta kalıcıdır (onayda değişiklik → itirazla özgün cezaya dönüş);
    // yürürlükteki cezayla aynıysa gösterilecek fark yoktur.
    dapi.listDecisions.mockResolvedValue({
      decisions: [
        makeDecision({
          approval_status: "APPROVED",
          approved_at: "2026-03-20",
          referred_to_district: true,
          penalty_type: "SHORT_TERM_SUSPENSION",
          penalty_type_display: "Okuldan kısa süreli uzaklaştırma",
          suspension_days: 3,
          board_penalty_type: "SHORT_TERM_SUSPENSION",
          board_suspension_days: 3,
        }),
      ],
      behavior_points: {},
    });
    renderSection();
    await screen.findByText("Zeynep Yılmaz");
    expect(screen.queryByText(/Kurulun verdiği ceza/)).toBeNull();
  });

  it("yalnız gün sayısı farklıysa kurulun verdiği ceza satırı görünür (S11b)", async () => {
    dapi.listDecisions.mockResolvedValue({
      decisions: [
        makeDecision({
          approval_status: "APPROVED",
          approved_at: "2026-03-20",
          referred_to_district: true,
          penalty_type: "SHORT_TERM_SUSPENSION",
          penalty_type_display: "Okuldan kısa süreli uzaklaştırma",
          suspension_days: 5,
          board_penalty_type: "SHORT_TERM_SUSPENSION",
          board_suspension_days: 3,
        }),
      ],
      behavior_points: {},
    });
    renderSection();
    expect(
      await screen.findByText(/Kurulun verdiği ceza: Okuldan kısa süreli uzaklaştırma \(3 gün\)/),
    ).toBeInTheDocument();
  });

  it("ilçeye sevk edilmiş kararda kurula iade tarihi de görünür (S11b)", async () => {
    dapi.listDecisions.mockResolvedValue({
      decisions: [
        makeDecision({
          approval_status: "REFERRED",
          referred_to_district: true,
          return_reason: "Ağır.\n\nİlçeye sevk: Israr.",
          returned_at: "2026-03-16",
          first_returned_at: "2026-03-11",
        }),
      ],
      behavior_points: {},
    });
    renderSection();
    expect(
      await screen.findByText(/İlçeye sevk gerekçesi · 16\.03\.2026 · kurula iade: 11\.03\.2026/),
    ).toBeInTheDocument();
  });

  it("iade sonrası beklemeye alınmış karar ilçeye gönderilebilir, yeniden iade edilemez (bulgu 28)", async () => {
    dapi.listDecisions.mockResolvedValue({
      decisions: [makeDecision({ returned_at: "2026-03-05", return_reason: "Ağır." })],
      behavior_points: {},
    });
    renderSection();
    expect(await screen.findByRole("button", { name: "İlçe kuruluna gönder" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Kurula iade" })).not.toBeInTheDocument();
  });

  it("hiç iade edilmemiş kararda ilçeye gönderme düğmesi yoktur (md. 197)", async () => {
    dapi.listDecisions.mockResolvedValue({ decisions: [makeDecision()], behavior_points: {} });
    renderSection();
    expect(await screen.findByRole("button", { name: "Kurula iade" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "İlçe kuruluna gönder" })).not.toBeInTheDocument();
  });

  it("yanlış girilen ilçe onayı düzeltilebilir: ilçe değişikliği onaylı kararda da sunulur (bulgu 28)", async () => {
    dapi.listDecisions.mockResolvedValue({
      decisions: [
        makeDecision({
          ...uzaklastirma,
          approval_status: "APPROVED",
          approval_status_display: "Onaylandı",
          approved_at: "2026-03-10",
          returned_at: "2026-03-06",
          referred_to_district: true,
        }),
      ],
      behavior_points: {},
    });
    dapi.approveDecision.mockResolvedValue({});
    const user = userEvent.setup();
    renderSection();

    await user.click(await screen.findByRole("button", { name: "İlçe kurulu kararı" }));
    // "Beklemede" seçeneği müdür onayına değil ilçe kuruluna dönüşü anlatır.
    expect(
      within(screen.getByLabelText("Onay durumu")).getByRole("option", {
        name: "İlçe kurulunda (karar bekleniyor)",
      }),
    ).toBeInTheDocument();
    await user.selectOptions(
      screen.getByLabelText("Kurul cezayı değiştirdi mi?"),
      "SHORT_TERM_SUSPENSION",
    );
    fireEvent.change(screen.getByLabelText(/Uzaklaştırma süresi/), { target: { value: "1" } });
    await user.click(screen.getByRole("button", { name: "Kaydet" }));
    await waitFor(() =>
      expect(dapi.approveDecision).toHaveBeenCalledWith(1, 5, {
        approval_status: "APPROVED",
        approved_on: "2026-03-10",
        modified_penalty_type: "SHORT_TERM_SUSPENSION",
        modified_suspension_days: 1,
      }),
    );
  });

  it("ilçe kurulundaki kararda form boş açılır; dokunmadan kaydedilmez (bulgu 28)", async () => {
    dapi.listDecisions.mockResolvedValue({
      decisions: [
        makeDecision({
          approval_status: "REFERRED",
          approval_status_display: "İlçe kuruluna gönderildi (md. 197)",
          returned_at: "2026-03-06",
          return_reason: "Ağır.\n\nİlçeye sevk: Israr.",
          referred_to_district: true,
        }),
      ],
      behavior_points: {},
    });
    const user = userEvent.setup();
    renderSection();
    await user.click(await screen.findByRole("button", { name: "İlçe kurulu kararı" }));
    expect(screen.getByLabelText("Onay durumu")).toHaveValue("");
    await user.click(screen.getByRole("button", { name: "Kaydet" }));
    expect(await screen.findByText("Onay durumunu seçin.")).toBeInTheDocument();
    expect(dapi.approveDecision).not.toHaveBeenCalled();
  });

  it("sevki geri alınmış dosyada karar eklenemez (bulgu 29)", async () => {
    dapi.listDecisions.mockResolvedValue({ decisions: [], behavior_points: {} });
    // Sevk olayı duruyor ama aşama geri alınmış (revert_stage olay silmez).
    renderSection(makeCase({ current_stage: "PETITION" }));
    expect(
      await screen.findByText(/yalnız okul öğrenci ödül ve disiplin kuruluna sevk/),
    ).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Karar ekle" })).not.toBeInTheDocument();
  });
});

// Kullanıcı kararı, 14.11.2026 — S9: cezasız kararda itiraz yolu yok (md. 169/3);
// tebliğden sonra itiraz süresi ve tampon beklenmeden dosya kapatılabilir.
describe("DecisionsSection — S9: cezasız kararda süre beklenmez", () => {
  const CEZASIZ: Partial<DisciplineDecision> = {
    penalty_type: "NO_PENALTY",
    penalty_type_display: "Ceza verilmesine yer olmadığı",
    behavior_point_deduction: 0,
    approval_status: "APPROVED",
    approval_status_display: "Onaylandı",
    approved_at: "2026-03-02",
  };

  it("tebliğ edilmiş cezasız kararda itiraz son günü yerine 'süre beklenmez' yazar", async () => {
    dapi.listDecisions.mockResolvedValue({
      decisions: [
        makeDecision({ ...CEZASIZ, notified_at: "2026-03-03", appeal_deadline: "2026-03-10" }),
      ],
      behavior_points: {},
    });
    renderSection();

    expect(await screen.findByText(/Tebliğ: 03\.03\.2026/)).toBeInTheDocument();
    expect(screen.queryByText(/İtiraz son gün/)).toBeNull();
    expect(
      screen.getByText(/itiraz yolu yok \(md\. 169\/3\); bu karar için süre beklenmez/),
    ).toBeInTheDocument();
  });

  it("tebliğ panelinde cezasız karar için itiraz süresi değil kapanış kuralı anlatılır", async () => {
    dapi.listDecisions.mockResolvedValue({
      decisions: [makeDecision(CEZASIZ)],
      behavior_points: {},
    });
    const user = userEvent.setup();
    renderSection();

    await user.click(await screen.findByRole("button", { name: "Tebliğ kaydet" }));
    expect(
      screen.getByText(/itiraz süresi ve kapanış tamponu beklenmeden kapatılabilir/),
    ).toBeInTheDocument();
    expect(screen.queryByText(/itiraz son günü otomatik hesaplanır/)).toBeNull();
  });

  it("cezalı kararda itiraz son günü eskisi gibi görünür", async () => {
    dapi.listDecisions.mockResolvedValue({
      decisions: [
        makeDecision({
          approval_status: "APPROVED",
          approval_status_display: "Onaylandı",
          approved_at: "2026-03-02",
          notified_at: "2026-03-03",
          appeal_deadline: "2026-03-10",
        }),
      ],
      behavior_points: {},
    });
    renderSection();
    expect(await screen.findByText(/İtiraz son gün: 10\.03\.2026/)).toBeInTheDocument();
    expect(screen.queryByText(/süre beklenmeden kapatılabilir/)).toBeNull();
  });
});

function itiraz() {
  return {
    id: 9,
    decision: 5,
    filed_on: "2026-03-05",
    filed_by_role: "PARENT",
    filed_by_name: "",
    within_deadline: true,
    appeal_authority: "DISTRICT_BOARD",
    appeal_authority_display: "İlçe",
    forward_deadline: null,
    forwarded_on: "2026-03-06",
    result: "PENDING",
    result_display: "İnceleniyor",
    resulted_on: null,
    result_notes: "",
    previous_penalty_type: "",
    previous_suspension_days: null,
  } as unknown as DisciplineDecision["appeals"][number];
}
