// Kurul toplantısı ekranı (04.10.2026, kurul işleyişi Aşama 1): kurul toplanır →
// gündemdeki teklifler madde madde karara bağlanır → karar defteri ve çizelge
// toplantıdan üretilir. Kurul kararı (uygun görüş / kabul / ret) yalnız burada verilir.
//
// - Onur Kurulu: "Uygun gör" / "Uygun görme" (md. 183/b) → teklif çizelgesi Ödül ve
//   Disiplin Kuruluna sunulur.
// - Ödül ve Disiplin Kurulu: "Kabul et" / "Reddet" (md. 161/1); yeter sayı (md. 191/1)
//   yoksa backend kararı reddeder, burada da uyarılır → karar çizelgesi müdüre sunulur.
// Olumsuz kararda gerekçe zorunlu (md. 196/1, 206/2); oy birliği/çoğunluğu ve karşı görüş
// madde başınadır (md. 196/2). Karara bağlanan madde, teklifin son adımı geri alınınca
// (Onur Kurulu → Teklifler) yeniden karar bekler.
// Saha bulguları 13/76: tarihi gelmemiş toplantıda karar verilemez (toplantı ileri tarihe
// planlanabilir); yanlış girilen toplantı tarihi, karara bağlı madde yokken düzeltilebilir.

import { useCallback, useEffect, useId, useState } from "react";

import { ApiError } from "../../lib/api";
import { saveBlob } from "../../lib/download";
import { formatDate, todayIso } from "../../lib/format";
import Button from "../../ui/Button";
import Card from "../../ui/Card";
import Icon from "../../ui/Icon";
import Select from "../../ui/Select";
import { SkeletonList } from "../../ui/Skeleton";
import { useSnackbar } from "../../ui/SnackbarProvider";
import TextField from "../../ui/TextField";
import { criteriaDisplay, odulApi, type HonorCertificate } from "../odul/api";
import {
  ATTENDEE_ROLE_TR,
  COUNCIL_TYPE_TR,
  DECISION_BASIS_TR,
  OUTCOME_ACTION_TR,
  kurulApi,
} from "./api";
import type { ActingChairOptions, AgendaItem, CouncilMeeting, DecisionBasis } from "./api";
import BaskanVekaleti from "./BaskanVekaleti";
import BilesimUyarisi from "./BilesimUyarisi";
import KatilimciEditor, { attendeeToRow, rowsToAttendees, validateRows } from "./KatilimciEditor";
import type { AttendeeRow } from "./KatilimciEditor";
import Textarea from "./Textarea";
import VekaletUyarisi from "./VekaletUyarisi";

interface Props {
  meetingId: number;
  onBack: () => void;
}

const OUTCOME_CHIP: Record<AgendaItem["outcome"], string> = {
  PENDING: "bg-secondary-container text-on-secondary-container",
  FAVORABLE: "bg-primary-container text-on-primary-container",
  UNFAVORABLE: "bg-error-container text-on-error-container",
};

