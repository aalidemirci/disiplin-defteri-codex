// Onur genel kurulu paneli — md. 181/1 uyarısı (kullanıcı kararı 26.09.2026): disiplin
// cezası alan aktif temsilcide "üyeliği düşmeli" uyarısı görünür, program üyeliği kendisi
// sonlandırmaz; "Görevi sonlandır" gerekçeye md. 181/1 atfını yazar.

import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { todayIso } from "../../lib/format";
import { ConfirmProvider } from "../../ui/ConfirmProvider";
import { SnackbarProvider } from "../../ui/SnackbarProvider";
import type { HonorGeneralAssemblyMember } from "./api";

const odul = vi.hoisted(() => ({
  listGeneralAssemblyMembers: vi.fn(),
  getHonorCompliance: vi.fn(() => Promise.resolve({ configured: false, terms: [] })),
  endGeneralAssemblyMember: vi.fn<(id: number, body: { reason: string }) => Promise<unknown>>(() =>
    Promise.resolve({}),
  ),
  addGeneralAssemblyMember: vi.fn(),
  cancelPlannedGeneralAssemblyChange: vi.fn<(id: number) => Promise<void>>(() => Promise.resolve()),
}));
const okul = vi.hoisted(() => ({
  listSchoolYears: vi.fn(() => Promise.resolve([{ id: 1, name: "2025-2026", is_active: true }])),
  listSchoolTerms: vi.fn(() => Promise.resolve([])),
}));

vi.mock("./api", async (importActual) => {
  const actual = await importActual<typeof import("./api")>();
  return { ...actual, odulApi: odul };
});
vi.mock("../okul/api", async (importActual) => {
  const actual = await importActual<typeof import("../okul/api")>();
  return { ...actual, okulApi: okul };
});

import OnurGenelKuruluPanel from "./OnurGenelKuruluPanel";

function member(over: Partial<HonorGeneralAssemblyMember> = {}): HonorGeneralAssemblyMember {
  return {
    id: 5,
    school_year: 1,
    member_student: 9,
    member_name: "Ayşe Kaya",
    class_level: 11,
    class_section: "A",
    effective_from: "2025-09-08",
    effective_until: null,
    end_reason: "",
    replaced_member: null,
    is_active: true,
    md181_penalty: null,
    ...over,
  };
}

function renderPanel() {
  return render(
    <SnackbarProvider>
      <ConfirmProvider>
        <OnurGenelKuruluPanel />
      </ConfirmProvider>
    </SnackbarProvider>,
  );
}

afterEach(() => vi.clearAllMocks());

describe("OnurGenelKuruluPanel — md. 181/1", () => {
  it("cezasız temsilcide uyarı yok", async () => {
    odul.listGeneralAssemblyMembers.mockResolvedValue([member()]);
    renderPanel();
    expect(await screen.findByText("Ayşe Kaya")).toBeInTheDocument();
    expect(screen.queryByText(/md. 181\/1/)).not.toBeInTheDocument();
  });

  it("ileri tarihli değişiklikte eski temsilci görevde, yenisi 'göreve başlayacak' görünür", async () => {
    // Saha bulgusu 39 (md. 178/1): değişiklik izleyen dönem başında yürürlüğe girer.
    odul.listGeneralAssemblyMembers.mockResolvedValue([
      member({ effective_until: "2999-02-07", end_reason: "İzleyen dönem başında yeni temsilci" }),
      member({
        id: 6,
        member_name: "Uğur Çınar",
        effective_from: "2999-02-08",
        is_active: false,
        replaced_member: 5,
      }),
    ]);
    renderPanel();
    expect(await screen.findByText("Ayşe Kaya")).toBeInTheDocument();
    expect(screen.getByText(/07.02.2999 tarihine kadar görevde/)).toBeInTheDocument();
    // Bitişi kayıtlı görev yeniden sonlandırılamaz.
    expect(screen.queryByRole("button", { name: "Görevi sonlandır" })).not.toBeInTheDocument();
    expect(screen.getByText("Göreve başlayacak temsilciler")).toBeInTheDocument();
    expect(screen.queryByText("Temsilcilik geçmişi")).not.toBeInTheDocument();
  });

  it("cezalı temsilcide uyarı görünür; sonlandırma gerekçesi md. 181/1 atfı taşır", async () => {
    const user = userEvent.setup();
    odul.listGeneralAssemblyMembers.mockResolvedValue([
      member({
        md181_penalty: {
          penalty_type_display: "Kınama",
          decision_no: "2025-2026/0003",
          decision_date: "2026-05-20",
        },
      }),
    ]);
    renderPanel();
    expect(await screen.findByText(/md. 181\/1: Kınama cezası aldı/)).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Görevi sonlandır" }));
    const dialog = await screen.findByRole("dialog");
    await user.click(
      Array.from(dialog.querySelectorAll("button")).find(
        (b) => b.textContent === "Görevi sonlandır",
      )!,
    );
    await waitFor(() => expect(odul.endGeneralAssemblyMember).toHaveBeenCalled());
    expect(odul.endGeneralAssemblyMember.mock.calls[0][1]).toMatchObject({
      reason: "md. 181/1: disiplin cezası (2025-2026/0003)",
    });
  });
});

