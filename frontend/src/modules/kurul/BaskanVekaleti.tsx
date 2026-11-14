// VEKÂLET KAYDI (kullanıcı kararı, 14.11.2026 — S7): Ödül ve Disiplin Kurulu toplantısında
// "Başkan toplantıya katılmadı" kutusu + "Başkanlık eden" seçimi. ToplantiForm (yeni
// tutanak) ve ToplantiDetay (katılımcı düzeltme) ortak kullanır.
//
// Dayanak: md. 188 — "Başkan bulunmadığında müdürün görevlendireceği öğretmen üyelerden
// biri kurula başkanlık eder. Üyenin başkanlık yaptığı durumlarda yedek üye toplantıya
// katılır."; md. 191/2 — şikâyetçi / zarar gören üye (başkan dahil) kurula katılamaz.
// Başkanlık edebilecekler backend'den gelir (`eligible`: kurulun asıl öğretmen üyeleri);
// katılımcı satırları burada yalnız ona göre düzenlenir, kural backend'de de denetlenir.
// Onur Kurulunda (md. 182) kullanılmaz.

import { useId } from "react";

import Card from "../../ui/Card";
import Icon from "../../ui/Icon";
import Select from "../../ui/Select";
import type { ActingChairOptions } from "./api";
import { toRow } from "./KatilimciEditor";
import type { AttendeeRow } from "./KatilimciEditor";

/** Ad karşılaştırma anahtarı (yalnız eşleştirme): boşluk ve Türkçe büyük/küçük harfe duyarsız. */
function nameKey(name: string): string {
  return name.trim().split(/\s+/).join(" ").toLocaleUpperCase("tr");
}

function isPerson(row: AttendeeRow, userId: number | null, name: string): boolean {
  if (row.member_user_id != null && userId != null) return row.member_user_id === userId;
  return nameKey(row.person_name) === nameKey(name);
}

/** Kurul başkanını katılımcı satırlarından çıkarır (başkan katılmadı). */
export function withoutChair(rows: AttendeeRow[], options: ActingChairOptions): AttendeeRow[] {
  return rows
    .filter((r) => !isPerson(r, options.chair, options.chair_name))
    .map((r) => ({ ...r, is_chair: false }));
}

/** Seçilen öğretmen üyeyi başkanlık eden (tek başkan satırı) yapar; listede yoksa ekler. */
export function withActingChair(
  rows: AttendeeRow[],
  options: ActingChairOptions,
  memberId: number | null,
): AttendeeRow[] {
  const cleared = withoutChair(rows, options);
  const candidate = options.eligible.find((c) => c.member_id === memberId);
  if (!candidate) return cleared;
  const found = cleared.some((r) => isPerson(r, candidate.member_user, candidate.member_name));
  const base = found
    ? cleared
    : [
        toRow({
          attendee_role: "VOTING_MEMBER",
          person_name: candidate.member_name,
          title: candidate.title || "Öğretmen",
          is_chair: false,
          member_user_id: candidate.member_user,
          member_student_id: null,
        }),
        ...cleared,
      ];
  return base.map((r) =>
    isPerson(r, candidate.member_user, candidate.member_name)
      ? { ...r, attendee_role: "VOTING_MEMBER", is_chair: true }
      : r,
  );
}

/** Vekâlet kaldırılınca kurul başkanını başkan satırı olarak geri koyar. */
export function withChairRestored(rows: AttendeeRow[], options: ActingChairOptions): AttendeeRow[] {
  return [
    toRow({
      attendee_role: "VOTING_MEMBER",
      person_name: options.chair_name,
      title: "Kurul Başkanı (Müdür Yardımcısı)",
      is_chair: true,
      member_user_id: options.chair,
      member_student_id: null,
    }),
    ...withoutChair(rows, options),
  ];
}

/** Satırlardaki başkanlık eden üyenin (aday listesindeki) kurul üyesi id'si; yoksa null. */
export function actingChairMemberId(
  rows: AttendeeRow[],
  options: ActingChairOptions,
): number | null {
  const chairRow = rows.find((r) => r.is_chair);
  if (!chairRow) return null;
  const candidate = options.eligible.find((c) => isPerson(chairRow, c.member_user, c.member_name));
  return candidate ? candidate.member_id : null;
}

interface Props {
  options: ActingChairOptions;
  chairAbsent: boolean;
  onChairAbsentChange: (absent: boolean) => void;
  rows: AttendeeRow[];
  onRowsChange: (rows: AttendeeRow[]) => void;
  /**
   * Mevcut (kayıtlı) tutanağın düzeltilmesi. Başkan dosyada şikâyetçi / zarar gören olsa da
   * kutu ZORLANMAZ (14.11.2026): eski kayıt kendiliğinden vekâlete çevrilmez, kullanıcı başka
   * bir satırı düzeltebilir; yalnız bilgi notu gösterilir. Zorlama yalnız YENİ kayıttadır.
   */
  existingRecord?: boolean;
}

