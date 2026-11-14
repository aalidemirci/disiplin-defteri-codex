// Kabuk — rota değişiminde kaydırma konumu (Windows kullanım bulgusu).
//
// Uzun bir sayfanın ortasındayken menüden başka sayfaya (Ayarlar, Kişiler) geçilince
// yeni sayfa ortasından açılıyordu: SPA'da tarayıcı kaydırmayı kendisi sıfırlamaz.

import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("./modules/guncelleme/UpdateBanner", () => ({ default: () => null }));
vi.mock("./modules/guvenlik/BekleyenGeriYuklemeBandi", () => ({ default: () => null }));

import AppShell from "./AppShell";

describe("AppShell — rota değişiminde kaydırma", () => {
  const scrollTo = vi.fn();

  beforeEach(() => {
    vi.stubGlobal("scrollTo", scrollTo);
  });
  afterEach(() => {
    vi.unstubAllGlobals();
    scrollTo.mockReset();
  });

  it("başka sayfaya geçilince pencere en üste kaydırılır", async () => {
    const user = userEvent.setup();
    render(
      <MemoryRouter initialEntries={["/disiplin"]}>
        <AppShell>
          <p>içerik</p>
        </AppShell>
      </MemoryRouter>,
    );
    scrollTo.mockClear();

    await user.click(screen.getAllByRole("link", { name: "Ayarlar" })[0]);

    expect(scrollTo).toHaveBeenCalledWith(0, 0);
  });

  it("yalnız sorgu parametresi değişince (aynı sayfa) kaydırma konumu korunur", async () => {
    const user = userEvent.setup();
    render(
      <MemoryRouter initialEntries={["/disiplin"]}>
        <AppShell>
          <p>içerik</p>
        </AppShell>
      </MemoryRouter>,
    );
    scrollTo.mockClear();

    // Üst çubuk araması aynı sayfaya `?ara=` ile gider — sayfa değişmez.
    await user.type(screen.getByLabelText("Dosya veya öğrenci ara"), "ali{Enter}");

    expect(scrollTo).not.toHaveBeenCalled();
  });
});
