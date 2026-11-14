// Ortak Autocomplete davranış testleri (Windows uçtan uca kullanım bulguları).
//
// Kapsam: (1) eski sorgunun geç gelen yanıtı güncel listeyi EZMEZ (süzme bozulmasın),
// (2) seçenek yalnız `click` ile etkinleştirildiğinde de seçilir (ekran okuyucu /
// erişilebilirlik "invoke" eylemi mousedown üretmez), (3) seçim üst bileşende
// tutulmuyorsa (çoklu ekleme kalıbı) seçimden sonra kutu temizlenir, liste kapanır.

import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";

import Autocomplete from "./Autocomplete";

interface Kisi {
  id: number;
  ad: string;
}

const HEPSI: Kisi[] = [
  { id: 1, ad: "Kemal Aksoy" },
  { id: 2, ad: "Selin Rehber" },
  { id: 3, ad: "Hakan Öztürk" },
];

function ertelenmis<T>() {
  let coz!: (value: T) => void;
  const soz = new Promise<T>((resolve) => {
    coz = resolve;
  });
  return { soz, coz };
}

describe("Autocomplete", () => {
  it("eski sorgunun geç gelen yanıtı güncel (süzülmüş) listeyi ezmez", async () => {
    const yavas = ertelenmis<Kisi[]>();
    const search = vi.fn((q: string) =>
      q === "" ? yavas.soz : Promise.resolve(HEPSI.filter((k) => k.ad.includes(q))),
    );
    const user = userEvent.setup();
    render(
      <Autocomplete<Kisi>
        label="Rehber öğretmen"
        selected={null}
        search={search}
        onSelect={() => {}}
        onClear={() => {}}
        getKey={(k) => k.id}
        getLabel={(k) => k.ad}
        minChars={0}
        debounceMs={0}
      />,
    );
    // minChars=0: boş sorguyla ilk arama yola çıkar ve yanıtı gecikir.
    await waitFor(() => expect(search).toHaveBeenCalledWith(""));

    await user.type(screen.getByLabelText("Rehber öğretmen"), "Selin");
    await waitFor(() => expect(screen.getAllByRole("option")).toHaveLength(1));

    // Boş sorgunun (bütün personel) yanıtı ŞİMDİ gelir — güncel sorgu "Selin".
    await act(async () => {
      yavas.coz(HEPSI);
      await yavas.soz;
    });

    expect(screen.getAllByRole("option")).toHaveLength(1);
    expect(screen.getByRole("option")).toHaveTextContent("Selin Rehber");
    expect(screen.queryByText("Kemal Aksoy")).not.toBeInTheDocument();
  });

  it("seçenek yalnız click ile etkinleştirildiğinde de seçilir", async () => {
    const onSelect = vi.fn();
    const user = userEvent.setup();
    render(
      <Autocomplete<Kisi>
        label="Rehber öğretmen"
        selected={null}
        search={() => Promise.resolve(HEPSI)}
        onSelect={onSelect}
        onClear={() => {}}
        getKey={(k) => k.id}
        getLabel={(k) => k.ad}
        debounceMs={0}
      />,
    );
    await user.type(screen.getByLabelText("Rehber öğretmen"), "Selin");
    const secenek = await screen.findByRole("option", { name: /Selin Rehber/ });

    // mousedown YOK: erişilebilirlik araçlarının "invoke" eylemi yalnız click üretir.
    fireEvent.click(secenek);

    expect(onSelect).toHaveBeenCalledTimes(1);
    expect(onSelect).toHaveBeenCalledWith(HEPSI[1]);
  });

  it("fareyle seçimde onSelect tek kez çağrılır (mousedown + click çift tetiklemez)", async () => {
    const onSelect = vi.fn();
    const user = userEvent.setup();
    render(
      <Autocomplete<Kisi>
        label="Rehber öğretmen"
        selected={null}
        search={() => Promise.resolve(HEPSI)}
        onSelect={onSelect}
        onClear={() => {}}
        getKey={(k) => k.id}
        getLabel={(k) => k.ad}
        debounceMs={0}
      />,
    );
    await user.type(screen.getByLabelText("Rehber öğretmen"), "Selin");
    await user.click(await screen.findByRole("option", { name: /Selin Rehber/ }));

    expect(onSelect).toHaveBeenCalledTimes(1);
  });

  it("seçim üstte tutulmuyorsa (çoklu ekleme) kutu temizlenir ve liste kapanır", async () => {
    // Yeni dosya formundaki "İlgili öğrenciler" kalıbı: onSelect listeye ekler,
    // `selected` hep null kalır; arama zaten eklenenleri dışlar.
    function CokluEkle() {
      const [eklenen, setEklenen] = useState<Kisi[]>([]);
      return (
        <>
          <ul aria-label="Eklenenler">
            {eklenen.map((k) => (
              <li key={k.id}>{k.ad}</li>
            ))}
          </ul>
          <Autocomplete<Kisi>
            label="Öğrenci ekle"
            selected={null}
            search={(q) =>
              Promise.resolve(
                HEPSI.filter((k) => k.ad.includes(q) && !eklenen.some((e) => e.id === k.id)),
              )
            }
            onSelect={(k) => setEklenen((onceki) => [...onceki, k])}
            onClear={() => {}}
            getKey={(k) => k.id}
            getLabel={(k) => k.ad}
            debounceMs={0}
            emptyText="Öğrenci bulunamadı."
          />
        </>
      );
    }
    const user = userEvent.setup();
    render(<CokluEkle />);
    const kutu = screen.getByLabelText("Öğrenci ekle");
    await user.type(kutu, "Selin");
    await user.click(await screen.findByRole("option", { name: /Selin Rehber/ }));

    expect(screen.getByRole("list", { name: "Eklenenler" })).toHaveTextContent("Selin Rehber");
    expect(kutu).toHaveValue("");
    // Kısa bir süre bekle: kutuda ad kalsaydı yeniden arama "bulunamadı" listesini açardı.
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 30));
    });
    expect(screen.queryByRole("listbox")).not.toBeInTheDocument();
    expect(screen.queryByText("Öğrenci bulunamadı.")).not.toBeInTheDocument();
  });
});
