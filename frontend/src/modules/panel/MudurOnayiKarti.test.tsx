// Panel "Müdür onayı bekleyenler" kartı (04.10.2026): bekleyen yoksa görünmez; disiplin
// kurulu kararı dosyaya, onur belgesi kararları Ödül ve Disiplin Kurulu → Müdür Onayı'na gider.

import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

const kapi = vi.hoisted(() => ({ principalPending: vi.fn() }));

vi.mock("../kurul/api", async (importActual) => {
  const actual = await importActual<typeof import("../kurul/api")>();
  return { ...actual, kurulApi: kapi };
});

import MudurOnayiKarti from "./MudurOnayiKarti";

function ekran() {
  return render(
    <MemoryRouter>
      <MudurOnayiKarti />
    </MemoryRouter>,
  );
}

afterEach(() => vi.clearAllMocks());

describe("MudurOnayiKarti", () => {
  it("bekleyen kararları bağlantılarıyla listeler", async () => {
    kapi.principalPending.mockResolvedValue({
      honor_certificates: [
        { id: 3, student_name: "Ali Veli", class_label: "10/A", awarded_at: "2026-06-01" },
      ],
      decisions: [
        {
          id: 8,
          case: 12,
          case_no: "2025-2026-0012",
          student_name: "Can Demir",
          penalty_type_display: "Kınama",
          decision_no: "1",
          decision_date: "2026-05-22",
        },
      ],
    });
    ekran();
    expect(await screen.findByText("Müdür onayı bekleyenler")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Can Demir — Kınama/ })).toHaveAttribute(
      "href",
      "/disiplin/12",
    );
    expect(screen.getByRole("link", { name: /1 onur belgesi kararı/ })).toHaveAttribute(
      "href",
      "/odul-disiplin-kurulu?sekme=mudur-onayi",
    );
  });

  it("bekleyen yoksa kart görünmez", async () => {
    kapi.principalPending.mockResolvedValue({ honor_certificates: [], decisions: [] });
    const { container } = ekran();
    await vi.waitFor(() => expect(kapi.principalPending).toHaveBeenCalled());
    expect(container).toBeEmptyDOMElement();
  });
});
