// İmha aracı sayfası testi (F5-D2): önizleme listesi, iki aşamalı onay zinciri
// (tutanak üretilmeden imha butonu KAPALI), nakil sekmesinde "+5 iş günü"
// göstergesi ve sonuç özeti. API istemcisi vi.mock ile taklit edilir — ağ yok.
//
// Auth yok: rol/yetki senaryosu YOKTUR (tek kullanıcılı masaüstü).

import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ConfirmProvider } from "../../ui/ConfirmProvider";
import { SnackbarProvider } from "../../ui/SnackbarProvider";
import type { PurgePreview, StudentPurgePreview } from "./api";

const imha = vi.hoisted(() => ({
  preview: vi.fn(),
  previewStudent: vi.fn(),
  recordForCases: vi.fn(),
  recordForStudent: vi.fn(),
  execute: vi.fn(),
}));
const download = vi.hoisted(() => ({ saveBlob: vi.fn() }));

vi.mock("./api", () => ({ imhaApi: imha }));
vi.mock("../../lib/download", () => ({ saveBlob: download.saveBlob }));

import ImhaPage from "./ImhaPage";

const PREVIEW: PurgePreview = {
  cases: [
    {
      case_id: 7,
      case_no: "2025-2026-0004",
      petition_date: "2026-03-02",
      closed_on: "2026-03-05",
      students: ["EMRE CAN YILMAZ"],
      warning_count: 1,
      warning_letter_count: 1,
      document_count: 1,
      event_count: 3,
      attachment_count: 0,
      participant_count: 1,
      in_active_school_year: true,
    },
  ],
  students: [
    {
      student_id: 11,
      full_name: "EMRE CAN YILMAZ",
      class_label: "10/A",
      status: "ACTIVE",
      warning_count: 1,
    },
  ],
  totals: { cases: 1, warnings: 1, documents: 1, attachments: 0 },
  active_school_year_name: "2025-2026",
  active_school_year_end: "2026-06-26",
};

const STUDENT_PREVIEW: StudentPurgePreview = {
  student_id: 11,
  student_name: "EMRE CAN YILMAZ",
  class_label: "10/A",
  warnings: [
    {
      warning_id: 3,
      case_id: 7,
      case_no: "2025-2026-0004",
      student_id: 11,
      student_name: "EMRE CAN YILMAZ",
      warning_date: "2026-03-05",
      warning_letter_count: 1,
      whole_case_purgeable: true,
    },
  ],
  whole_case_ids: [7],
  totals: { warnings: 1, documents: 1, cases: 1 },
  transfer_date: "2026-06-15",
  purge_deadline: "2026-06-22",
  working_days_left: 3,
  overdue: false,
};

function renderPage() {
  return render(
    <MemoryRouter>
      <SnackbarProvider>
        <ConfirmProvider>
          <ImhaPage />
        </ConfirmProvider>
      </SnackbarProvider>
    </MemoryRouter>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  imha.preview.mockResolvedValue(PREVIEW);
  imha.previewStudent.mockResolvedValue(STUDENT_PREVIEW);
  imha.recordForCases.mockResolvedValue({
    blob: new Blob(["pdf"]),
    filename: "imha-tutanagi-20260626-101010.pdf",
    token: "jeton-1",
    storedPath: "imha/imha-tutanagi-20260626-101010.pdf",
  });
  imha.recordForStudent.mockResolvedValue({
    blob: new Blob(["pdf"]),
    filename: "imha-tutanagi-20260618-101010.pdf",
    token: "jeton-2",
    storedPath: "imha/imha-tutanagi-20260618-101010.pdf",
  });
  imha.execute.mockResolvedValue({
    purged_cases: 1,
    purged_warnings: 1,
    purged_documents: 1,
    purged_events: 3,
    purged_attachments: 0,
    purged_participants: 1,
    record_path: "imha/imha-tutanagi-20260626-101010.pdf",
    case_numbers: ["2025-2026-0004"],
  });
});