export default function BaskanVekaleti({
  options,
  chairAbsent,
  onChairAbsentChange,
  rows,
  onRowsChange,
  existingRecord = false,
}: Props) {
  // Başkan seçilen dosyada şikâyetçi / zarar gören ise YENİ kayıtta kutu zorunludur
  // (md. 191/2). Kayıtlı tutanak düzeltilirken zorlanmaz (§7.6 — tek yönlü kapan olmasın).
  const forced = options.chair_conflicted && !existingRecord;
  const legacyNote = options.chair_conflicted && existingRecord && !chairAbsent;
  const reasonId = useId();
  const selected = chairAbsent ? actingChairMemberId(rows, options) : null;
  // Geçmiş toplantının düzeltilmesinde kayıtlı başkanlık eden artık aday olmayabilir (kuruldan
  // çıkarılmış üye): satır korunur ve seçim kutusunda adıyla gösterilir — "Seçin…" değil.
  // Kayıt denetimi backend'dedir (başkanlık eden satırı aynı kaldıkça düzeltme engellenmez).
  const recorded = chairAbsent && selected === null ? rows.find((r) => r.is_chair) : undefined;

  const toggle = (absent: boolean) => {
    onChairAbsentChange(absent);
    onRowsChange(absent ? withoutChair(rows, options) : withChairRestored(rows, options));
  };

  return (
    <Card elevation={0} className="space-y-2 bg-surface-container-low p-4">
      <label className="flex min-h-12 items-center gap-3 text-body-medium text-on-surface">
        <input
          type="checkbox"
          checked={chairAbsent}
          disabled={forced}
          aria-describedby={forced ? reasonId : undefined}
          onChange={(e) => toggle(e.target.checked)}
          className="size-5 accent-primary"
        />
        <span>Başkan toplantıya katılmadı ({options.chair_name})</span>
      </label>
      {forced && (
        <p id={reasonId} className="flex items-start gap-1 text-body-small text-on-surface-variant">
          <Icon name="info" size="sm" />
          <span>
            Kurul başkanı seçilen dosyada şikâyetçi/zarar gören kişi olduğundan kurula katılamaz
            (md. 191/2); toplantıya öğretmen üyelerden biri başkanlık eder (md. 188).
          </span>
        </p>
      )}
      {legacyNote && (
        <p className="flex items-start gap-1 text-body-small text-on-surface-variant">
          <Icon name="info" size="sm" />
          <span>
            Kurul başkanı bu tutanağın dosyasında şikâyetçi/zarar gören kişi (md. 191/2), ama
            tutanak başkan katılmış olarak kayıtlı. Bu kayıt kendiliğinden değiştirilmez: diğer
            satırları düzeltip kaydedebilirsiniz. Başkan toplantıya katılmadıysa kutuyu işaretleyip
            kurula başkanlık eden öğretmen üyeyi seçin (md. 188).
          </span>
        </p>
      )}
      {chairAbsent &&
        (options.eligible.length === 0 ? (
          <p className="flex items-start gap-1 text-body-small text-error">
            <Icon name="error" size="sm" />
            <span>
              Kurulda bu toplantıya başkanlık edebilecek asıl öğretmen üye yok (md. 188, 191/2).
              Asıl öğretmen üyeliği boşalmışsa bu üyelik sıraya göre yedek üyeyle doldurulur (md.
              186); asıl ve yedek üyelikler boşaldığı için kurul kurulamıyorsa açık üyelikler için
              yeniden seçim yapılır (md. 187). Kurul kaydı Üyeler sekmesinden bu duruma getirilmeden
              toplantı vekâletle kaydedilemez.
            </span>
          </p>
        ) : (
          <Select
            label="Başkanlık eden öğretmen üye (md. 188)"
            value={selected === null ? "" : String(selected)}
            onChange={(e) =>
              onRowsChange(
                withActingChair(rows, options, e.target.value ? Number(e.target.value) : null),
              )
            }
            options={[
              {
                value: "",
                label: recorded?.person_name.trim()
                  ? `${recorded.person_name.trim()} (kayıtlı)`
                  : "Seçin…",
              },
              ...options.eligible.map((c) => ({
                value: String(c.member_id),
                label: c.member_name,
              })),
            ]}
            helperText="Müdürün görevlendirdiği asıl öğretmen üye. Başkan katılımcı listesinde yer almaz ve yeter sayıya girmez; başkanın yerine çağrılan yedek üyeyi katılımcı olarak ekleyin."
          />
        ))}
    </Card>
  );
}
