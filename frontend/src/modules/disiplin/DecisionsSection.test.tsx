// Resmî kararlar bölümü testi (F4 denetim bulguları 2/3/7/19/B3).
//
// Kapsam: (1) EK-1 anlatı panelinde girilen doğum tarihinin autosave debounce'una
// takılmadan kaydetme gövdesine girmesi, (2) "Kurula iade" edilmiş kararda onay
// durumu listesinin listede GERÇEKTEN bulunan bir değere ilklenmesi, (3) kapalı
// dosyada anlatı panelinin salt-okunur olması, (4) silinen kararı geri alınca hem
// aktif hem çöp kutusu listesinin tazelenmesi, (5) itiraz süresi mevzuat atfı.

import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ConfirmProvider } from "../../ui/ConfirmProvider";
import { SnackbarProvider } from "../../ui/SnackbarProvider";
import type { DisciplineCase, DisciplineDecision } from "./api";

const dapi = vi.hoisted(() => ({
  listDecisions: vi.fn(),
  listDeletedDecisions: vi.fn(),
  deleteDecision: vi.fn(),
  restoreDecision: vi.fn(),
  updateDecisionNarrative: vi.fn(),
  approveDecision: vi.fn(),
  confirmESchoolEntry: vi.fn(),
  createDecision: vi.fn(),
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

afterEach(() => {
  vi.clearAllMocks();
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

describe("DecisionsSection — onay durumu", () => {
  it("kurula iade edilmiş kararda listede bulunan bir değere ilklenir", async () => {
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
    // Seçenekler PENDING/APPROVED ile süzülü; RETURNED listede yok → PENDING görünmeli.
    expect(screen.getByLabelText("Onay durumu")).toHaveValue("PENDING");

    // Kullanıcı dokunmadan kaydedince backend'in reddettiği RETURNED gitmemeli.
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
