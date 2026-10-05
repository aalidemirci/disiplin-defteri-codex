// Kurul toplantısı katılımcı düzenleyicisi — ToplantiForm (yeni tutanak) ve ToplantiDetay
// (katılımcı düzeltme) ortak kullanır. Oy hakkı olan üye / oy hakkı olmayan davetli
// (md. 185/6), tek başkan (md. 188), karşı görüş (md. 206). ToplantiForm'dan ayrıldı
// (04.10.2026, kurul işleyişi Aşama 1); davranış aynen korunur.

import Button from "../../ui/Button";
import Card from "../../ui/Card";
import Select from "../../ui/Select";
import TextField from "../../ui/TextField";
import { ATTENDEE_ROLE_TR } from "./api";
import type { AttendeeInput, AttendeeRole, CouncilAttendee } from "./api";

// Form içi geçici katılımcı satırı (key yerel anahtar).
export interface AttendeeRow extends AttendeeInput {
  key: string;
}

let rowSeq = 0;
export function toRow(a: AttendeeInput): AttendeeRow {
  rowSeq += 1;
  return { key: `r${rowSeq}`, ...a, title: a.title ?? "", dissent_note: a.dissent_note ?? "" };
}

export function emptyRow(role: AttendeeRole = "VOTING_MEMBER"): AttendeeRow {
  return toRow({
    attendee_role: role,
    person_name: "",
    title: "",
    is_chair: false,
    dissent_note: "",
  });
}

/** Kayıtlı katılımcıyı düzenlenebilir satıra çevirir (FK'lar korunur). */
export function attendeeToRow(a: CouncilAttendee): AttendeeRow {
  return toRow({
    attendee_role: a.attendee_role,
    person_name: a.person_name,
    title: a.title,
    is_chair: a.is_chair,
    dissent_note: a.dissent_note,
    member_user_id: a.member_user ?? null,
    member_student_id: a.member_student ?? null,
  });
}

/** Satırları doğrular; hata metni ya da null döner (md. 188/191). */
export function validateRows(rows: AttendeeRow[]): string | null {
  const filled = rows.filter((r) => r.person_name.trim());
  if (filled.filter((r) => r.attendee_role === "VOTING_MEMBER").length === 0) {
    return "En az bir oy hakkı olan üye eklenmelidir (md. 191).";
  }
  if (filled.filter((r) => r.is_chair).length !== 1) {
    return "Tam olarak bir başkan işaretlenmelidir (md. 188).";
  }
  return null;
}

/** Dolu satırları backend katılımcı sözlüğüne çevirir. */
export function rowsToAttendees(rows: AttendeeRow[]): AttendeeInput[] {
  return rows
    .filter((r) => r.person_name.trim())
    .map((r, i) => ({
      attendee_role: r.attendee_role,
      person_name: r.person_name.trim(),
      title: (r.title ?? "").trim(),
      is_chair: !!r.is_chair,
      dissent_note: (r.dissent_note ?? "").trim(),
      order: i,
      member_user_id: r.member_user_id ?? null,
      member_student_id: r.member_student_id ?? null,
    }));
}

interface Props {
  rows: AttendeeRow[];
  onChange: (rows: AttendeeRow[]) => void;
  idBase: string;
}

export default function KatilimciEditor({ rows, onChange, idBase }: Props) {
  const updateRow = (key: string, patch: Partial<AttendeeRow>) => {
    onChange(rows.map((r) => (r.key === key ? { ...r, ...patch } : r)));
  };

  // Başkan tekildir: bir satır başkan işaretlenince diğerleri temizlenir (md. 188).
  const setChair = (key: string) => {
    onChange(rows.map((r) => ({ ...r, is_chair: r.key === key })));
  };

  return (
    <div className="space-y-3">
      {rows.map((r) => (
        <Card key={r.key} elevation={0} className="space-y-3 bg-surface-container-low p-4">
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <TextField
              label="Ad Soyad"
              value={r.person_name}
              onChange={(e) => updateRow(r.key, { person_name: e.target.value })}
            />
            <TextField
              label="Görev / Ünvan"
              value={r.title ?? ""}
              onChange={(e) => updateRow(r.key, { title: e.target.value })}
            />
          </div>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <Select
              label="Rol"
              value={r.attendee_role}
              onChange={(e) =>
                updateRow(r.key, {
                  attendee_role: e.target.value as AttendeeRole,
                  // Davetli başkan olamaz (md. 185/6).
                  is_chair: e.target.value === "VOTING_MEMBER" ? r.is_chair : false,
                })
              }
              options={(Object.keys(ATTENDEE_ROLE_TR) as AttendeeRole[]).map((v) => ({
                value: v,
                label: ATTENDEE_ROLE_TR[v],
              }))}
            />
            <label className="flex min-h-12 items-center gap-2 text-body-medium text-on-surface">
              <input
                type="radio"
                name={`${idBase}-chair`}
                checked={!!r.is_chair}
                disabled={r.attendee_role !== "VOTING_MEMBER"}
                onChange={() => setChair(r.key)}
                className="size-5 accent-primary"
              />
              Başkan (md. 188)
            </label>
          </div>
          {r.attendee_role === "VOTING_MEMBER" && (
            <TextField
              label="Karşı görüş gerekçesi (md. 206 — varsa)"
              value={r.dissent_note ?? ""}
              onChange={(e) => updateRow(r.key, { dissent_note: e.target.value })}
            />
          )}
          <div className="flex justify-end">
            <Button
              variant="text"
              icon="delete"
              onClick={() => onChange(rows.filter((x) => x.key !== r.key))}
              aria-label="Katılımcıyı kaldır"
            >
              Kaldır
            </Button>
          </div>
        </Card>
      ))}

      <Button variant="outlined" icon="add" onClick={() => onChange([...rows, emptyRow()])}>
        Katılımcı ekle
      </Button>
    </div>
  );
}
