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

import { useCallback, useEffect, useId, useState } from "react";

import { ApiError } from "../../lib/api";
import { saveBlob } from "../../lib/download";
import { formatDate } from "../../lib/format";
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
import type { AgendaItem, CouncilMeeting, DecisionBasis } from "./api";
import KatilimciEditor, { attendeeToRow, rowsToAttendees, validateRows } from "./KatilimciEditor";
import type { AttendeeRow } from "./KatilimciEditor";
import Textarea from "./Textarea";

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

  const saveAttendees = async () => {
    if (editingAttendees === null) return;
    const rowError = validateRows(editingAttendees);
    if (rowError) {
      setError(rowError);
      return;
    }
    const ok = await run(
      () => kurulApi.updateMeeting(meeting.id, { attendees: rowsToAttendees(editingAttendees) }),
      "Katılımcılar güncellendi.",
    );
    if (ok) setEditingAttendees(null);
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
          <p
            className={`text-body-medium ${
              quorum.ok ? "text-on-surface-variant" : "text-on-error-container"
            }`}
          >
            Yeter sayı (md. 191/1): kurul {quorum.full} kişi, en az {quorum.required} oy hakkı olan
            üye gerekir; bu toplantıda {quorum.present}.
            {quorum.ok
              ? " Toplantı yeter sayısı sağlanmış."
              : " Yeter sayı yok — katılımcıları tamamlamadan karar verilemez."}
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
            <Button
              variant="text"
              icon="edit"
              onClick={() => setEditingAttendees(meeting.attendees.map(attendeeToRow))}
            >
              Katılımcıları düzenle
            </Button>
          )}
        </div>
        {editingAttendees !== null ? (
          <div className="space-y-3">
            <KatilimciEditor
              rows={editingAttendees}
              onChange={setEditingAttendees}
              idBase={idBase}
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
            {meeting.attendees.map((a) => (
              <li key={a.id ?? a.person_name} className="text-body-medium text-on-surface">
                {a.person_name}
                {a.is_chair && <strong> (Başkan)</strong>}
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
  onDecide,
  onRemove,
}: {
  index: number;
  item: AgendaItem;
  meeting: CouncilMeeting;
  busy: boolean;
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
                  disabled={busy}
                >
                  {actions.unfavorable}
                </Button>
                <Button icon="gavel" onClick={() => void decide("FAVORABLE")} disabled={busy}>
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