export default function ToplantiDetay({ meetingId, onBack }: Props) {
  const snackbar = useSnackbar();
  const idBase = useId();
  const [meeting, setMeeting] = useState<CouncilMeeting | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [editingAttendees, setEditingAttendees] = useState<AttendeeRow[] | null>(null);
  const [candidates, setCandidates] = useState<HonorCertificate[] | null>(null);
  const [selected, setSelected] = useState<number[]>([]);
  const [editingDate, setEditingDate] = useState<string | null>(null);
  // VEKÂLET KAYDI (S7): katılımcı düzeltmesinde "Başkan toplantıya katılmadı" kutusu.
  const [chairOptions, setChairOptions] = useState<ActingChairOptions | null>(null);
  const [editingChairAbsent, setEditingChairAbsent] = useState(false);
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    kurulApi
      .getMeeting(meetingId)
      .then((data) => {
        setMeeting(data);
        setError(null);
      })
      .catch((e: unknown) => setError(e instanceof ApiError ? e.message : "Toplantı yüklenemedi."));
  }, [meetingId]);

  useEffect(load, [load]);

  if (meeting === null) {
    return error ? <ErrorBanner message={error} /> : <SkeletonList rows={4} />;
  }

  const councilType = meeting.council_type;
  const isDiscipline = councilType === "DISCIPLINE";
  // Teklif yalnız Onur Kurulu (aylık) ve Ödül ve Disiplin Kurulu genel toplantısında görüşülür.
  const acceptsProposals = isDiscipline
    ? meeting.minutes_type === "GENERAL"
    : meeting.honor_meeting_kind !== "GENERAL_ASSEMBLY";
  const items = meeting.agenda_items ?? [];
  const favorableCount = items.filter((item) => item.outcome === "FAVORABLE").length;
  const quorum = meeting.quorum;
  const unmatched = quorum?.unmatched ?? [];
  const chairSkipped = quorum?.chair_skipped ?? [];
  // Karar tarihi = toplantı tarihi: yapılmamış toplantının kararı yazılamaz (backend de reddeder).
  const notHeldYet = meeting.meeting_date > todayIso();
  // Karara bağlı maddesi olan toplantının tarihi değişmez (önce karar geri alınır).
  const dateEditable = items.every((item) => item.outcome === "PENDING");

  const run = async (action: () => Promise<CouncilMeeting | void>, success: string) => {
    setBusy(true);
    setError(null);
    try {
      const updated = await action();
      if (updated) setMeeting(updated);
      snackbar.success(success);
      return true;
    } catch (e: unknown) {
      setError(e instanceof ApiError ? e.message : "İşlem kaydedilemedi.");
      return false;
    } finally {
      setBusy(false);
    }
  };

  const openCandidates = async () => {
    try {
      setCandidates(await kurulApi.agendaCandidates(councilType));
      setSelected([]);
    } catch (e: unknown) {
      setError(e instanceof ApiError ? e.message : "Teklifler yüklenemedi.");
    }
  };

  const addSelected = async () => {
    if (selected.length === 0) return;
    const ok = await run(
      () => kurulApi.addAgendaItems(meeting.id, selected),
      "Teklifler gündeme alındı.",
    );
    if (ok) setCandidates(null);
  };

  const startAttendeeEdit = async () => {
    setEditingAttendees(meeting.attendees.map(attendeeToRow));
    setEditingChairAbsent(meeting.chair_absent);
    setChairOptions(null);
    if (!isDiscipline) return;
    try {
      // Kayıtlı tutanak düzeltiliyor: başkan görüşülen dosyada şikâyetçi / zarar gören olsa da
      // (md. 191/2) vekâlet ZORLANMAZ ve başkan satırı silinmez (14.11.2026) — S7 öncesi
      // kayıt kendiliğinden değiştirilmez, kullanıcı başka bir satırı düzeltebilir; uygun
      // öğretmen üye yoksa da kayıt kilitlenmez (§7.6). Durum kalıcı uyarıyla
      // (`chair_warnings`) ve kutunun altındaki notla gösterilir. Zorlama yalnız yeni
      // tutanakta (ToplantiForm) ve backend'in yeni kayıt denetimindedir.
      setChairOptions(await kurulApi.actingChairOptions(meeting.discipline_case));
    } catch {
      // Bilgilendirme amaçlı; alınamazsa kayıt denetimi backend tarafında kalır.
    }
  };

  const saveAttendees = async () => {
    if (editingAttendees === null) return;
    const vekalet = isDiscipline && chairOptions !== null;
    // Başkanlık eden satırı hiç yoksa burada durdurulur. Satır var ama aday listesinde
    // değilse (kayıtlı başkanlık eden sonradan kuruldan çıkarılmış) karar backend'indir:
    // satır aynı kaldıkça düzeltme engellenmez (§7.6), değiştiyse md. 188 denetlenir.
    if (vekalet && editingChairAbsent && !editingAttendees.some((r) => r.is_chair)) {
      setError(
        "Başkan toplantıya katılmadıysa kurula başkanlık eden öğretmen üyeyi seçin (md. 188).",
      );
      return;
    }
    const rowError = validateRows(editingAttendees, councilType);
    if (rowError) {
      setError(rowError);
      return;
    }
    const ok = await run(
      () =>
        kurulApi.updateMeeting(meeting.id, {
          attendees: rowsToAttendees(editingAttendees),
          ...(vekalet ? { chair_absent: editingChairAbsent } : {}),
        }),
      "Katılımcılar güncellendi.",
    );
    if (ok) setEditingAttendees(null);
  };

  const saveDate = async () => {
    if (!editingDate) return;
    const ok = await run(
      () => kurulApi.updateMeeting(meeting.id, { meeting_date: editingDate }),
      "Toplantı tarihi güncellendi.",
    );
    if (ok) setEditingDate(null);
  };

  const download = async (kind: "minutes" | "chart") => {
    try {
      if (kind === "minutes") {
        saveBlob(
          await kurulApi.minutes(meeting.id),
          `kurul-toplanti-tutanagi-${meeting.meeting_no_display}.pdf`,
        );
      } else if (isDiscipline) {
        saveBlob(
          await odulApi.awardRecord(meeting.id),
          `odul-disiplin-kurulu-onur-karari-${meeting.meeting_no_display}.pdf`,
        );
      } else {
        saveBlob(
          await odulApi.recommendationRecord(meeting.id),
          `onur-kurulu-teklif-cizelgesi-${meeting.meeting_no_display}.pdf`,
        );
      }
    } catch (e: unknown) {
      setError(e instanceof ApiError ? e.message : "Belge üretilemedi.");
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <Button variant="text" icon="arrow_back" onClick={onBack}>
            Toplantılar
          </Button>
          <h2 className="mt-2 text-title-large text-on-surface">
            {COUNCIL_TYPE_TR[councilType]} — Toplantı {meeting.meeting_no_display}
          </h2>
          <p className="text-body-medium text-on-surface-variant">
            {formatDate(meeting.meeting_date)}
            {meeting.term_name ? ` · ${meeting.term_name}` : ""}
            {meeting.honor_meeting_kind === "GENERAL_ASSEMBLY" ? " · Onur Genel Kurulu" : ""}
          </p>
          {dateEditable &&
            (editingDate === null ? (
              <Button
                variant="text"
                icon="edit"
                onClick={() => setEditingDate(meeting.meeting_date)}
              >
                Tarihi düzelt
              </Button>
            ) : (
              <div className="mt-2 flex flex-wrap items-end gap-2">
                <TextField
                  label="Toplantı tarihi"
                  type="date"
                  value={editingDate}
                  onChange={(e) => setEditingDate(e.target.value)}
                />
                <Button variant="text" onClick={() => setEditingDate(null)} disabled={busy}>
                  Vazgeç
                </Button>
                <Button icon="save" onClick={() => void saveDate()} disabled={busy || !editingDate}>
                  Tarihi kaydet
                </Button>
              </div>
            ))}
        </div>
        <div className="flex flex-wrap gap-2">
          <Button variant="outlined" icon="picture_as_pdf" onClick={() => void download("minutes")}>
            Karar defteri sayfası
          </Button>
          {favorableCount > 0 && (
            <Button variant="outlined" icon="table_view" onClick={() => void download("chart")}>
              {isDiscipline ? "Karar çizelgesi (müdüre)" : "Teklif çizelgesi (kurula)"}
            </Button>
          )}
        </div>
      </div>

      {quorum && (
        <Card
          elevation={0}
          className={`flex items-start gap-3 p-4 ${
            quorum.ok ? "bg-surface-container-low" : "bg-error-container"
          }`}
        >
          <Icon
            name={quorum.ok ? "how_to_vote" : "warning"}
            className={`shrink-0 ${quorum.ok ? "text-primary" : "text-on-error-container"}`}
          />
          <div
            className={`space-y-2 text-body-medium ${
              quorum.ok ? "text-on-surface-variant" : "text-on-error-container"
            }`}
          >
            <p>
              Yeter sayı (md. 191/1): kurul {quorum.full} kişi, en az {quorum.required} oy hakkı
              olan üye gerekir; bu toplantıda {quorum.present}.
              {quorum.ok
                ? " Toplantı yeter sayısı sağlanmış."
                : " Yeter sayı yok — katılımcıları tamamlamadan karar verilemez."}
            </p>
            {/* Kullanıcı kararı, 14.11.2026 — S13: sayılmayan satırlar adı ve nedeniyle
                listelenir (md. 191/1: üye dışı çağrılanlar oy kullanamaz). Yoksa kart aynıdır. */}
            {(unmatched.length > 0 || chairSkipped.length > 0) && (
              <div>
                <p>Yeter sayıya girmeyen oy hakkı satırları:</p>
                <ul className="list-inside list-disc">
                  {unmatched.map((name, index) => (
                    <li key={`${name}-${index}`}>
                      {name} kurul üyesi olarak kayıtlı değil; yeter sayıya katılmadı.
                    </li>
                  ))}
                  {/* S7 (14.11.2026): "başkan katılmadı" kayıtlı toplantıda bugünkü başkanla
                      eşleşen satır sessizce düşmez — nedeni yazılır. */}
                  {chairSkipped.map((name, index) => (
                    <li key={`baskan-${name}-${index}`}>
                      {name} bugün kurul başkanı olarak kayıtlı; bu toplantı “başkan katılmadı”
                      kayıtlı olduğundan yeter sayıya katılmadı (başkan değişikliğinin geçmişi
                      tutulmaz). Bu satır yüzünden katılımcı düzeltmesi engellenmez.
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        </Card>
      )}

      {/* Kullanıcı kararı, 14.11.2026 — S5: md. 185/1 bileşimi uyarılır, engellenmez. */}
      <BilesimUyarisi warnings={meeting.composition_warnings} />
      {/* S7: yedek üye çağrılmamış / dosya toplantısı kaydıyla çelişki — uyarır, engellemez. */}
      <VekaletUyarisi warnings={meeting.chair_warnings} />

      {notHeldYet && (
        <Card elevation={0} className="flex items-start gap-3 bg-surface-container-low p-4">
          <Icon name="schedule" className="shrink-0 text-primary" />
          <p className="text-body-medium text-on-surface-variant">
            Toplantı tarihi henüz gelmedi ({formatDate(meeting.meeting_date)}). Gündem
            hazırlanabilir; kararlar toplantı günü geldiğinde girilir. Toplantı yapıldıysa önce
            tarihi düzeltin.
          </p>
        </Card>
      )}

      {error && <ErrorBanner message={error} />}

      <section className="space-y-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h3 className="text-title-medium text-on-surface">Gündem maddeleri ({items.length})</h3>
          {acceptsProposals && candidates === null && (
            <Button variant="text" icon="playlist_add" onClick={() => void openCandidates()}>
              Gündeme teklif ekle
            </Button>
          )}
        </div>

        {candidates !== null && (
          <Card elevation={0} className="space-y-3 bg-surface-container-low p-4">
            {candidates.length === 0 ? (
              <p className="text-body-medium text-on-surface-variant">
                Gündeme alınmayı bekleyen teklif yok.
              </p>
            ) : (
              <ul className="space-y-2">
                {candidates.map((c) => (
                  <li key={c.id}>
                    <label className="flex items-start gap-3 text-body-medium text-on-surface">
                      <input
                        type="checkbox"
                        className="mt-1 size-5 accent-primary"
                        checked={selected.includes(c.id)}
                        onChange={(e) =>
                          setSelected((prev) =>
                            e.target.checked ? [...prev, c.id] : prev.filter((x) => x !== c.id),
                          )
                        }
                      />
                      <span>
                        {c.student_name}
                        <span className="block text-body-small text-on-surface-variant">
                          {criteriaDisplay(c.criteria).join(" · ")}
                        </span>
                      </span>
                    </label>
                  </li>
                ))}
              </ul>
            )}
            <div className="flex justify-end gap-2">
              <Button variant="text" onClick={() => setCandidates(null)}>
                Vazgeç
              </Button>
              <Button
                icon="add"
                onClick={() => void addSelected()}
                disabled={busy || selected.length === 0}
              >
                Gündeme al
              </Button>
            </div>
          </Card>
        )}

        {items.length === 0 ? (
          <p className="text-body-medium text-on-surface-variant">
            {acceptsProposals
              ? "Bu toplantının gündeminde onur belgesi teklifi yok."
              : "Bu toplantı türünde onur belgesi teklifi görüşülmez."}
          </p>
        ) : (
          <ol className="space-y-3">
            {items.map((item, index) => (
              <AgendaItemCard
                key={item.id}
                index={index + 1}
                item={item}
                meeting={meeting}
                busy={busy}
                decisionLocked={notHeldYet}
                onDecide={(body) =>
                  run(
                    () => kurulApi.decideAgendaItem(meeting.id, item.id, body),
                    "Karar kaydedildi.",
                  )
                }
                onRemove={() =>
                  run(
                    () => kurulApi.removeAgendaItem(meeting.id, item.id),
                    "Madde gündemden çıkarıldı.",
                  )
                }
              />
            ))}
          </ol>
        )}
      </section>

      {(meeting.agenda || meeting.decision_text) && (
        <section className="space-y-2">
          <h3 className="text-title-medium text-on-surface">Diğer gündem ve kararlar</h3>
          {meeting.agenda && (
            <p className="whitespace-pre-line text-body-medium text-on-surface-variant">
              {meeting.agenda}
            </p>
          )}
          {meeting.decision_text && (
            <p className="whitespace-pre-line text-body-medium text-on-surface">
              {meeting.decision_text}
            </p>
          )}
        </section>
      )}

      <section className="space-y-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h3 className="text-title-medium text-on-surface">
            Katılanlar ({meeting.attendees.length})
          </h3>
          {editingAttendees === null && (
            <Button variant="text" icon="edit" onClick={() => void startAttendeeEdit()}>
              Katılımcıları düzenle
            </Button>
          )}
        </div>
        {editingAttendees !== null ? (
          <div className="space-y-3">
            {isDiscipline && chairOptions !== null && (
              <BaskanVekaleti
                options={chairOptions}
                chairAbsent={editingChairAbsent}
                onChairAbsentChange={setEditingChairAbsent}
                rows={editingAttendees}
                onRowsChange={setEditingAttendees}
                existingRecord
                caseReview={meeting.discipline_case !== null}
              />
            )}
            <KatilimciEditor
              rows={editingAttendees}
              onChange={setEditingAttendees}
              idBase={idBase}
              councilType={councilType}
              chairLocked={isDiscipline && chairOptions !== null && editingChairAbsent}
            />
            <div className="flex justify-end gap-2">
              <Button variant="text" onClick={() => setEditingAttendees(null)} disabled={busy}>
                Vazgeç
              </Button>
              <Button icon="save" onClick={() => void saveAttendees()} disabled={busy}>
                Katılımcıları kaydet
              </Button>
            </div>
          </div>
        ) : (
          <ul className="space-y-1">
            {/* VEKÂLET KAYDI (S7, 14.11.2026): yalnız başkanın katılmadığı toplantıda. */}
            {meeting.chair_absent && (
              <li className="flex items-start gap-1 text-body-medium text-on-surface-variant">
                <Icon name="info" size="sm" />
                <span>
                  {/* K5 (15.11.2026): o günkü başkanın adı kayıttan; eski kayıtta boştur. */}
                  Başkan{meeting.absent_chair_name ? ` (${meeting.absent_chair_name})` : ""}{" "}
                  katılmadı;{" "}
                  {meeting.attendees.find((a) => a.is_chair)?.person_name ?? "öğretmen üye"}{" "}
                  başkanlık etti (md. 188).
                </span>
              </li>
            )}
            {meeting.attendees.map((a) => (
              <li key={a.id ?? a.person_name} className="text-body-medium text-on-surface">
                {a.person_name}
                {a.is_chair && (
                  <strong>{meeting.chair_absent ? " (Başkanlık eden)" : " (Başkan)"}</strong>
                )}
                <span className="text-on-surface-variant">
                  {" "}
                  — {a.title || ATTENDEE_ROLE_TR[a.attendee_role]}
                  {a.attendee_role === "NON_VOTING_INVITEE" ? " · oy hakkı yok" : ""}
                </span>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}

function AgendaItemCard({
  index,
  item,
  meeting,
  busy,
  decisionLocked,
  onDecide,
  onRemove,
}: {
  index: number;
  item: AgendaItem;
  meeting: CouncilMeeting;
  busy: boolean;
  /** Toplantı tarihi gelmediyse karar düğmeleri kapalıdır. */
  decisionLocked: boolean;
  onDecide: (body: {
    outcome: "FAVORABLE" | "UNFAVORABLE";
    decision_text: string;
    decision_basis: DecisionBasis;
    dissent_note: string;
  }) => Promise<boolean>;
  onRemove: () => Promise<boolean>;
}) {
  const idBase = useId();
  const [reason, setReason] = useState("");
  const [basis, setBasis] = useState<DecisionBasis>(meeting.decision_basis);
  const [dissent, setDissent] = useState("");
  const [localError, setLocalError] = useState<string | null>(null);
  const actions = OUTCOME_ACTION_TR[meeting.council_type];
  const pending = item.outcome === "PENDING";

  const decide = async (outcome: "FAVORABLE" | "UNFAVORABLE") => {
    if (outcome === "UNFAVORABLE" && !reason.trim()) {
      setLocalError("Olumsuz kararda gerekçe zorunludur (md. 196/1, 206/2).");
      return;
    }
    setLocalError(null);
    await onDecide({
      outcome,
      decision_text: reason.trim(),
      decision_basis: basis,
      dissent_note: dissent.trim(),
    });
  };

  return (
    <li>
      <Card elevation={1} className="space-y-3 p-5">
        <div className="flex flex-wrap items-start justify-between gap-2">
          <div>
            <p className="text-title-small text-on-surface">
              {index}. {item.student_name}
              {item.class_label && (
                <span className="text-on-surface-variant"> ({item.class_label})</span>
              )}
            </p>
            <p className="text-body-small text-on-surface-variant">
              Onur belgesi teklifi · {criteriaDisplay(item.criteria).join(" · ")}
            </p>
            {item.justification && (
              <p className="mt-1 text-body-small text-on-surface-variant">{item.justification}</p>
            )}
            {item.proposer_role_display && (
              <p className="mt-1 text-label-small text-on-surface-variant">
                Teklif eden: {item.proposer_role_display}
              </p>
            )}
          </div>
          <span
            className={`inline-flex items-center rounded-shape-xl px-2 py-0.5 text-label-small ${OUTCOME_CHIP[item.outcome]}`}
          >
            {item.outcome_display}
          </span>
        </div>

        {pending ? (
          <div className="space-y-3">
            {/* Kullanıcı kararı, 14.11.2026 — S6: Onur Kurulu karardan ÖNCE uyarılır,
                engellenmez (md. 183/b öneri yetkisi; uygunluk md. 161/1). */}
            {meeting.council_type === "HONOR" && item.honor_eligible === false && (
              <div
                role="status"
                className="flex items-start gap-2 rounded-shape-sm bg-tertiary-container px-4 py-3 text-body-small text-on-tertiary-container"
              >
                <Icon name="warning" size="sm" />
                <span>
                  Öğrencinin davranış puanı indirilmiş (md. 161/1); uygun görüş verilse de Ödül ve
                  Disiplin Kurulu kabulünde ve müdür onayında uygunluk yeniden denetlenir.
                </span>
              </div>
            )}
            <Textarea
              id={`${idBase}-reason`}
              label="Karar gerekçesi (olumsuz kararda zorunlu)"
              value={reason}
              onChange={(e) => setReason(e.target.value)}
            />
            <div className="grid gap-3 sm:grid-cols-2">
              <Select
                label="Karar esası"
                value={basis}
                onChange={(e) => setBasis(e.target.value as DecisionBasis)}
                options={(Object.keys(DECISION_BASIS_TR) as DecisionBasis[]).map((v) => ({
                  value: v,
                  label: DECISION_BASIS_TR[v],
                }))}
              />
              <TextField
                label="Karşı görüş (üye ve gerekçesi — varsa)"
                value={dissent}
                onChange={(e) => setDissent(e.target.value)}
              />
            </div>
            {localError && <ErrorBanner message={localError} />}
            <div className="flex flex-wrap justify-between gap-2">
              <Button
                variant="text"
                icon="playlist_remove"
                onClick={() => void onRemove()}
                disabled={busy}
              >
                Gündemden çıkar
              </Button>
              <div className="flex flex-wrap gap-2">
                <Button
                  variant="outlined"
                  icon="block"
                  onClick={() => void decide("UNFAVORABLE")}
                  disabled={busy || decisionLocked}
                >
                  {actions.unfavorable}
                </Button>
                <Button
                  icon="gavel"
                  onClick={() => void decide("FAVORABLE")}
                  disabled={busy || decisionLocked}
                >
                  {actions.favorable}
                </Button>
              </div>
            </div>
          </div>
        ) : (
          <div className="space-y-1 text-body-small text-on-surface-variant">
            {item.decision_text && <p>Gerekçe: {item.decision_text}</p>}
            <p>{DECISION_BASIS_TR[item.decision_basis]}</p>
            {item.dissent_note && <p>Karşı görüş: {item.dissent_note}</p>}
          </div>
        )}
      </Card>
    </li>
  );
}

function ErrorBanner({ message }: { message: string }) {
  return (
    <div className="flex items-start gap-2 rounded-shape-sm bg-error-container px-4 py-3 text-body-small text-on-error-container">
      <Icon name="error" size="sm" />
      <span>{message}</span>
    </div>
  );
}
