// SelectOrOther — "Seçim + Diğer" girişi (Tur 148, Talep 3 Faz B) bileşen testi.
// Stateful harness ile gerçek controlled davranış doğrulanır (seç → değer; Diğer →
// serbest kutu; eşleşmeyen eski değer → Diğer modunda açılır).

import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { describe, expect, it } from "vitest";

import SelectOrOther from "./SelectOrOther";

const OPTIONS = ["Gündüzlü", "Parasız yatılı", "Paralı yatılı"];

function Harness({ initial = "" }: { initial?: string }) {
  const [v, setV] = useState(initial);
  return (
    <>
      <SelectOrOther label="Yatılılık" value={v} options={OPTIONS} onChange={setV} />
      <output data-testid="val">{v}</output>
    </>
  );
}

describe("SelectOrOther", () => {
  it("boş değerde placeholder; serbest kutu kapalı; 'Diğer…' seçeneği var", () => {
    render(<Harness />);
    expect((screen.getByLabelText("Yatılılık") as HTMLSelectElement).value).toBe("");
    expect(screen.queryByLabelText("Yatılılık — diğer")).toBeNull();
    expect(screen.getByRole("option", { name: "Diğer…" })).toBeInTheDocument();
  });

  it("gerçek seçenek seçilince değer o etiket olur, serbest kutu açılmaz", async () => {
    render(<Harness />);
    await userEvent.selectOptions(screen.getByLabelText("Yatılılık"), "Parasız yatılı");
    expect(screen.getByTestId("val")).toHaveTextContent("Parasız yatılı");
    expect(screen.queryByLabelText("Yatılılık — diğer")).toBeNull();
  });

  it("'Diğer…' seçilince serbest kutu açılır ve yazılan değer kaydedilir", async () => {
    render(<Harness />);
    await userEvent.selectOptions(screen.getByLabelText("Yatılılık"), "Diğer…");
    const other = screen.getByLabelText("Yatılılık — diğer");
    await userEvent.type(other, "Yurtta");
    expect(screen.getByTestId("val")).toHaveTextContent("Yurtta");
  });

  it("eşleşmeyen mevcut değer (eski serbest metin) 'Diğer' modunda açılır", () => {
    render(<Harness initial="Akraba yanında" />);
    expect((screen.getByLabelText("Yatılılık") as HTMLSelectElement).value).toBe("__other__");
    expect((screen.getByLabelText("Yatılılık — diğer") as HTMLInputElement).value).toBe(
      "Akraba yanında",
    );
  });

  it("eşleşen mevcut değer select'te seçili; serbest kutu kapalı", () => {
    render(<Harness initial="Gündüzlü" />);
    expect((screen.getByLabelText("Yatılılık") as HTMLSelectElement).value).toBe("Gündüzlü");
    expect(screen.queryByLabelText("Yatılılık — diğer")).toBeNull();
  });
});
