// Disiplin dosyası detay sayfası testleri (F4 denetimi — bulgu #11/#16/#22).
//
// Kapsam: katılımcı ekleme/çıkarma sonrası dosya detayının tazelenmesi (öğrenci
// listesi bayat kalmasın), gerekçe alanlarının SAKLANMADIĞINI doğru anlatan UI
// metni ve künye düzenleme yolu (kapalı dosyada kapalı).
//
// `./api` modülü kısmen taklit edilir: yalnız `disiplinApi` + lookup'lar; etiket
// sabitleri (STAGE_TR, PARTICIPANT_ROLE_TR…) gerçek kalır ki metin iddiaları
// gerçek sözlükle eşleşsin.

import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ConfirmProvider } from "../../ui/ConfirmProvider";
import { SnackbarProvider } from "../../ui/SnackbarProvider";
import { ApiError } from "../../lib/api";
import type {
  DisciplineCase,
  DisciplineEvent,
  DisciplineMeeting,
  DisciplineParticipant,
  DisciplineWarning,
} from "./api";

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
  deleteWarning: vi.fn(),
  deleteMeeting: vi.fn(),
}));
// "Kurul & Karar" sekmesindeki komşu bölümler kendi testlerinde sınanır; burada
// yalnız kaç kez (yeniden) bağlandıkları izlenir — toplantı silinince karar bölümü
// verisinin tazelendiğini (§7.5) bununla doğrularız.
const bolum = vi.hoisted(() => ({ decisionsMounted: vi.fn() }));

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

vi.mock("./DecisionsSection", async () => {
  const { useEffect } = await import("react");
  return {
    default: function DecisionsStub() {
      useEffect(() => {
        bolum.decisionsMounted();
      }, []);
      return <div data-testid="kararlar-bolumu" />;
    },
  };
});
vi.mock("./PeriodsSection", () => ({ default: () => <div data-testid="sureler-bolumu" /> }));

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

  it("yazarak arayıp listeden seçilen rehber kayda TAM adıyla geçer", async () => {
    // Windows kullanım bulgusu: "Selin" yazıp seçenek etkinleştirildiğinde seçim
    // tutulmadı, kayda yazılan metin ("Selin") geçti. Erişilebilirlik araçlarının
    // "invoke" eylemi mousedown üretmez; seçim yalnız click ile de tamamlanmalı.
    dapi.listParticipants.mockResolvedValue([]);
    dapi.listWarnings.mockResolvedValue([]);
    dapi.triageSuggestion.mockResolvedValue({ students: [], should_route_to_committee: false });
    dapi.addEvent.mockResolvedValue({});
    oapi.listClassResponsibilities.mockResolvedValue([]);
    const SELIN = {
      id: 7,
      first_name: "Selin",
      last_name: "Rehber",
      full_name: "Selin Rehber",
      title: "Rehber Öğretmen",
      branch: "Rehberlik",
    };
    const KEMAL = {
      id: 8,
      first_name: "Kemal",
      last_name: "Aksoy",
      full_name: "Kemal Aksoy",
      title: "Müdür Yardımcısı",
      branch: "",
    };
    (oapi.listPersonnel as ReturnType<typeof vi.fn>).mockImplementation(
      (params: { search?: string }) => {
        const results = params.search ? [SELIN] : [KEMAL, SELIN];
        return Promise.resolve({ count: results.length, next: null, previous: null, results });
      },
    );
    const user = userEvent.setup();
    renderPage();

    await screen.findByText("İlgili öğrenciler");
    await user.click(screen.getByRole("button", { name: "Rehberliğe sevk" }));
    await user.type(await screen.findByLabelText(/Rehber öğretmen/), "Selin");

    // Liste süzülür: yalnız eşleşen personel kalır.
    await waitFor(() => expect(screen.getAllByRole("option")).toHaveLength(1));
    expect(screen.queryByText("Kemal Aksoy")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("option", { name: /Selin Rehber/ }));
    await user.click(screen.getByRole("button", { name: "Aşamayı ekle" }));

    await waitFor(() =>
      expect(dapi.addEvent).toHaveBeenCalledWith(
        5,
        expect.objectContaining({
          stage: "GUIDANCE_REFERRED",
          assigned_guidance_name: "Selin Rehber",
        }),
      ),
    );
  });
});

