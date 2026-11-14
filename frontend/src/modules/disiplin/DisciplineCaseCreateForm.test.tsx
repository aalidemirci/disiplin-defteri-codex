// Yeni disiplin dosyası formu — öğrenci ekleme alanı (Windows kullanım bulgusu).
//
// Öğrenci seçildikten sonra arama kutusunda ad kalıyor, kutu aynı adla yeniden
// arıyor ve (eklenen öğrenci sonuçlardan dışlandığı için) "Öğrenci bulunamadı."
// listesi "Eksik veli bilgisi" kutusunun üstüne biniyordu.

import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { SnackbarProvider } from "../../ui/SnackbarProvider";

const slookup = vi.hoisted(() => ({ search: vi.fn() }));

vi.mock("./api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("./api")>();
  return {
    ...actual,
    disiplinApi: { createCase: vi.fn() },
    studentLookupApi: slookup,
    personnelLookupApi: { search: vi.fn(() => Promise.resolve([])) },
  };
});

vi.mock("../okul/api", () => ({ okulApi: { updateStudent: vi.fn() } }));

import DisciplineCaseCreateForm from "./DisciplineCaseCreateForm";

const OGRENCI = {
  id: 50,
  full_name: "Ali Yılmaz",
  student_number: "101",
  class_label: "9/A",
  guardian_name: "",
};

afterEach(() => vi.clearAllMocks());

describe("DisciplineCaseCreateForm — ilgili öğrenci ekleme", () => {
  it("öğrenci seçilince arama kutusu temizlenir ve sonuç listesi kapanır", async () => {
    slookup.search.mockResolvedValue([OGRENCI]);
    const user = userEvent.setup();
    render(
      <SnackbarProvider>
        <DisciplineCaseCreateForm onCancel={() => {}} onCreated={() => {}} />
      </SnackbarProvider>,
    );

    const kutu = screen.getByRole("textbox", { name: "İlgili öğrenciler" });
    await user.type(kutu, "Ali");
    await user.click(await screen.findByRole("option", { name: /Ali Yılmaz/ }));

    // Öğrenci chip olarak eklendi, veli adı istenir.
    expect(screen.getByRole("button", { name: "Öğrenciyi kaldır" })).toBeInTheDocument();
    expect(screen.getByText("Eksik veli bilgisi")).toBeInTheDocument();

    expect(kutu).toHaveValue("");
    // Debounce (300 ms) geçtikten sonra da liste açılmamalı.
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 400));
    });
    expect(screen.queryByRole("listbox")).not.toBeInTheDocument();
    expect(screen.queryByText("Öğrenci bulunamadı.")).not.toBeInTheDocument();
    // Seçimden sonra aynı adla yeniden arama yapılmadı.
    expect(slookup.search).toHaveBeenCalledTimes(1);
  });
});
