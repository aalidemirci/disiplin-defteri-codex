// Kullanıcı kararı, 14.11.2026 — S7 (VEKÂLET KAYDI): Ödül ve Disiplin Kurulu toplantı
// formunda "Başkan toplantıya katılmadı" kutusu + "Başkanlık eden" seçimi. Başkan
// katılmadıysa kurula asıl öğretmen üyelerden biri başkanlık eder (md. 188); başkan seçilen
// dosyada şikâyetçi / zarar gören ise kurula katılamaz (md. 191/2) — kutu zorunlu ve nedeni
// yazılıdır. Onur Kurulu toplantısında (md. 182) kutu yoktur.

import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { SnackbarProvider } from "../../ui/SnackbarProvider";

const kapi = vi.hoisted(() => ({
  prefill: vi.fn(),
  compositionWarnings: vi.fn(),
  createMeeting: vi.fn(),
  caseOptions: vi.fn(),
  actingChairOptions: vi.fn(),
}));

vi.mock("./api", async (importActual) => {
  const actual = await importActual<typeof import("./api")>();
  return {
    ...actual,
    kurulApi: kapi,
    listSchoolYears: vi.fn(() =>
      Promise.resolve({
        school_years: [
          {
            id: 1,
            name: "2025-2026",
            start_date: "2025-09-08",
            end_date: "2026-06-26",
            is_active: true,
          },
        ],
      }),
    ),
  };
});

import ToplantiForm from "./ToplantiForm";

const CHAIR = {
  person_name: "Ayşe Başkan",
  title: "Kurul Başkanı (Müdür Yardımcısı)",
  attendee_role: "VOTING_MEMBER",
  is_chair: true,
  member_user_id: 7,
  member_student_id: null,
  order: 0,
};
const OGRETMEN = {
  person_name: "İpek Öğretmen",
  title: "Öğretmen",
  attendee_role: "VOTING_MEMBER",
  is_chair: false,
  member_user_id: 71,
  member_student_id: null,
  order: 1,
};
const SECENEKLER = {
  chair: 7,
  chair_name: "Ayşe Başkan",
  chair_conflicted: false,
  eligible: [{ member_id: 11, member_user: 71, member_name: "İpek Öğretmen", title: "" }],
};

function form(councilType: "DISCIPLINE" | "HONOR") {
  render(
    <SnackbarProvider>
      <ToplantiForm councilType={councilType} onCreated={vi.fn()} onCancel={vi.fn()} />
    </SnackbarProvider>,
  );
}

function hazirla() {
  kapi.prefill.mockResolvedValue({ attendees: [CHAIR, OGRETMEN] });
  kapi.compositionWarnings.mockResolvedValue([]);
  kapi.actingChairOptions.mockResolvedValue(SECENEKLER);
  kapi.createMeeting.mockResolvedValue({ id: 3, meeting_no_display: "T003" });
}

afterEach(() => vi.clearAllMocks());

