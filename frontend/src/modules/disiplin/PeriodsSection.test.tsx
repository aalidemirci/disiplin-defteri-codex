// Kurul süre uzatması + tedbir kartları (saha testi 14.11.2026):
// - yanlış girilen / müdürün onaylamadığı süre uzatması silinebilir (§7.6 tek yönlü kapan);
//   onaylanmış uzatmada "Sil" yoktur (kurul süresini fiilen uzatmıştır),
// - kapalı dosyada tedbir/uzatma ekleme, onay ve tedbir uzatma düğmeleri gizlenir;
//   yürürlükte kalmış tedbirin "Sonlandır"ı açık kalır.

import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ConfirmProvider } from "../../ui/ConfirmProvider";
import { SnackbarProvider } from "../../ui/SnackbarProvider";
import type { DisciplineCase, DisciplineDeadlineExtension, DisciplinePrecaution } from "./api";
import { ALL_CAPABILITIES } from "./workflow";

const dapi = vi.hoisted(() => ({
  listExtensions: vi.fn(),
  createExtension: vi.fn(),
  approveExtension: vi.fn(),
  deleteExtension: vi.fn(),
  listPrecautions: vi.fn(),
  createPrecaution: vi.fn(),
  liftPrecaution: vi.fn(),
  extendPrecaution: vi.fn(),
}));

vi.mock("./api", async () => {
  const actual = await vi.importActual<typeof import("./api")>("./api");
  return { ...actual, disiplinApi: dapi };
});

import PeriodsSection from "./PeriodsSection";

const CASE: DisciplineCase = {
  id: 7,
  case_no: "2026-2027-0001",
  petition_date: "2026-11-02",
  petitioner_name: "Zeynep Ak",
  petitioner_role: "OGRETMEN",
  summary: "Olay özeti",
  current_stage: "DECIDED",
  current_stage_display: "Müdür değerlendirmesi",
  closed_at: null,
  students: [{ id: 11, full_name: "Çağrı Işıkgöz", student_number: "101", class_label: "9/A" }],
};

function extension(over: Partial<DisciplineDeadlineExtension> = {}): DisciplineDeadlineExtension {
  return {
    id: 3,
    requested_days: 5,
    reason: "İfade gecikmesi",
    decided_on: "2026-11-05",
    approved_by_principal: false,
    approved_on: null,
    original_deadline: "2026-11-17",
    new_deadline: "2026-11-24",
    notes: "",
    ...over,
  } as DisciplineDeadlineExtension;
}

function precaution(over: Partial<DisciplinePrecaution> = {}): DisciplinePrecaution {
  return {
    id: 5,
    student: 11,
    start_date: "2026-11-03",
    requested_days: 3,
    end_date: "2026-11-05",
    process_start_deadline: "2026-11-06",
    mne_notified: true,
    extension_count: 0,
    status: "ACTIVE",
    status_display: "Yürürlükte",
    lifted_on: null,
    reason: "",
    notes: "",
    ...over,
  } as DisciplinePrecaution;
}

function setup(
  extensions: DisciplineDeadlineExtension[],
  precautions: DisciplinePrecaution[] = [],
) {
  dapi.listExtensions.mockResolvedValue({
    extensions,
    committee_referred_on: "2026-11-03",
    committee_decision_deadline: "2026-11-17",
  });
  dapi.listPrecautions.mockResolvedValue(precautions);
}

function renderSection(caseObj: DisciplineCase = CASE) {
  return render(
    <SnackbarProvider>
      <ConfirmProvider>
        <PeriodsSection caseObj={caseObj} caps={ALL_CAPABILITIES} />
      </ConfirmProvider>
    </SnackbarProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe("PeriodsSection — süre uzatmasını silme", () => {
  it("onaysız uzatma onay alınarak silinir ve liste tazelenir", async () => {
    setup([extension()]);
    dapi.deleteExtension.mockResolvedValue(undefined);
    const user = userEvent.setup();
    renderSection();

    await user.click(await screen.findByRole("button", { name: "Sil" }));
    const dialog = await screen.findByRole("dialog", { name: "Onay" });
    expect(dialog).toHaveTextContent("süre uzatması kaydı silinsin mi");
    setup([]); // silme sonrası yeniden yükleme boş liste döner
    await user.click(within(dialog).getByRole("button", { name: "Sil" }));

    await waitFor(() => expect(dapi.deleteExtension).toHaveBeenCalledWith(7, 3));
    expect(await screen.findByText("Süre uzatması kaydedilmedi.")).toBeInTheDocument();
    // Kayıt silindi → "ancak bir kez" kuralı yeniden yeni kayda izin verir.
    expect(screen.getByRole("button", { name: "Süre uzatması ekle" })).toBeInTheDocument();
  });

  it("onaylanmış uzatmada Sil düğmesi yoktur", async () => {
    setup([extension({ approved_by_principal: true, approved_on: "2026-11-06" })]);
    renderSection();

    expect(await screen.findByText("Müdür onaylı")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Sil" })).not.toBeInTheDocument();
  });

  it("sunucu reddederse Türkçe ileti gösterilir", async () => {
    setup([extension()]);
    dapi.deleteExtension.mockRejectedValue(
      new Error("Müdürün onayladığı süre uzatması silinemez."),
    );
    const user = userEvent.setup();
    renderSection();

    await user.click(await screen.findByRole("button", { name: "Sil" }));
    const dialog = await screen.findByRole("dialog", { name: "Onay" });
    await user.click(within(dialog).getByRole("button", { name: "Sil" }));

    expect(
      await screen.findByText("Müdürün onayladığı süre uzatması silinemez."),
    ).toBeInTheDocument();
  });
});

describe("PeriodsSection — kapalı dosya", () => {
  const CLOSED: DisciplineCase = {
    ...CASE,
    current_stage: "CLOSED",
    current_stage_display: "Kapandı",
    closed_at: "2026-11-12T10:00:00+03:00",
  };

  it("ekleme, onay ve tedbir uzatma düğmeleri gizlenir; Sonlandır ve Sil kalır", async () => {
    setup([extension()], [precaution()]);
    renderSection(CLOSED);

    expect(await screen.findByText("Onay bekliyor")).toBeInTheDocument();
    expect(await screen.findByText("Çağrı Işıkgöz")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Tedbir ekle" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Süre uzatması ekle" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Müdür onayı (Form-13)" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Uzat" })).not.toBeInTheDocument();
    // Yürürlükte kalmış tedbir kapalı dosyada da sonlandırılabilmeli; onaysız uzatma silinebilmeli.
    expect(screen.getByRole("button", { name: "Sonlandır" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Sil" })).toBeInTheDocument();
  });

  it("açık dosyada düğmeler görünür", async () => {
    setup([], [precaution()]);
    renderSection();

    expect(await screen.findByRole("button", { name: "Tedbir ekle" })).toBeInTheDocument();
    expect(await screen.findByRole("button", { name: "Süre uzatması ekle" })).toBeInTheDocument();
    expect(await screen.findByRole("button", { name: "Uzat" })).toBeInTheDocument();
  });
});