describe("DisiplinDetayPage — müdür değerlendirmesi seçenekleri erişilebilir", () => {
  it("üç seçenek adlı bir radyo grubunda, her düğme kendi etiketiyle adlandırılır", async () => {
    dapi.listParticipants.mockResolvedValue([]);
    dapi.listWarnings.mockResolvedValue([]);
    dapi.triageSuggestion.mockResolvedValue({ students: [], should_route_to_committee: false });
    const user = userEvent.setup();
    renderPage();

    await screen.findByText("İlgili öğrenciler");
    await user.click(screen.getByRole("button", { name: /Override \(aşama atla\)/ }));

    const grup = await screen.findByRole("radiogroup", {
      name: /Müdür değerlendirmesi \/ sevk kararı/,
    });
    expect(grup).toHaveAccessibleDescription(/ya yazılı uyarı verir/i);
    const dugmeler = within(grup).getAllByRole("radio");
    expect(dugmeler).toHaveLength(3);
    // Değer "on" (tarayıcı varsayılanı) kalmasın: erişilebilirlik ağacında üç düğme
    // de "on" görünüyordu.
    expect(dugmeler.map((d) => (d as HTMLInputElement).value)).toEqual([
      "WRITTEN_WARNING",
      "HONOR_COMMITTEE",
      "DISCIPLINE_COMMITTEE",
    ]);
    for (const ad of ["Yazılı uyarı", "Onur Kuruluna sevk", "Disiplin Kuruluna sevk"]) {
      const dugme = within(grup).getByRole("radio", { name: ad });
      expect(dugme).toHaveAttribute("aria-labelledby");
    }
    await user.click(within(grup).getByText("Onur Kuruluna sevk"));
    expect(within(grup).getByRole("radio", { name: "Onur Kuruluna sevk" })).toBeChecked();
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

// ---------------------------------------------------------------------------
// Saha gözden geçirmesi (kasım 2026): servis kilitleri ↔ arayüz hizası ve
// tek yönlü kapanların (§7.6) çıkış yolları.
// ---------------------------------------------------------------------------

const SEVK_OLAYI: DisciplineEvent = {
  id: 700,
  stage: "DECIDED",
  stage_display: "Müdür kararı",
  event_date: "2026-05-20",
  recorded_at: "2026-05-20T09:00:00Z",
  notes: "",
  assigned_guidance_name: "",
  guidance_outcome: "",
  principal_decisions: ["DISCIPLINE_COMMITTEE"],
  committee_decision_type: null,
  committee_decision_type_name: null,
  committee_decision_text: "",
  is_override: false,
  override_reason: "",
};

const UYARI: DisciplineWarning = {
  id: 31,
  student: OGRENCI.id,
  student_name: "Emre Can Yılmaz",
  warning_date: "2026-05-19",
  summary: "Derse geç kalma.",
};

const TOPLANTI: DisciplineMeeting = {
  id: 61,
  event: null,
  meeting_date: "2026-05-22",
  notes: "",
  attendees: [1, 2],
  attendee_names: ["Kemal Aksoy", "Selin Rehber"],
};

function bosListeler() {
  dapi.listParticipants.mockResolvedValue([]);
  dapi.listWarnings.mockResolvedValue([]);
  dapi.listMeetings.mockResolvedValue([]);
  dapi.triageSuggestion.mockResolvedValue({ students: [], should_route_to_committee: false });
}

describe("DisiplinDetayPage — müdür uyarısı silme (A1, tek yönlü kapan)", () => {
  it("onaylı 'Sil' uyarıyı siler; uyarı listesi ve triaj önerisi tazelenir", async () => {
    bosListeler();
    dapi.listWarnings.mockResolvedValueOnce([UYARI]).mockResolvedValue([]);
    dapi.deleteWarning.mockResolvedValue(undefined);
    const user = userEvent.setup();
    renderPage();

    await screen.findByText("İlgili öğrenciler");
    await waitFor(() => expect(dapi.triageSuggestion).toHaveBeenCalledTimes(1));
    await user.click(screen.getByRole("tab", { name: /Taraflar/ }));
    expect(await screen.findByText("Derse geç kalma.")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Sil" }));
    // Onay verilmeden silinmez.
    const dialog = await screen.findByRole("dialog");
    expect(dapi.deleteWarning).not.toHaveBeenCalled();
    await user.click(within(dialog).getByRole("button", { name: "Sil" }));

    await waitFor(() => expect(dapi.deleteWarning).toHaveBeenCalledWith(5, UYARI.id));
    await waitFor(() => expect(dapi.listWarnings).toHaveBeenCalledTimes(2));
    expect(await screen.findByText(/Henüz müdür uyarısı kaydedilmedi/)).toBeInTheDocument();

    // Uyarı kaydı triajda öğrenciyi "uyarılmış" saydırır — öneri yeniden çekilir.
    await user.click(screen.getByRole("tab", { name: /Genel/ }));
    await waitFor(() => expect(dapi.triageSuggestion).toHaveBeenCalledTimes(2));
  });

  it("onay reddedilirse silme çağrılmaz", async () => {
    bosListeler();
    dapi.listWarnings.mockResolvedValue([UYARI]);
    const user = userEvent.setup();
    renderPage();

    await screen.findByText("İlgili öğrenciler");
    await user.click(screen.getByRole("tab", { name: /Taraflar/ }));
    await user.click(await screen.findByRole("button", { name: "Sil" }));
    const dialog = await screen.findByRole("dialog");
    await user.click(within(dialog).getByRole("button", { name: "Vazgeç" }));

    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    expect(dapi.deleteWarning).not.toHaveBeenCalled();
    expect(dapi.listWarnings).toHaveBeenCalledTimes(1);
  });

  it("kapalı dosyada da uyarı silinebilir (backend delete_warning kapalı dosyada siler)", async () => {
    bosListeler();
    dapi.listWarnings.mockResolvedValue([UYARI]);
    const user = userEvent.setup();
    renderPage({ current_stage: "CLOSED", closed_at: "2026-06-01T10:00:00Z" });

    await screen.findByText("İlgili öğrenciler");
    await user.click(screen.getByRole("tab", { name: /Taraflar/ }));
    expect(await screen.findByRole("button", { name: "Sil" })).toBeEnabled();
  });

  it("sunucu silmeyi reddederse ileti gösterilir, kayıt listede kalır", async () => {
    bosListeler();
    dapi.listWarnings.mockResolvedValue([UYARI]);
    dapi.deleteWarning.mockRejectedValue(new ApiError(400, "invalid", "Uyarı silinemedi: örnek."));
    const user = userEvent.setup();
    renderPage();

    await screen.findByText("İlgili öğrenciler");
    await user.click(screen.getByRole("tab", { name: /Taraflar/ }));
    await user.click(await screen.findByRole("button", { name: "Sil" }));
    const dialog = await screen.findByRole("dialog");
    await user.click(within(dialog).getByRole("button", { name: "Sil" }));

    expect(await screen.findByText("Uyarı silinemedi: örnek.")).toBeInTheDocument();
    expect(screen.getByText("Derse geç kalma.")).toBeInTheDocument();
  });
});

describe("DisiplinDetayPage — dosya toplantısı (A2)", () => {
  it("kurula sevk edilmemiş dosyada 'Toplantı kaydet' sunulmaz", async () => {
    bosListeler();
    const user = userEvent.setup();
    renderPage({ current_stage: "DECIDED", events: [] });

    await screen.findByText("İlgili öğrenciler");
    await user.click(screen.getByRole("tab", { name: /Kurul & Karar/ }));
    expect(await screen.findByText(/Henüz kurul toplantısı kaydedilmedi/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Toplantı kaydet/ })).toBeNull();
    expect(
      screen.getByText(/yalnız disiplin kuruluna sevk edilen dosyada kaydedilir/),
    ).toBeInTheDocument();
  });

  it("kapalı dosyada 'Toplantı kaydet' ve satırdaki 'Sil' sunulmaz", async () => {
    bosListeler();
    dapi.listMeetings.mockResolvedValue([TOPLANTI]);
    const user = userEvent.setup();
    renderPage({
      current_stage: "CLOSED",
      closed_at: "2026-06-01T10:00:00Z",
      events: [SEVK_OLAYI],
    });

    await screen.findByText("İlgili öğrenciler");
    await user.click(screen.getByRole("tab", { name: /Kurul & Karar/ }));
    expect(await screen.findByText("Kemal Aksoy")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Toplantı kaydet/ })).toBeNull();
    expect(screen.queryByRole("button", { name: "Sil" })).toBeNull();
    expect(screen.getByText(/Dosya kapalı; kurul toplantısı kaydedilemez/)).toBeInTheDocument();
  });

  it("sevkli açık dosyada 'Toplantı kaydet' sunulur; onaylı 'Sil' toplantıyı siler, karar bölümü tazelenir", async () => {
    bosListeler();
    dapi.listMeetings.mockResolvedValueOnce([TOPLANTI]).mockResolvedValue([]);
    dapi.deleteMeeting.mockResolvedValue(undefined);
    const user = userEvent.setup();
    renderPage({ current_stage: "DECIDED", events: [SEVK_OLAYI] });

    await screen.findByText("İlgili öğrenciler");
    await user.click(screen.getByRole("tab", { name: /Kurul & Karar/ }));
    expect(await screen.findByText("Kemal Aksoy")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Toplantı kaydet/ })).toBeInTheDocument();
    expect(bolum.decisionsMounted).toHaveBeenCalledTimes(1);

    await user.click(screen.getByRole("button", { name: "Sil" }));
    const dialog = await screen.findByRole("dialog");
    expect(dapi.deleteMeeting).not.toHaveBeenCalled();
    await user.click(within(dialog).getByRole("button", { name: "Sil" }));

    await waitFor(() => expect(dapi.deleteMeeting).toHaveBeenCalledWith(5, TOPLANTI.id));
    // Toplantı listesi yeniden çekilir…
    await waitFor(() => expect(dapi.listMeetings).toHaveBeenCalledTimes(2));
    expect(await screen.findByText(/Henüz kurul toplantısı kaydedilmedi/)).toBeInTheDocument();
    // …EK-1/karar bölümü verisi (yeniden bağlanarak) ve dosya detayı da tazelenir.
    await waitFor(() => expect(bolum.decisionsMounted).toHaveBeenCalledTimes(2));
    await waitFor(() => expect(dapi.getCase).toHaveBeenCalledTimes(2));
  });
});

