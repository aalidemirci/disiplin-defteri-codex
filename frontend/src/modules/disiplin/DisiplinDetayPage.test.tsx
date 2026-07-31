// Disiplin dosyası detay sayfası testleri (F4 denetimi — bulgu #11/#16/#22).
//
// Kapsam: katılımcı ekleme/çıkarma sonrası dosya detayının tazelenmesi (öğrenci
// listesi bayat kalmasın), gerekçe alanlarının SAKLANMADIĞINI doğru anlatan UI
// metni ve künye düzenleme yolu (kapalı dosyada kapalı).
//
// `./api` modülü kısmen taklit edilir: yalnız `disiplinApi` + lookup'lar; etiket
// sabitleri (STAGE_TR, PARTICIPANT_ROLE_TR…) gerçek kalır ki metin iddiaları
// gerçek sözlükle eşleşsin.

import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ConfirmProvider } from "../../ui/ConfirmProvider";
import { SnackbarProvider } from "../../ui/SnackbarProvider";
import type { DisciplineCase, DisciplineParticipant } from "./api";

const dapi = vi.hoisted(() => ({
  getCase: vi.fn(),
  listParticipants: vi.fn(),
  listWarnings: vi.fn(),
  triageSuggestion: vi.fn(),
  addParticipant: vi.fn(),
  removeParticipant: vi.fn(),
  patchCase: vi.fn(),
  listDecisionTypes: vi.fn(),
  listMeetings: vi.fn(),
  getCommittee: vi.fn(),
  addEvent: vi.fn(),
}));

const slookup = vi.hoisted(() => ({ search: vi.fn() }));
const oapi = vi.hoisted(() => ({
  listClassResponsibilities: vi.fn(() => Promise.resolve([] as Array<Record<string, unknown>>)),
  listPersonnel: vi.fn(() =>
    Promise.resolve({ count: 0, next: null, previous: null, results: [] }),
  ),
}));

vi.mock("./api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("./api")>();
  return {
    ...actual,
    disiplinApi: dapi,
    studentLookupApi: slookup,
    personnelLookupApi: { search: vi.fn(() => Promise.resolve([])) },
  };
});

vi.mock("../okul/api", () => ({ okulApi: oapi }));

import DisiplinDetayPage from "./DisiplinDetayPage";

const OGRENCI = {
  id: 50,
  full_name: "Emre Can Yılmaz",
  student_number: "1001",
  class_label: "10/A",
};

const CASE: DisciplineCase = {
  id: 5,
  case_no: "2026/1",
  petition_date: "2026-05-18",
  petitioner_name: "Ali Örnek",
  petitioner_role: "IDARE",
  summary: "Koridorda tartışma.",
  current_stage: "PETITION",
  current_stage_display: "Dilekçe alındı",
  closed_at: null,
  students: [OGRENCI],
  events: [],
  attachments: [],
  close_eligible: false,
  close_eligible_on: null,
};

const ACCUSED: DisciplineParticipant = {
  id: 90,
  role: "ACCUSED",
  role_display: "Hakkında İşlem Yapılan",
  person_type: "STUDENT",
  person_type_display: "Öğrenci",
  student: OGRENCI.id,
  user: null,
  external_name: "",
  external_title: "",
  name_snapshot: "Emre Can Yılmaz",
  notes: "",
};

function renderPage(over: Partial<DisciplineCase> = {}) {
  dapi.getCase.mockResolvedValue({ ...CASE, ...over });
  return render(
    <SnackbarProvider>
      <ConfirmProvider>
        <MemoryRouter initialEntries={["/disiplin/5"]}>
          <Routes>
            <Route path="/disiplin/:id" element={<DisiplinDetayPage />} />
          </Routes>
        </MemoryRouter>
      </ConfirmProvider>
    </SnackbarProvider>,
  );
}

afterEach(() => vi.clearAllMocks());

