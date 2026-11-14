// VEKÂLET KAYDI (kullanıcı kararı, 14.11.2026 — S7) — katılımcı satırı yardımcıları.
// md. 188: başkan bulunmadığında öğretmen üyelerden biri başkanlık eder; başkan katılımcı
// listesinde yer almaz. Vekâlet kaldırılınca kurul başkanı başkan satırı olarak geri gelir.

import { describe, expect, it } from "vitest";

import {
  actingChairMemberId,
  withActingChair,
  withChairRestored,
  withoutChair,
} from "./BaskanVekaleti";
import { toRow } from "./KatilimciEditor";

const SECENEKLER = {
  chair: 70,
  chair_name: "Işıl Çağrı",
  chair_conflicted: false,
  eligible: [
    { member_id: 11, member_user: 71, member_name: "İpek Öğretmen", title: "" },
    { member_id: 12, member_user: 72, member_name: "Ilgaz Şahin", title: "Öğretmen" },
  ],
};

function satirlar() {
  return [
    toRow({
      attendee_role: "VOTING_MEMBER",
      person_name: "Işıl Çağrı",
      is_chair: true,
      member_user_id: 70,
    }),
    toRow({
      attendee_role: "VOTING_MEMBER",
      person_name: "İpek Öğretmen",
      is_chair: false,
      member_user_id: 71,
    }),
    toRow({ attendee_role: "VOTING_MEMBER", person_name: "Hasan Velioğlu", is_chair: false }),
  ];
}

describe("BaskanVekaleti yardımcıları (S7)", () => {
  it("withoutChair başkanı çıkarır ve başkan işaretini temizler", () => {
    const rows = withoutChair(satirlar(), SECENEKLER);
    expect(rows.map((r) => r.person_name)).toEqual(["İpek Öğretmen", "Hasan Velioğlu"]);
    expect(rows.some((r) => r.is_chair)).toBe(false);
  });

  it("elle yazılmış (kayıt bağı olmayan) başkan satırı Türkçe harfe duyarsız adla eşleşir", () => {
    const rows = [
      toRow({ attendee_role: "VOTING_MEMBER", person_name: "ışıl  çağrı", is_chair: true }),
    ];
    expect(withoutChair(rows, SECENEKLER)).toHaveLength(0);
  });

  it("withActingChair listedeki öğretmeni tek başkan yapar; listede yoksa ekler", () => {
    const first = withActingChair(satirlar(), SECENEKLER, 11);
    expect(first.filter((r) => r.is_chair).map((r) => r.person_name)).toEqual(["İpek Öğretmen"]);
    expect(first).toHaveLength(2);
    expect(actingChairMemberId(first, SECENEKLER)).toBe(11);

    const second = withActingChair(first, SECENEKLER, 12);
    expect(second.filter((r) => r.is_chair).map((r) => r.person_name)).toEqual(["Ilgaz Şahin"]);
    expect(second.find((r) => r.is_chair)?.member_user_id).toBe(72);
    expect(second).toHaveLength(3);
    expect(actingChairMemberId(second, SECENEKLER)).toBe(12);
  });

  it("aday olmayan kişi başkan işaretliyse başkanlık eden bulunmaz", () => {
    const rows = [
      toRow({ attendee_role: "VOTING_MEMBER", person_name: "Hasan Velioğlu", is_chair: true }),
    ];
    expect(actingChairMemberId(rows, SECENEKLER)).toBeNull();
    expect(withActingChair(rows, SECENEKLER, null).some((r) => r.is_chair)).toBe(false);
  });

  it("withChairRestored kurul başkanını tek başkan satırı olarak geri koyar", () => {
    const rows = withChairRestored(withActingChair(satirlar(), SECENEKLER, 11), SECENEKLER);
    expect(rows[0]).toMatchObject({
      person_name: "Işıl Çağrı",
      is_chair: true,
      member_user_id: 70,
      attendee_role: "VOTING_MEMBER",
    });
    expect(rows.filter((r) => r.is_chair)).toHaveLength(1);
  });
});