describe("ToplantiForm — başkan vekâleti (S7)", () => {
  it("kutu işaretlenince başkan listeden çıkar; seçilen öğretmen üye başkanlık eder", async () => {
    const user = userEvent.setup();
    hazirla();
    form("DISCIPLINE");
    await screen.findByDisplayValue("Ayşe Başkan");

    const kutu = await screen.findByRole("checkbox", { name: /Başkan toplantıya katılmadı/ });
    expect(kutu).not.toBeChecked();
    await user.click(kutu);
    expect(screen.queryByDisplayValue("Ayşe Başkan")).not.toBeInTheDocument();

    await user.type(screen.getByLabelText("Toplantı Tarihi"), "2026-05-25");
    // Başkanlık eden seçilmeden kaydedilmez.
    await user.click(screen.getByRole("button", { name: "Tutanağı Kaydet" }));
    expect(await screen.findByText(/başkanlık eden öğretmen üyeyi seçin/)).toBeInTheDocument();
    expect(kapi.createMeeting).not.toHaveBeenCalled();

    await user.selectOptions(screen.getByLabelText(/Başkanlık eden öğretmen üye/), "11");
    await user.click(screen.getByRole("button", { name: "Tutanağı Kaydet" }));
    await waitFor(() => expect(kapi.createMeeting).toHaveBeenCalledTimes(1));
    const body = kapi.createMeeting.mock.calls[0][0] as {
      chair_absent?: boolean;
      attendees: { person_name: string; is_chair: boolean }[];
    };
    expect(body.chair_absent).toBe(true);
    expect(body.attendees).toEqual([
      expect.objectContaining({ person_name: "İpek Öğretmen", is_chair: true }),
    ]);
  });

  it("kutu kaldırılınca kurul başkanı başkan satırı olarak geri gelir", async () => {
    const user = userEvent.setup();
    hazirla();
    form("DISCIPLINE");
    await screen.findByDisplayValue("Ayşe Başkan");
    const kutu = await screen.findByRole("checkbox", { name: /Başkan toplantıya katılmadı/ });
    await user.click(kutu);
    await user.selectOptions(screen.getByLabelText(/Başkanlık eden öğretmen üye/), "11");
    await user.click(kutu);
    expect(screen.getByDisplayValue("Ayşe Başkan")).toBeInTheDocument();

    await user.type(screen.getByLabelText("Toplantı Tarihi"), "2026-05-25");
    await user.click(screen.getByRole("button", { name: "Tutanağı Kaydet" }));
    await waitFor(() => expect(kapi.createMeeting).toHaveBeenCalledTimes(1));
    const body = kapi.createMeeting.mock.calls[0][0] as {
      attendees: { person_name: string; is_chair: boolean }[];
    };
    // Vekâlet kutusu işaretli değilken gövdede chair_absent yoktur.
    expect(body).not.toHaveProperty("chair_absent");
    expect(body.attendees.filter((a) => a.is_chair).map((a) => a.person_name)).toEqual([
      "Ayşe Başkan",
    ]);
  });

  it("şikâyetçi başkanın dosyası seçilince kutu zorunlu olur ve nedeni yazılır", async () => {
    const user = userEvent.setup();
    hazirla();
    kapi.caseOptions.mockResolvedValue({
      cases: [{ id: 9, case_no: "2025-2026-0009", students: ["Ali Veli"] }],
    });
    kapi.actingChairOptions.mockImplementation((caseId?: number | null) =>
      Promise.resolve({ ...SECENEKLER, chair_conflicted: caseId === 9 }),
    );
    form("DISCIPLINE");
    await screen.findByDisplayValue("Ayşe Başkan");

    await user.selectOptions(screen.getByLabelText("Tutanak Türü"), "CASE_REVIEW");
    await screen.findByRole("option", { name: /2025-2026-0009/ });
    await user.selectOptions(screen.getByLabelText("Görüşülen Disiplin Dosyası"), "9");

    expect(await screen.findByText(/kurula katılamaz \(md\. 191\/2\)/)).toBeInTheDocument();
    const kutu = screen.getByRole("checkbox", { name: /Başkan toplantıya katılmadı/ });
    expect(kutu).toBeChecked();
    expect(kutu).toBeDisabled();
    // Zorunluluğun nedeni kutuya bağlıdır (ekran okuyucu kilitli kutuyla birlikte okur).
    expect(kutu).toHaveAccessibleDescription(/kurula katılamaz \(md\. 191\/2\)/);
    expect(screen.queryByDisplayValue("Ayşe Başkan")).not.toBeInTheDocument();
    expect(kapi.actingChairOptions).toHaveBeenLastCalledWith(9);
  });

  it("zorunluluk kalkınca (başka dosya / tür) kutu ve başkan satırı eski hâline döner", async () => {
    const user = userEvent.setup();
    hazirla();
    kapi.caseOptions.mockResolvedValue({
      cases: [
        { id: 9, case_no: "2025-2026-0009", students: ["Ali Veli"] },
        { id: 10, case_no: "2025-2026-0010", students: ["Can Demir"] },
      ],
    });
    kapi.actingChairOptions.mockImplementation((caseId?: number | null) =>
      Promise.resolve({ ...SECENEKLER, chair_conflicted: caseId === 9 }),
    );
    form("DISCIPLINE");
    await screen.findByDisplayValue("Ayşe Başkan");
    await user.selectOptions(screen.getByLabelText("Tutanak Türü"), "CASE_REVIEW");
    await screen.findByRole("option", { name: /2025-2026-0009/ });
    const dosya = screen.getByLabelText("Görüşülen Disiplin Dosyası");
    await user.selectOptions(dosya, "9");
    const kutu = screen.getByRole("checkbox", { name: /Başkan toplantıya katılmadı/ });
    await waitFor(() => expect(kutu).toBeChecked());
    await user.selectOptions(screen.getByLabelText(/Başkanlık eden öğretmen üye/), "11");

    // Yanlış dosya seçilmişti: doğru dosyada başkan engelli değil.
    await user.selectOptions(dosya, "10");
    await waitFor(() => expect(kutu).not.toBeChecked());
    expect(kutu).toBeEnabled();
    expect(screen.getByDisplayValue("Ayşe Başkan")).toBeInTheDocument();

    await user.type(screen.getByLabelText("Toplantı Tarihi"), "2026-05-25");
    await user.click(screen.getByRole("button", { name: "Tutanağı Kaydet" }));
    await waitFor(() => expect(kapi.createMeeting).toHaveBeenCalledTimes(1));
    const body = kapi.createMeeting.mock.calls[0][0] as {
      attendees: { person_name: string; is_chair: boolean }[];
    };
    expect(body).not.toHaveProperty("chair_absent");
    expect(body.attendees.filter((a) => a.is_chair).map((a) => a.person_name)).toEqual([
      "Ayşe Başkan",
    ]);
  });

  it("elle işaretlenen kutu dosya değişince kendiliğinden kalkmaz", async () => {
    const user = userEvent.setup();
    hazirla();
    kapi.caseOptions.mockResolvedValue({
      cases: [{ id: 10, case_no: "2025-2026-0010", students: ["Can Demir"] }],
    });
    form("DISCIPLINE");
    await screen.findByDisplayValue("Ayşe Başkan");
    const kutu = await screen.findByRole("checkbox", { name: /Başkan toplantıya katılmadı/ });
    await user.click(kutu);
    await user.selectOptions(screen.getByLabelText("Tutanak Türü"), "CASE_REVIEW");
    await screen.findByRole("option", { name: /2025-2026-0010/ });
    await user.selectOptions(screen.getByLabelText("Görüşülen Disiplin Dosyası"), "10");
    await waitFor(() => expect(kapi.actingChairOptions).toHaveBeenLastCalledWith(10));
    expect(kutu).toBeChecked();
    expect(screen.queryByDisplayValue("Ayşe Başkan")).not.toBeInTheDocument();
  });

  it("Onur Kurulu toplantısında vekâlet kutusu yoktur", async () => {
    kapi.prefill.mockResolvedValue({ attendees: [] });
    form("HONOR");
    await waitFor(() => expect(kapi.prefill).toHaveBeenCalled());
    expect(kapi.actingChairOptions).not.toHaveBeenCalled();
    expect(screen.queryByRole("checkbox", { name: /Başkan toplantıya katılmadı/ })).toBeNull();
  });
});