describe("DisiplinDetayPage — kapalı dosyada taraflar kilitli (A3)", () => {
  it("'Katılımcı ekle' ve 'Çıkar' gizlenir, bilgi satırı görünür", async () => {
    bosListeler();
    dapi.listParticipants.mockResolvedValue([ACCUSED]);
    const user = userEvent.setup();
    renderPage({ current_stage: "CLOSED", closed_at: "2026-06-01T10:00:00Z" });

    await screen.findByText("İlgili öğrenciler");
    await user.click(screen.getByRole("tab", { name: /Taraflar/ }));
    // Katılımcı satırı listelenir, ama eylem yok.
    expect(await screen.findByText("Katılımcılar (1)")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Katılımcı ekle/ })).toBeNull();
    expect(screen.queryByRole("button", { name: /Çıkar/ })).toBeNull();
    expect(screen.getByText("Dosya kapalı; taraflar değiştirilemez.")).toBeInTheDocument();
  });

  it("açık dosyada bilgi satırı yoktur, eylemler sunulur", async () => {
    bosListeler();
    dapi.listParticipants.mockResolvedValue([ACCUSED]);
    const user = userEvent.setup();
    renderPage();

    await screen.findByText("İlgili öğrenciler");
    await user.click(screen.getByRole("tab", { name: /Taraflar/ }));
    expect(await screen.findByRole("button", { name: /Çıkar/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Katılımcı ekle/ })).toBeInTheDocument();
    expect(screen.queryByText("Dosya kapalı; taraflar değiştirilemez.")).toBeNull();
  });
});
