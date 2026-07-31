// Belge üretim formu testi (F4 denetimi, bulgu B4): KİŞİ değişiminde o kişiye özgü
// serbest metin alanları sıfırlanmalıdır. Aksi hâlde A katılımcısının ifadesi /
// A öğrencisinin davranış özeti B'nin resmî tutanağına basılır (md. 194 + KVKK).
// Form içeriği no-trace (kaydedilmez), bu yüzden tek koruma formun kendisidir.

import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ConfirmProvider } from "../../ui/ConfirmProvider";
import { SnackbarProvider } from "../../ui/SnackbarProvider";
import type {
  DisciplineCase,
  DisciplineDecision,
  DisciplineParticipant,
  GeneratedDocument,
} from "./api";

const dapi = vi.hoisted(() => ({
  listDocuments: vi.fn(),
  listDeletedDocuments: vi.fn(),
  listParticipants: vi.fn(),
  listWarnings: vi.fn(),
  listDecisions: vi.fn(),
  generateDocument: vi.fn(),
  downloadStoredDocument: vi.fn(),
}));

// Yalnız API çağrıları taklit edilir; belge türü kataloğu (GENERATABLE_DOCUMENT_TYPES)
// gerçek kalır — workflow.ts onu içe aktarır ve test asıl davranışı ölçer.
vi.mock("./api", async () => {
  const actual = await vi.importActual<typeof import("./api")>("./api");
  return { ...actual, disiplinApi: dapi };
});

import DocumentsSection from "./DocumentsSection";

const CASE: DisciplineCase = {
  id: 7,
  case_no: "2026-1",
  petition_date: "2026-05-12",
  petitioner_name: "Zeynep Ak",
  petitioner_role: "OGRETMEN",
  summary: "Olay özeti",
  current_stage: "DECIDED",
  current_stage_display: "Müdür değerlendirmesi",
  closed_at: null,
  students: [
    { id: 11, full_name: "Ayşe Yılmaz", student_number: "101", class_label: "9/A" },
    { id: 22, full_name: "Mehmet Kaya", student_number: "102", class_label: "9/B" },
  ],
  events: [], // dal belirsiz → tüm üretilebilir türler listelenir
};

function participant(id: number, name: string): DisciplineParticipant {
  return {
    id,
    role: "ACCUSED",
    role_display: "Hakkında İşlem Yapılan",
    person_type: "STUDENT",
    person_type_display: "Öğrenci",
    student: id,
    user: null,
    external_name: "",
    external_title: "",
    name_snapshot: name,
    notes: "",
  };
}

function renderSection() {
  return render(
    <SnackbarProvider>
      <ConfirmProvider>
        <DocumentsSection caseObj={CASE} canManage />
      </ConfirmProvider>
    </SnackbarProvider>,
  );
}

// "Belge üret" panelini açar ve verilen belge türünü seçer.
async function openGenerateForm(user: ReturnType<typeof userEvent.setup>, docType: string) {
  await user.click(await screen.findByRole("button", { name: /Belge üret/ }));
  await user.selectOptions(screen.getByLabelText(/Belge türü/), docType);
}

beforeEach(() => {
  vi.clearAllMocks();
  dapi.listDocuments.mockResolvedValue([]);
  dapi.listDeletedDocuments.mockResolvedValue([]);
  dapi.listParticipants.mockResolvedValue([
    participant(1, "Ayşe Yılmaz"),
    participant(2, "Mehmet Kaya"),
  ]);
  dapi.listWarnings.mockResolvedValue([]);
  dapi.listDecisions.mockResolvedValue({ decisions: [], behavior_points: {} });
  dapi.downloadStoredDocument.mockResolvedValue(new Blob(["%PDF-test"]));
});

