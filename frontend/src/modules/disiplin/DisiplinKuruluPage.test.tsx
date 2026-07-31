// Disiplin Kurulu sayfası testi (Tur 71/Faz 4; Tur 212 sekmeli): kurul yoksa
// oluşturma kartı, kurul varsa başkan + üye listesi + üye çıkarma, veli üye
// ad snapshot'ı ile ekleme, tutanak sekmesi.
//
// OYS `modules/disiplin/DisiplinKuruluPage.test.tsx`'ten UYARLANDI (F4-D2). Sapmalar:
// auth yok — yetkisiz/memur kilit senaryoları kalktı (rol kapısı yok, hepsi-yetkili);
// `sistem/api` yerine `okul/api` mock'u (okulApi.listSchoolYears düz dizi);
// userLookup/parentLookup yerine personnelLookup; fixture'da member_parent/created_at
// yok; VELİ üye member_name snapshot'ı testi eklendi (addCommitteeMember kurulun
// tamamını döner — yeniden yükleme yapılmaz).

import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ConfirmProvider } from "../../ui/ConfirmProvider";
import { SnackbarProvider } from "../../ui/SnackbarProvider";
import type { DisciplineCommittee } from "./api";

const dapi = vi.hoisted(() => ({
  getCommittee: vi.fn(),
  createCommittee: vi.fn(),
  setCommitteeChair: vi.fn(),
  addCommitteeMember: vi.fn(),
  removeCommitteeMember: vi.fn(),
}));

vi.mock("./api", () => ({
  disiplinApi: dapi,
  personnelLookupApi: { search: vi.fn(() => Promise.resolve([])) },
  studentLookupApi: { search: vi.fn(() => Promise.resolve([])) },
  COMMITTEE_MEMBER_TYPE_TR: { TEACHER: "Öğretmen", STUDENT: "Öğrenci", PARENT: "Veli" },
}));

vi.mock("../okul/api", () => ({
  okulApi: {
    listSchoolYears: vi.fn(() =>
      Promise.resolve([
        {
          id: 1,
          name: "2025-2026",
          start_date: "2025-09-01",
          end_date: "2026-06-30",
          is_active: true,
        },
      ]),
    ),
  },
}));

// Tutanak listesi ayrı bileşen olarak test edilir; sayfa testi sekme kabuğuna odaklanır.
vi.mock("../kurul/TutanakListesi", () => ({
  default: ({ councilType }: { councilType: string }) => (
    <div data-testid="tutanak-listesi">{councilType}</div>
  ),
}));

import DisiplinKuruluPage from "./DisiplinKuruluPage";

const COMMITTEE: DisciplineCommittee = {
  id: 1,
  school_year: 1,
  chair: 7,
  chair_name: "Ayşe Müdür Yardımcısı",
  notes: "",
  members: [
    {
      id: 10,
      member_type: "TEACHER",
      member_type_display: "Öğretmen",
      is_substitute: false,
      order: 0,
      title: "Zümre başkanı",
      member_name: "Mehmet Öğretmen",
      member_user: 30,
      member_student: null,
    },
    {
      id: 11,
      member_type: "STUDENT",
      member_type_display: "Öğrenci",
      is_substitute: true,
      order: 0,
      title: "",
      member_name: "Zeynep Öğrenci",
      member_user: null,
      member_student: 50,
    },
  ],
};

function renderPage() {
  return render(
    <SnackbarProvider>
      <ConfirmProvider>
        <MemoryRouter>
          <DisiplinKuruluPage />
        </MemoryRouter>
      </ConfirmProvider>
    </SnackbarProvider>,
  );
}

afterEach(() => {
  vi.clearAllMocks();
});

