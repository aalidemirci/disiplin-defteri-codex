import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, it, vi } from "vitest";

const yedek = vi.hoisted(() => ({ ozet: vi.fn() }));

vi.mock("./yedekApi", () => ({ yedekApi: yedek }));
vi.mock("./YedektenGeriYukleme", () => ({
  default: () => <div data-testid="geri-yukleme-karti" />,
}));

import BekleyenGeriYuklemeBandi, { yedekDegistiYayinla } from "./BekleyenGeriYuklemeBandi";
import YedektenGeriYuklemeAcilir from "./YedektenGeriYuklemeAcilir";

beforeEach(() => vi.clearAllMocks());

it("bekleyen geri yükleme yokken bant görünmez", async () => {
  yedek.ozet.mockResolvedValue({ pending_restore: false });
  render(<BekleyenGeriYuklemeBandi />);

  await waitFor(() => expect(yedek.ozet).toHaveBeenCalled());
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
});

it("geri yükleme hazırken girilecek kayıtların kaybolacağını her ekranda söyler", async () => {
  yedek.ozet.mockResolvedValue({ pending_restore: true });
  render(<BekleyenGeriYuklemeBandi />);

  const bant = await screen.findByRole("alert");
  expect(bant).toHaveTextContent("Yedekten geri yükleme hazır");
  expect(bant).toHaveTextContent(/girdiğiniz kayıtlar geri yüklemeyle birlikte kaybolur/);
});

it("kart yedek hazırlayınca ya da vazgeçilince durumu yeniden okur", async () => {
  yedek.ozet.mockResolvedValue({ pending_restore: false });
  render(<BekleyenGeriYuklemeBandi />);
  await waitFor(() => expect(yedek.ozet).toHaveBeenCalledTimes(1));

  yedek.ozet.mockResolvedValue({ pending_restore: true });
  act(() => yedekDegistiYayinla());

  expect(await screen.findByRole("alert")).toBeInTheDocument();
});

it("durum okunamazsa sessiz kalır", async () => {
  yedek.ozet.mockRejectedValue(new Error("ağ yok"));
  render(<BekleyenGeriYuklemeBandi />);

  await waitFor(() => expect(yedek.ozet).toHaveBeenCalled());
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
});

it("açılır bölüm kartı ancak istenince gösterir", async () => {
  render(<YedektenGeriYuklemeAcilir etiket="Yedekten geri yükleyin" />);

  expect(screen.queryByTestId("geri-yukleme-karti")).not.toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "Yedekten geri yükleyin" }));

  expect(screen.getByTestId("geri-yukleme-karti")).toBeInTheDocument();
});