describe("OnurGenelKuruluPanel — planlanan değişiklik geri alınabilir (§7.6)", () => {
  const ESKI = member({
    effective_until: "2999-02-07",
    end_reason: "İzleyen dönem başında yeni temsilci seçildi.",
  });
  const YENI = member({
    id: 6,
    member_name: "Uğur Çınar",
    effective_from: "2999-02-08",
    is_active: false,
    replaced_member: 5,
  });

  async function onayla(etiket: string) {
    const dialog = await screen.findByRole("dialog");
    return Array.from(dialog.querySelectorAll("button")).find((b) => b.textContent === etiket)!;
  }

  it("'Planlanan değişikliği iptal et' onayla iptal ucunu çağırır ve listeyi tazeler", async () => {
    const user = userEvent.setup();
    odul.listGeneralAssemblyMembers
      .mockResolvedValueOnce([ESKI, YENI])
      .mockResolvedValue([member()]);
    renderPanel();
    expect(await screen.findByText("Göreve başlayacak temsilciler")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Planlanan değişikliği iptal et" }));
    // Onay verilmeden iptal edilmez.
    const onay = await onayla("Değişikliği iptal et");
    expect(odul.cancelPlannedGeneralAssemblyChange).not.toHaveBeenCalled();
    await user.click(onay);

    await waitFor(() => expect(odul.cancelPlannedGeneralAssemblyChange).toHaveBeenCalledWith(6));
    await waitFor(() => expect(odul.listGeneralAssemblyMembers).toHaveBeenCalledTimes(2));
    // Tazelenen listede planlanan kayıt yok; eski temsilci yeniden süresiz görevde.
    await waitFor(() =>
      expect(screen.queryByText("Göreve başlayacak temsilciler")).not.toBeInTheDocument(),
    );
    expect(screen.getByRole("button", { name: "Görevi sonlandır" })).toBeInTheDocument();
  });

  it("onay verilmezse iptal ucu çağrılmaz", async () => {
    const user = userEvent.setup();
    odul.listGeneralAssemblyMembers.mockResolvedValue([ESKI, YENI]);
    renderPanel();
    await user.click(await screen.findByRole("button", { name: "Planlanan değişikliği iptal et" }));
    await user.click(await onayla("Vazgeç"));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(odul.cancelPlannedGeneralAssemblyChange).not.toHaveBeenCalled();
  });

  it("bitişi gelecekte olan temsilcide 'Bitiş tarihini öne çek' bugünün tarihini gönderir", async () => {
    const user = userEvent.setup();
    odul.listGeneralAssemblyMembers.mockResolvedValue([
      {
        ...ESKI,
        md181_penalty: {
          penalty_type_display: "Kınama",
          decision_no: "2025-2026/0003",
          decision_date: "2026-05-20",
        },
      },
      YENI,
    ]);
    renderPanel();

    await user.click(await screen.findByRole("button", { name: "Bitiş tarihini öne çek" }));
    await user.click(await onayla("Bitişi öne çek"));

    await waitFor(() => expect(odul.endGeneralAssemblyMember).toHaveBeenCalled());
    const [id, body] = odul.endGeneralAssemblyMember.mock.calls[0];
    expect(id).toBe(5);
    expect(body).toMatchObject({
      effective_until: todayIso(),
      reason: "md. 181/1: disiplin cezası (2025-2026/0003)",
    });
  });

  it("bitmiş (bitişi geçmişte) görevde ve süresiz görevde 'Bitiş tarihini öne çek' yoktur", async () => {
    odul.listGeneralAssemblyMembers.mockResolvedValue([
      member(),
      member({
        id: 7,
        member_name: "Deniz Arı",
        class_section: "B",
        effective_until: "2025-10-01",
        end_reason: "Görev değişikliği",
        is_active: false,
      }),
    ]);
    renderPanel();
    expect(await screen.findByText("Temsilcilik geçmişi")).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Bitiş tarihini öne çek" }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Planlanan değişikliği iptal et" }),
    ).not.toBeInTheDocument();
  });
});