describe("DisiplinDetayPage — rehberliğe sevk", () => {
  it("sınıf eşleştirmesindeki rehberi önerir ve aşamaya ad snapshot'ı gönderir", async () => {
    dapi.listParticipants.mockResolvedValue([]);
    dapi.listWarnings.mockResolvedValue([]);
    dapi.triageSuggestion.mockResolvedValue({ students: [], should_route_to_committee: false });
    dapi.addEvent.mockResolvedValue({});
    oapi.listClassResponsibilities.mockResolvedValue([
      {
        id: 1,
        school_year: 2,
        school_year_name: "2026-2027",
        class_level: 10,
        class_section: "A",
        class_label: "10/A",
        class_teacher: null,
        class_teacher_detail: null,
        assistant_principal: null,
        assistant_principal_detail: null,
        guidance_teacher: 44,
        guidance_teacher_detail: {
          id: 44,
          first_name: "Örnek",
          last_name: "Rehber",
          full_name: "Örnek Rehber",
          title: "Rehber Öğretmen",
          branch: "Rehberlik",
        },
      },
    ]);
    const user = userEvent.setup();
    renderPage();

    await screen.findByText("İlgili öğrenciler");
    await user.click(screen.getByRole("button", { name: "Rehberliğe sevk" }));

    expect(await screen.findByText("Örnek Rehber")).toBeInTheDocument();
    expect(screen.getByText(/sınıf sorumluluğundan otomatik önerildi/i)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Aşamayı ekle" }));

    await waitFor(() =>
      expect(dapi.addEvent).toHaveBeenCalledWith(
        5,
        expect.objectContaining({
          stage: "GUIDANCE_REFERRED",
          assigned_guidance_name: "Örnek Rehber",
        }),
      ),
    );
  });
});

describe("DisiplinDetayPage — katılımcı ↔ dosya öğrenci listesi senkronu (bulgu #16)", () => {
  it("katılımcı eklenince dosya detayı yeniden çekilir", async () => {
    dapi.listParticipants.mockResolvedValue([]);
    dapi.listWarnings.mockResolvedValue([]);
    dapi.triageSuggestion.mockResolvedValue({ students: [], should_route_to_committee: false });
    dapi.addParticipant.mockResolvedValue({ ...ACCUSED, id: 91 });
    slookup.search.mockResolvedValue([
      { id: 51, full_name: "Zeynep Kaya", student_number: "1002", class_label: "10/A" },
    ]);
    const user = userEvent.setup();
    renderPage();

    await screen.findByText("İlgili öğrenciler");
    await user.click(screen.getByRole("tab", { name: /Taraflar/ }));
    await user.click(await screen.findByRole("button", { name: /Katılımcı ekle/ }));

    await user.selectOptions(screen.getByLabelText("Rol"), "ACCUSED");
    await user.type(screen.getByLabelText(/Öğrenci seç/), "zey");
    const listbox = await screen.findByRole("listbox");
    // Eşleşen alt-dizge <mark> ile sarıldığından erişilebilir ad bölünür; tek
    // sonuç olduğu için ad yerine sıra ile seçilir.
    await user.click(within(listbox).getAllByRole("option")[0]);
    await user.click(screen.getByRole("button", { name: /Katılımcıyı ekle/ }));

    await waitFor(() => expect(dapi.addParticipant).toHaveBeenCalled());
    // Backend ACCUSED katılımcıyı dosyanın öğrenci listesine bağlar; FE bu yüzden
    // yalnız katılımcıları değil DOSYAYI da tazelemek zorunda.
    await waitFor(() => expect(dapi.getCase).toHaveBeenCalledTimes(2));
  });

  it("katılımcı çıkarılınca dosya detayı yeniden çekilir", async () => {
    dapi.listParticipants.mockResolvedValue([ACCUSED]);
    dapi.listWarnings.mockResolvedValue([]);
    dapi.triageSuggestion.mockResolvedValue({ students: [], should_route_to_committee: false });
    dapi.removeParticipant.mockResolvedValue(undefined);
    const user = userEvent.setup();
    renderPage();

    await screen.findByText("İlgili öğrenciler");
    await user.click(screen.getByRole("tab", { name: /Taraflar/ }));
    await user.click(await screen.findByRole("button", { name: /Çıkar/ }));
    const dialog = await screen.findByRole("dialog");
    await user.click(within(dialog).getByRole("button", { name: "Çıkar" }));

    await waitFor(() => expect(dapi.removeParticipant).toHaveBeenCalledWith(5, ACCUSED.id));
    await waitFor(() => expect(dapi.getCase).toHaveBeenCalledTimes(2));
  });
});

describe("DisiplinDetayPage — gerekçe metinleri gerçeğe hizalı (bulgu #11)", () => {
  it("aşama geri alma: 'denetim kaydı' vaadi yok, saklanmadığı söylenir", async () => {
    dapi.listParticipants.mockResolvedValue([]);
    dapi.listWarnings.mockResolvedValue([]);
    dapi.triageSuggestion.mockResolvedValue({ students: [], should_route_to_committee: false });
    const user = userEvent.setup();
    renderPage({ current_stage: "DECIDED" });

    await screen.findByText("İlgili öğrenciler");
    await user.click(screen.getByRole("button", { name: /Aşamayı geri al/ }));

    expect(screen.queryByText(/denetim kaydına/i)).toBeNull();
    expect(screen.getByText(/bu metni saklamaz/i)).toBeInTheDocument();
    expect(screen.getByText(/evrak kütüğüne/i)).toBeInTheDocument();
  });

  it("erken kapatma: AccessLog/STATE_MACHINE_OVERRIDE vaadi yok", async () => {
    dapi.listParticipants.mockResolvedValue([]);
    dapi.listWarnings.mockResolvedValue([]);
    dapi.triageSuggestion.mockResolvedValue({ students: [], should_route_to_committee: false });
    const user = userEvent.setup();
    renderPage({ current_stage: "COMMITTEE_DONE" });

    await screen.findByText("İlgili öğrenciler");
    await user.click(screen.getByRole("button", { name: /Dosyayı kapat/ }));

    expect(await screen.findByLabelText(/Erken kapatma gerekçesi/)).toBeInTheDocument();
    expect(screen.queryByText(/STATE_MACHINE_OVERRIDE/)).toBeNull();
    expect(screen.queryByText(/denetim kaydına/i)).toBeNull();
    expect(screen.getByText(/bu metni saklamaz/i)).toBeInTheDocument();
  });

  it("override gerekçesi: olmayan AccessLog'a atıf yok, aşama kaydında saklandığı yazar", async () => {
    dapi.listParticipants.mockResolvedValue([]);
    dapi.listWarnings.mockResolvedValue([]);
    dapi.triageSuggestion.mockResolvedValue({ students: [], should_route_to_committee: false });
    const user = userEvent.setup();
    renderPage();

    await screen.findByText("İlgili öğrenciler");
    await user.click(screen.getByRole("button", { name: /Override \(aşama atla\)/ }));

    // Override gerekçesi GERÇEKTEN saklanır (DisciplineEvent.override_reason) —
    // yanlış olan, olmayan bir AccessLog'a atıf yapılmasıydı.
    expect(await screen.findByLabelText(/Override gerekçesi/)).toBeInTheDocument();
    expect(screen.queryByText(/AccessLog/)).toBeNull();
    expect(screen.getByText(/zaman çizelgesinde/i)).toBeInTheDocument();
  });
});

describe("DisiplinDetayPage — künye düzenleme (bulgu #22)", () => {
  it("künye düzeltilir: patchCase çağrılır ve dosya tazelenir", async () => {
    dapi.listParticipants.mockResolvedValue([]);
    dapi.listWarnings.mockResolvedValue([]);
    dapi.triageSuggestion.mockResolvedValue({ students: [], should_route_to_committee: false });
    dapi.patchCase.mockResolvedValue({ ...CASE, petitioner_name: "Ayşe Yılmaz" });
    const user = userEvent.setup();
    renderPage();

    await screen.findByText("İlgili öğrenciler");
    await user.click(screen.getByRole("button", { name: /Künye düzenle/ }));

    const dialog = await screen.findByRole("dialog");
    const ad = within(dialog).getByLabelText(/Dilekçeyi veren kişi/);
    await user.clear(ad);
    await user.type(ad, "Ayşe Yılmaz");
    await user.click(within(dialog).getByRole("button", { name: /Kaydet/ }));

    await waitFor(() =>
      expect(dapi.patchCase).toHaveBeenCalledWith(5, {
        petition_date: "2026-05-18",
        petitioner_name: "Ayşe Yılmaz",
        petitioner_role: "IDARE",
        summary: "Koridorda tartışma.",
      }),
    );
    await waitFor(() => expect(dapi.getCase).toHaveBeenCalledTimes(2));
  });

  it("kapalı dosyada künye düzenleme yolu kapalıdır (backend de reddeder)", async () => {
    dapi.listParticipants.mockResolvedValue([]);
    dapi.listWarnings.mockResolvedValue([]);
    dapi.triageSuggestion.mockResolvedValue({ students: [], should_route_to_committee: false });
    renderPage({ current_stage: "CLOSED", closed_at: "2026-06-01T10:00:00Z" });

    await screen.findByText("İlgili öğrenciler");
    expect(screen.queryByRole("button", { name: /Künye düzenle/ })).toBeNull();
  });
});