describe("DisiplinKuruluPage", () => {
  it("üyeler varsayılan sekme, tutanak sekmesi erişilebilir", async () => {
    dapi.getCommittee.mockResolvedValue({ committee: COMMITTEE });
    const user = userEvent.setup();
    renderPage();
    expect(await screen.findByText("Ayşe Müdür Yardımcısı")).toBeInTheDocument();
    await user.click(screen.getByRole("tab", { name: /Toplantı Tutanakları/ }));
    expect(await screen.findByTestId("tutanak-listesi")).toHaveTextContent("DISCIPLINE");
  });

  it("kurul yoksa: oluşturma kartı gösterilir", async () => {
    dapi.getCommittee.mockResolvedValue({ committee: null });
    renderPage();
    expect(await screen.findByText("Kurul oluştur")).toBeInTheDocument();
    expect(screen.getByText(/Kurul başkanı \(müdür yardımcısı\)/)).toBeInTheDocument();
  });

  it("kurul varsa: başkan + asıl/yedek üyeler listelenir", async () => {
    dapi.getCommittee.mockResolvedValue({ committee: COMMITTEE });
    renderPage();
    expect(await screen.findByText("Ayşe Müdür Yardımcısı")).toBeInTheDocument();
    expect(screen.getByText("Mehmet Öğretmen")).toBeInTheDocument();
    expect(screen.getByText("Zeynep Öğrenci")).toBeInTheDocument();
    expect(screen.getByText("Asıl üyeler")).toBeInTheDocument();
    expect(screen.getByText("Yedek üyeler")).toBeInTheDocument();
  });

  it("veli üye: ad snapshot'ı ile eklenir, dönen kurulla liste tazelenir", async () => {
    dapi.getCommittee.mockResolvedValue({ committee: COMMITTEE });
    dapi.addCommitteeMember.mockResolvedValue({
      ...COMMITTEE,
      members: [
        ...COMMITTEE.members,
        {
          id: 12,
          member_type: "PARENT",
          member_type_display: "Veli",
          is_substitute: false,
          order: 1,
          title: "",
          member_name: "Fatma Veli",
          member_user: null,
          member_student: null,
        },
      ],
    });
    const user = userEvent.setup();
    renderPage();

    await screen.findByText("Mehmet Öğretmen");
    await user.click(screen.getByRole("button", { name: /Üye ekle/ }));
    // Veli tipinde FK yok — autocomplete yerine serbest metin ad alanı çıkar.
    await user.selectOptions(screen.getByLabelText(/Üye tipi/), "PARENT");
    await user.type(screen.getByLabelText(/Veli adı soyadı/), "Fatma Veli");
    await user.click(screen.getByRole("button", { name: /Üyeyi ekle/ }));

    await waitFor(() =>
      expect(dapi.addCommitteeMember).toHaveBeenCalledWith({
        member_type: "PARENT",
        member_name: "Fatma Veli",
        is_substitute: false,
        order: 0,
        title: "",
      }),
    );
    // Dönen kurul state'i tazeler — yeni üye görünür, getCommittee YENİDEN çağrılmaz.
    expect(await screen.findByText("Fatma Veli")).toBeInTheDocument();
    expect(dapi.getCommittee).toHaveBeenCalledTimes(1);
  });

  it("üye çıkar: onay dialog'unda onaylayınca API çağrılır ve liste yenilenir", async () => {
    dapi.getCommittee.mockResolvedValue({ committee: COMMITTEE });
    dapi.removeCommitteeMember.mockResolvedValue(undefined);
    const user = userEvent.setup();
    renderPage();

    await screen.findByText("Mehmet Öğretmen");
    // Satırdaki "Çıkar" → M3 onay dialog'unu açar (native confirm yerine, C12).
    const removeButtons = screen.getAllByRole("button", { name: /Çıkar/ });
    await user.click(removeButtons[0]);

    // Dialog'daki "Çıkar" onay butonuna bas.
    const dialog = await screen.findByRole("dialog");
    await user.click(within(dialog).getByRole("button", { name: "Çıkar" }));

    await waitFor(() => expect(dapi.removeCommitteeMember).toHaveBeenCalledWith(10));
    // onChanged → getCommittee yeniden çağrılır (ilk yük + yenileme).
    await waitFor(() => expect(dapi.getCommittee).toHaveBeenCalledTimes(2));
  });
});