describe("ImhaPage — ders yılı sonu", () => {
  it("kapsamdaki dosyayı ve mevzuat dayanağını gösterir", async () => {
    renderPage();
    expect(await screen.findByText("2025-2026-0004")).toBeInTheDocument();
    expect(screen.getByText("EMRE CAN YILMAZ")).toBeInTheDocument();
    // Dal B dışlaması kullanıcıya AÇIKÇA söylenir.
    expect(screen.getAllByText(/kurul kararlı/i).length).toBeGreaterThan(0);
    // Aktif ders yılı rozeti (md. 157/7-d "ders yılı sonunda").
    expect(screen.getByText("aktif ders yılı")).toBeInTheDocument();
  });

  it("tutanak üretilmeden imha butonu kapalıdır", async () => {
    renderPage();
    await screen.findByText("2025-2026-0004");
    expect(screen.getByRole("button", { name: /İmhayı uygula/ })).toBeDisabled();
    expect(screen.getByText(/tutanak üretilmeden uygulanamaz/i)).toBeInTheDocument();
  });

  it("tutanak → ikinci onay → imha zincirini yürütür", async () => {
    const user = userEvent.setup();
    renderPage();
    await screen.findByText("2025-2026-0004");

    await user.click(screen.getByRole("button", { name: /Tutanağı üret ve indir/ }));
    // BİRİNCİ onay diyaloğu.
    const dialog1 = await screen.findByRole("dialog");
    await user.click(within(dialog1).getByRole("button", { name: "Tutanağı üret" }));

    await waitFor(() => expect(imha.recordForCases).toHaveBeenCalledWith([7]));
    expect(download.saveBlob).toHaveBeenCalled();

    const applyButton = await screen.findByRole("button", { name: /İmhayı uygula/ });
    await waitFor(() => expect(applyButton).toBeEnabled());

    await user.click(applyButton);
    // İKİNCİ onay diyaloğu — tutanaktan SONRA.
    const dialog2 = await screen.findByRole("dialog");
    expect(within(dialog2).getAllByText(/geri alınamaz/i).length).toBeGreaterThan(0);
    await user.click(within(dialog2).getByRole("button", { name: "İmha et" }));

    await waitFor(() => expect(imha.execute).toHaveBeenCalledWith("jeton-1"));
    expect(await screen.findByText("İmha tamamlandı")).toBeInTheDocument();
    expect(screen.getByText(/Dosya numaraları/)).toHaveTextContent("2025-2026-0004");
  });

  it("seçim değişince tutanak jetonu düşer (imha yeniden kilitlenir)", async () => {
    const user = userEvent.setup();
    renderPage();
    await screen.findByText("2025-2026-0004");

    await user.click(screen.getByRole("button", { name: /Tutanağı üret ve indir/ }));
    const dialog = await screen.findByRole("dialog");
    await user.click(within(dialog).getByRole("button", { name: "Tutanağı üret" }));
    await waitFor(() =>
      expect(screen.getByRole("button", { name: /İmhayı uygula/ })).toBeEnabled(),
    );

    await user.click(
      screen.getByRole("checkbox", { name: /2025-2026-0004 dosyasını imha kapsamına al/ }),
    );
    expect(screen.getByRole("button", { name: /İmhayı uygula/ })).toBeDisabled();
  });

  it("önizleme hatasını canlı bölgede gösterir", async () => {
    imha.preview.mockRejectedValue(new Error("kopuk"));
    renderPage();
    expect(await screen.findByRole("alert")).toHaveTextContent(/yüklenemedi/i);
  });

  it("kapsam boşsa boş durum gösterir", async () => {
    imha.preview.mockResolvedValue({ ...PREVIEW, cases: [], students: [] });
    renderPage();
    expect(await screen.findByText("İmha edilecek uyarı dosyası yok")).toBeInTheDocument();
  });
});

describe("ImhaPage — nakil (tekil)", () => {
  async function openNakil(user: ReturnType<typeof userEvent.setup>) {
    renderPage();
    await screen.findByText("2025-2026-0004");
    await user.click(screen.getByRole("tab", { name: /Nakil/ }));
  }

  it("nakil tarihine göre +5 iş günü son gününü gösterir", async () => {
    const user = userEvent.setup();
    await openNakil(user);

    await user.selectOptions(screen.getByLabelText("Öğrenci"), "11");
    await waitFor(() => expect(imha.previewStudent).toHaveBeenCalled());

    expect(await screen.findByText(/Yasal imha son günü/)).toBeInTheDocument();
    expect(screen.getByText("22.06.2026")).toBeInTheDocument();
    expect(screen.getByText(/Kalan süre: 3 iş günü/)).toBeInTheDocument();
  });

  it("süre geçtiyse gecikme uyarısı verir", async () => {
    imha.previewStudent.mockResolvedValue({ ...STUDENT_PREVIEW, overdue: true });
    const user = userEvent.setup();
    await openNakil(user);

    await user.selectOptions(screen.getByLabelText("Öğrenci"), "11");
    expect(await screen.findByText(/Süre GEÇTİ/)).toBeInTheDocument();
  });

  it("tekil imhada da tutanak → imha sırası zorunludur", async () => {
    const user = userEvent.setup();
    await openNakil(user);

    await user.selectOptions(screen.getByLabelText("Öğrenci"), "11");
    await screen.findByText(/Yasal imha son günü/);

    expect(screen.getByRole("button", { name: /İmhayı uygula/ })).toBeDisabled();

    await user.click(screen.getByRole("button", { name: /Tutanağı üret ve indir/ }));
    const dialog1 = await screen.findByRole("dialog");
    await user.click(within(dialog1).getByRole("button", { name: "Tutanağı üret" }));
    await waitFor(() => expect(imha.recordForStudent).toHaveBeenCalledWith(11, undefined));

    const applyButton = screen.getByRole("button", { name: /İmhayı uygula/ });
    await waitFor(() => expect(applyButton).toBeEnabled());
    await user.click(applyButton);
    const dialog2 = await screen.findByRole("dialog");
    await user.click(within(dialog2).getByRole("button", { name: "İmha et" }));

    await waitFor(() => expect(imha.execute).toHaveBeenCalledWith("jeton-2"));
    expect(await screen.findByText("İmha tamamlandı")).toBeInTheDocument();
  });
});
