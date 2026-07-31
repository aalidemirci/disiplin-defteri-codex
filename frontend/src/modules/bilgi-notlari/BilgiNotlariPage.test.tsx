import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it } from "vitest";

import BilgiNotlariPage from "./BilgiNotlariPage";

function renderPage(path = "/bilgi-notlari") {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/bilgi-notlari" element={<BilgiNotlariPage />} />
        <Route path="/bilgi-notlari/:notTuru" element={<BilgiNotlariPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

beforeEach(() => window.localStorage.clear());

describe("BilgiNotlariPage", () => {
  it("varsayılan olarak disiplin kurulu notunu gösterir", () => {
    renderPage();
    expect(screen.getByRole("heading", { name: "Kurul bilgi notları" })).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: "Okul Öğrenci Ödül ve Disiplin Kurulu" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Önerilen sene başı gündemi" })).toBeInTheDocument();
  });

  it("Onur Kurulu bilgi notuna geçer", async () => {
    const user = userEvent.setup();
    renderPage();
    await user.click(screen.getByRole("link", { name: /Onur Kurulu/ }));
    expect(screen.getByRole("heading", { name: "Onur Kurulu" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Tekliften karara süreç" })).toBeInTheDocument();
  });

  it("kontrol listesi ilerlemesini cihazda saklar", async () => {
    const user = userEvent.setup();
    renderPage("/bilgi-notlari/onur-kurulu");
    await user.click(screen.getByRole("checkbox", { name: /Her şubeden/ }));
    expect(screen.getByText("1 / 10")).toBeInTheDocument();
    expect(window.localStorage.getItem("bilgi-notu-kontrol-onur-kurulu")).toContain("true");
  });
});
