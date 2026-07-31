import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ConfirmProvider } from "../../ui/ConfirmProvider";
import { SnackbarProvider } from "../../ui/SnackbarProvider";

const okul = vi.hoisted(() => ({
  listSchoolYears: vi.fn(),
  listClassResponsibilities: vi.fn(),
  listPersonnel: vi.fn(),
  createClassResponsibility: vi.fn(),
  updateClassResponsibility: vi.fn(),
  deleteClassResponsibility: vi.fn(),
}));

vi.mock("../okul/api", () => ({ okulApi: okul }));

import SinifSorumlulariPage from "./SinifSorumlulariPage";

const REHBER = {
  id: 9,
  first_name: "Örnek",
  last_name: "Rehber",
  full_name: "Örnek Rehber",
  title: "Rehber Öğretmen",
  branch: "Rehberlik",
};

const ROW = {
  id: 4,
  school_year: 1,
  school_year_name: "2026-2027",
  class_level: 10,
  class_section: "A",
  class_label: "10/A",
  class_teacher: null,
  class_teacher_detail: null,
  assistant_principal: null,
  assistant_principal_detail: null,
  guidance_teacher: REHBER.id,
  guidance_teacher_detail: REHBER,
};

function renderPage() {
  okul.listSchoolYears.mockResolvedValue([
    {
      id: 1,
      name: "2026-2027",
      start_date: "2026-09-01",
      end_date: "2027-06-30",
      is_active: true,
    },
  ]);
  okul.listClassResponsibilities.mockResolvedValue([ROW]);
  okul.listPersonnel.mockResolvedValue({
    count: 1,
    next: null,
    previous: null,
    results: [REHBER],
  });
  return render(
    <SnackbarProvider>
      <ConfirmProvider>
        <MemoryRouter>
          <SinifSorumlulariPage />
        </MemoryRouter>
      </ConfirmProvider>
    </SnackbarProvider>,
  );
}

afterEach(() => vi.clearAllMocks());

describe("SinifSorumlulariPage", () => {
  it("aktif yılın şubesini ve atanmış rehber öğretmeni gösterir", async () => {
    renderPage();

    expect(await screen.findByText("10/A")).toBeInTheDocument();
    expect(screen.getByText("Örnek Rehber")).toBeInTheDocument();
    expect(okul.listClassResponsibilities).toHaveBeenCalledWith(1);
  });

  it("düzenleme mevcut sorumluları kimlikleriyle kaydeder", async () => {
    okul.updateClassResponsibility.mockResolvedValue(ROW);
    const user = userEvent.setup();
    renderPage();

    await screen.findByText("10/A");
    await user.click(screen.getByRole("button", { name: "Düzenle" }));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText("Örnek Rehber")).toBeInTheDocument();
    await user.click(within(dialog).getByRole("button", { name: "Kaydet" }));

    await waitFor(() =>
      expect(okul.updateClassResponsibility).toHaveBeenCalledWith(4, {
        school_year: 1,
        class_level: 10,
        class_section: "A",
        class_teacher: null,
        assistant_principal: null,
        guidance_teacher: 9,
      }),
    );
  });
});