describe("DocumentsSection — belge üretiminde kişi değişimi", () => {
  it("katılımcı değişince ifade konusu ve gövdesi sıfırlanır", async () => {
    const user = userEvent.setup();
    renderSection();
    await openGenerateForm(user, "STATEMENT_RECORD");

    const participantSelect = await screen.findByLabelText(/İlgili katılımcı/);
    await user.selectOptions(participantSelect, "1");

    const subject = screen.getByLabelText(/Disiplin konusu \/ sorular/);
    const body = screen.getByLabelText(/İfade metni/);
    await user.type(subject, "Kantin olayı");
    await user.type(body, "Ben olay sırasında sınıftaydım.");
    expect(body).toHaveValue("Ben olay sırasında sınıftaydım.");

    await user.selectOptions(participantSelect, "2");

    expect(subject).toHaveValue("");
    expect(body).toHaveValue("");
    expect(await screen.findByText(/Katılımcı değişti/)).toBeInTheDocument();
  });

  it("öğrenci değişince davranış özeti sıfırlanır", async () => {
    const user = userEvent.setup();
    renderSection();
    await openGenerateForm(user, "WARNING_LETTER");

    const studentSelect = screen.getByLabelText(/^Öğrenci/);
    await user.selectOptions(studentSelect, "11");
    await waitFor(() => expect(dapi.listWarnings).toHaveBeenCalled());

    const summary = screen.getByLabelText(/Davranışın kısa açıklaması/);
    await user.type(summary, "Derse sürekli geç kaldı.");

    await user.selectOptions(studentSelect, "22");

    expect(summary).toHaveValue("");
    expect(await screen.findByText(/Öğrenci değişti/)).toBeInTheDocument();
  });

  it("öğrenci değişince üst kurul tebliği alanları sıfırlanır", async () => {
    const user = userEvent.setup();
    renderSection();
    await openGenerateForm(user, "BOARD_DECISION_NOTICE");

    const studentSelect = screen.getByLabelText(/^Öğrenci/);
    await user.selectOptions(studentSelect, "11");
    await waitFor(() => expect(dapi.listDecisions).toHaveBeenCalled());

    const decisionNo = screen.getByLabelText(/Merci karar no/);
    const summary = screen.getByLabelText(/Kurul kararının özeti/);
    await user.type(decisionNo, "2026/12");
    await user.type(summary, "Ceza değiştirilerek onaylandı.");

    await user.selectOptions(studentSelect, "22");

    expect(decisionNo).toHaveValue("");
    expect(summary).toHaveValue("");
  });

  it("alanlar boşken kişi değişimi uyarı göstermez", async () => {
    const user = userEvent.setup();
    renderSection();
    await openGenerateForm(user, "STATEMENT_RECORD");

    const participantSelect = await screen.findByLabelText(/İlgili katılımcı/);
    await user.selectOptions(participantSelect, "1");
    await user.selectOptions(participantSelect, "2");

    expect(screen.queryByText(/Katılımcı değişti/)).not.toBeInTheDocument();
  });
});

describe("DocumentsSection — EK-1 eksik bilgi uyarısı", () => {
  it("seçili öğrencinin EK-1 anlatısı eksikse giriş yolunu gösterir", async () => {
    const user = userEvent.setup();
    dapi.listDecisions.mockResolvedValue({
      decisions: [
        {
          student: 11,
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
          incident_date: null,
          prior_penalties_summary: "Daha önce ceza almamıştır.",
          student_birth_date: null,
        } as DisciplineDecision,
      ],
      behavior_points: {},
    });
    renderSection();
    await openGenerateForm(user, "COMMITTEE_DECISION");

    await user.selectOptions(screen.getByLabelText(/^Öğrenci/), "11");

    expect(await screen.findByText(/EK-1 bilgileri eksik/)).toBeInTheDocument();
    expect(screen.getByText(/Kurul & Karar → Resmî kararlar → EK-1 anlatı/)).toBeInTheDocument();
  });
});

describe("DocumentsSection — saklanan PDF kopyaları", () => {
  it("yeniden indirme eylemini ve en altta Silinen evraklar bölümünü gösterir", async () => {
    const archived: GeneratedDocument = {
      id: 41,
      student: 11,
      document_type: "COMMITTEE_DECISION",
      document_type_display: "Kurul kararı (EK-1)",
      title: "EK-1 Kurul Kararı",
      document_no: "2025-2026/0001",
      source_label: "",
      source_name: "",
      generated_on: "2026-05-22",
      notes: "",
      page_count: 2,
      has_stored_pdf: true,
      stored_pdf_size: 2048,
      stored_filename: "2026-1-COMMITTEE_DECISION.pdf",
      parent_document: null,
      sort_order: 10,
      created_at: "2026-05-22T10:00:00Z",
      sub_documents: [],
    };
    dapi.listDocuments.mockResolvedValue([archived]);
    dapi.listDeletedDocuments.mockResolvedValue([{ ...archived, id: 42 }]);
    const user = userEvent.setup();

    renderSection();

    expect(await screen.findByText("PDF saklandı")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Tekrar indir" })).toBeInTheDocument();
    const deletedButton = screen.getByRole("button", { name: /Silinen evraklar/ });
    await user.click(deletedButton);
    expect(await screen.findByText(/Silinen evraklar \(1\)/)).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: "Tekrar indir" })).toHaveLength(2);
  });
});
