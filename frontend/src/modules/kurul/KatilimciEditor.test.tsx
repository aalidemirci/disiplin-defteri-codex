// Katılımcı düzenleyicisi (saha bulguları 37, 83): başkan atfı kurula göre (ÖDK md. 188,
// Onur Kurulu md. 182); aynı kişi iki kez yazılamaz; Ödül ve Disiplin Kurulunda elle eklenen
// satır varsayılan olarak davetlidir (oy hakkı yalnız kurul üyelerinindir — md. 191/1).

import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import KatilimciEditor, { emptyRow, toRow, validateRows } from "./KatilimciEditor";
import type { AttendeeRow } from "./KatilimciEditor";

function row(name: string, over: Partial<AttendeeRow> = {}): AttendeeRow {
  return toRow({ attendee_role: "VOTING_MEMBER", person_name: name, is_chair: false, ...over });
}

describe("validateRows", () => {
  it("başkan atfı kurul türüne göredir", () => {
    const rows = [row("Ali Can")];
    expect(validateRows(rows, "HONOR")).toMatch(/md. 182/);
    expect(validateRows(rows, "HONOR")).not.toMatch(/188/);
    expect(validateRows(rows, "DISCIPLINE")).toMatch(/md. 188/);
  });

  it("aynı kişi iki kez yazılamaz (Türkçe harfe duyarsız)", () => {
    const rows = [row("Işıl Çiçek", { is_chair: true }), row("IŞIL ÇİÇEK")];
    expect(validateRows(rows, "DISCIPLINE")).toMatch(/birden çok kez/);
    expect(validateRows([rows[0], row("Ali Can")], "DISCIPLINE")).toBeNull();
  });
});

describe("KatilimciEditor", () => {
  it("Ödül ve Disiplin Kurulunda elle eklenen satır davetlidir", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(<KatilimciEditor rows={[]} onChange={onChange} idBase="t" councilType="DISCIPLINE" />);
    expect(screen.getByText(/yalnız kurulun başkanı, asıl ya da yedek üyesi/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Katılımcı ekle" }));
    expect(onChange.mock.calls[0][0][0].attendee_role).toBe("NON_VOTING_INVITEE");
  });

  it("Onur Kurulunda eklenen satır oy hakkı olan üyedir; başkan etiketi md. 182", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(
      <KatilimciEditor rows={[emptyRow()]} onChange={onChange} idBase="t" councilType="HONOR" />,
    );
    expect(screen.getByText("Başkan (md. 182)")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Katılımcı ekle" }));
    expect(onChange.mock.calls[0][0][1].attendee_role).toBe("VOTING_MEMBER");
  });
});
