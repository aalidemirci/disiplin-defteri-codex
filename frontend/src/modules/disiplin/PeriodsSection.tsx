// OYS frontend/src/modules/disiplin/PeriodsSection.tsx'ten UYARLANDI (F4-D2). Sapmalar:
// CaseStudent.student_id → id; ExtensionCreateBody'de approved_by_principal/approved_on
// yok (müdür onayı YALNIZ ayrı uçtan — satırdaki Form-13 paneli); auth yok, caps daima
// ALL_CAPABILITIES ile gelir (403-gizleme dalları zararsız OYS kalıntısı).
//
// Disiplin kurul karar süresi + uzatma (Form-12/13) ve tedbir/geçici uzaklaştırma
// (md. 175) UI. İki kart: (1) Kurul karar süresi — kurula geliş + 10 iş günü karar
// son günü izleme (md. 192/3), ancak bir kez uzatma (Form-12/13); (2) Tedbir — acele
// geçici uzaklaştırma (md. 175), ≤10 iş günü, işleme başlama 3 iş günü, iki kez daha
// uzatma, devamsızlıktan SAYILMAZ.

import { useCallback, useEffect, useId, useState } from "react";

import { ApiError } from "../../lib/api";
import { formatDate, todayIso } from "../../lib/format";
import Button from "../../ui/Button";
import { SkeletonList } from "../../ui/Skeleton";
import Card from "../../ui/Card";
import Icon from "../../ui/Icon";
import Select from "../../ui/Select";
import { useSnackbar } from "../../ui/SnackbarProvider";
import TextField from "../../ui/TextField";
import { disiplinApi } from "./api";
import type {
  CaseStudent,
  DisciplineCase,
  DisciplineDeadlineExtension,
  DisciplinePrecaution,
  ExtensionCreateBody,
  PrecautionCreateBody,
  PrecautionStatus,
} from "./api";
import { asMessage, FormError, PanelActions, PanelShell } from "./formHelpers";
import type { DisciplineCapabilities } from "./workflow";

function studentNames(caseObj: DisciplineCase): Record<number, string> {
  const map: Record<number, string> = {};
  for (const s of caseObj.students) map[s.id] = s.full_name;
  return map;
}

const PRECAUTION_STATUS_CHIP: Record<PrecautionStatus, string> = {
  ACTIVE: "bg-error-container text-on-error-container",
  LIFTED: "bg-secondary-container text-on-secondary-container",
  EXPIRED: "bg-surface-container-high text-on-surface-variant",
};

export default function PeriodsSection({
  caseObj,
  caps,
}: {
  caseObj: DisciplineCase;
  caps: DisciplineCapabilities;
}) {
  return (
    <>
      <ExtensionsCard caseObj={caseObj} caps={caps} />
      <PrecautionsCard caseObj={caseObj} caps={caps} />
    </>
  );
}

// ===========================================================================
// Kurul karar süresi + uzatma (md. 192/3)
// ===========================================================================

function ExtensionsCard({
  caseObj,
  caps,
}: {
  caseObj: DisciplineCase;
  caps: DisciplineCapabilities;
}) {
  // Süre ara kararı (F-12) kurul başkanına; müdür onayı (F-13) müdüre (md. 192/3).
  // ALL_CAPABILITIES ile ikisi de daima açık.
  const canCreate = caps.isChair || caps.isAdmin;
  const canApprove = caps.isMudur || caps.isAdmin;
  const [extensions, setExtensions] = useState<DisciplineDeadlineExtension[] | null>(null);
  const [referredOn, setReferredOn] = useState<string | null>(null);
  const [deadline, setDeadline] = useState<string | null>(null);
  const [hidden, setHidden] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [adding, setAdding] = useState(false);

  const load = useCallback(() => {
    disiplinApi
      .listExtensions(caseObj.id)
      .then((r) => {
        setExtensions(r.extensions);
        setReferredOn(r.committee_referred_on);
        setDeadline(r.committee_decision_deadline);
        setError(null);
      })
      .catch((e: unknown) => {
        if (e instanceof ApiError && e.status === 403) {
          setHidden(true);
          return;
        }
        setError(e instanceof ApiError ? e.message : "Süre bilgileri yüklenemedi.");
      });
  }, [caseObj.id]);
  useEffect(load, [load]);

  if (hidden) return null;

  const hasExtension = (extensions ?? []).length > 0;

  return (
    <Card elevation={1} className="p-6">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-title-medium text-on-surface">Kurul karar süresi</p>
        {canCreate && !adding && !hasExtension && referredOn && (
          <Button variant="tonal" icon="more_time" onClick={() => setAdding(true)}>
            Süre uzatması ekle
          </Button>
        )}
      </div>
      <p className="mt-1 text-body-small text-on-surface-variant">
        Kurul, dosyanın kurula gelişinden itibaren 10 iş günü içinde karar verir; ara kararla ancak
        bir kez uzatılabilir (md. 192/3 — Form-12/13).
      </p>

      {/* Kurula geliş + karar son günü izleme */}
      <div className="mt-3 flex flex-wrap gap-2 text-label-medium">
        {referredOn ? (
          <>
            <span className="inline-flex items-center gap-1.5 rounded-shape-xl bg-surface-container px-3 py-1 text-on-surface-variant">
              <Icon name="login" size="sm" className="text-primary" />
              Kurula geliş: <span className="text-on-surface">{formatDate(referredOn)}</span>
            </span>
            {deadline && (
              <span className="inline-flex items-center gap-1.5 rounded-shape-xl bg-surface-container px-3 py-1 text-on-surface-variant">
                <Icon name="event_available" size="sm" className="text-primary" />
                Karar son günü: <span className="text-on-surface">{formatDate(deadline)}</span>
                {hasExtension && " (uzatıldı)"}
              </span>
            )}
          </>
        ) : (
          <span className="inline-flex items-center gap-1.5 rounded-shape-xl bg-tertiary-container px-3 py-1 text-on-tertiary-container">
            <Icon name="info" size="sm" />
            Dosya henüz disiplin kuruluna sevk edilmedi.
          </span>
        )}
      </div>

      {hasExtension && (
        <p className="mt-3 text-body-small text-on-surface-variant">
          <Icon name="info" size="sm" className="mr-1 align-middle" />
          Kurul karar süresi yalnızca bir kez uzatılabilir (md. 192/3); ek uzatma kaydedilemez.
        </p>
      )}

      {adding && (
        <div className="mt-4">
          <AddExtensionForm
            caseId={caseObj.id}
            onCancel={() => setAdding(false)}
            onAdded={() => {
              setAdding(false);
              load();
            }}
          />
        </div>
      )}

      {error && (
        <div className="mt-3 flex items-start gap-2 rounded-shape-sm bg-error-container px-4 py-2 text-body-small text-on-error-container">
          <Icon name="error" size="sm" />
          <span>{error}</span>
        </div>
      )}

      {extensions === null ? (
        <SkeletonList rows={3} />
      ) : extensions.length === 0 ? (
        <p className="mt-3 text-body-medium text-on-surface-variant">Süre uzatması kaydedilmedi.</p>
      ) : (
        <ul className="mt-3 space-y-2">
          {extensions.map((x) => (
            <ExtensionRow
              key={x.id}
              caseId={caseObj.id}
              extension={x}
              canManage={canApprove}
              onChanged={load}
            />
          ))}
        </ul>
      )}
    </Card>
  );
}

function ExtensionRow({
  caseId,
  extension: x,
  canManage,
  onChanged,
}: {
  caseId: number;
  extension: DisciplineDeadlineExtension;
  canManage: boolean;
  onChanged: () => void;
}) {
  const [approving, setApproving] = useState(false);

  return (
    <li className="rounded-shape-md border border-outline-variant bg-surface-container-low p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-body-large text-on-surface">
          <Icon name="more_time" size="base" className="mr-1 align-middle text-primary" />+
          {x.requested_days} iş günü uzatma
        </p>
        <span
          className={`inline-flex items-center rounded-shape-xl px-2.5 py-0.5 text-label-small ${
            x.approved_by_principal
              ? "bg-secondary-container text-on-secondary-container"
              : "bg-tertiary-container text-on-tertiary-container"
          }`}
        >
          {x.approved_by_principal ? "Müdür onaylı" : "Onay bekliyor"}
        </span>
      </div>
      <p className="mt-1 text-label-small text-on-surface-variant">
        Ara karar: {formatDate(x.decided_on)}
        {x.original_deadline && ` · eski son gün: ${formatDate(x.original_deadline)}`}
        {x.new_deadline && ` · yeni son gün: ${formatDate(x.new_deadline)}`}
        {x.approved_on && ` · onay: ${formatDate(x.approved_on)}`}
      </p>
      {x.reason && (
        <p className="mt-1 whitespace-pre-wrap text-body-medium text-on-surface-variant">
          {x.reason}
        </p>
      )}

      {canManage && !x.approved_by_principal && !approving && (
        <div className="mt-2">
          <Button variant="text" icon="approval" onClick={() => setApproving(true)}>
            Müdür onayı (Form-13)
          </Button>
        </div>
      )}
      {approving && (
        <ApproveExtensionForm
          caseId={caseId}
          extension={x}
          onCancel={() => setApproving(false)}
          onDone={() => {
            setApproving(false);
            onChanged();
          }}
        />
      )}
    </li>
  );
}

function AddExtensionForm({
  caseId,
  onCancel,
  onAdded,
}: {
  caseId: number;
  onCancel: () => void;
  onAdded: () => void;
}) {
  const today = todayIso();
  const [requestedDays, setRequestedDays] = useState("10");
  const [decidedOn, setDecidedOn] = useState(today);
  const [reason, setReason] = useState("");
  const [notes, setNotes] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const snackbar = useSnackbar();
  const fieldIdBase = useId();

  const submit = async () => {
    setBusy(true);
    setError(null);
    try {
      if (!reason.trim()) throw new Error("Uzatma gerekçesi zorunludur.");
      // Müdür onayı (Form-13) burada girilmez — kayıt sonrası satırdaki
      // "Müdür onayı" paneli ayrı uçtan işler (OYS'den sapma: create'te onay alanı yok).
      const body: ExtensionCreateBody = {
        requested_days: Number(requestedDays),
        reason: reason.trim(),
        decided_on: decidedOn,
        notes: notes.trim(),
      };
      await disiplinApi.createExtension(caseId, body);
      snackbar.success("Süre uzatması kaydedildi.");
      onAdded();
    } catch (err) {
      setError(asMessage(err, "Süre uzatması kaydedilemedi."));
      setBusy(false);
    }
  };

  return (
    <div className="space-y-4 rounded-shape-md bg-surface-container-low p-4">
      <p className="text-title-medium text-on-surface">Kurul süre uzatması (Form-12/13)</p>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <TextField
          label="Ek süre (iş günü)"
          type="number"
          min={1}
          required
          value={requestedDays}
          onChange={(e) => setRequestedDays(e.target.value)}
        />
        <TextField
          label="Ara karar tarihi"
          type="date"
          required
          value={decidedOn}
          onChange={(e) => setDecidedOn(e.target.value)}
        />
      </div>
      <div>
        <label
          htmlFor={`${fieldIdBase}-reason`}
          className="mb-1 block text-label-large text-on-surface-variant"
        >
          Gerekçe <span className="text-error">*</span>
        </label>
        <textarea
          id={`${fieldIdBase}-reason`}
          required
          rows={3}
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          placeholder="Sürenin neden uzatıldığına dair ara karar gerekçesi."
          className="block w-full rounded-shape-xs border border-outline bg-surface px-4 py-3 text-body-medium text-on-surface outline-none focus-visible:ring-2 focus-visible:ring-primary focus:border-primary"
        />
      </div>
      <div>
        <label
          htmlFor={`${fieldIdBase}-notes`}
          className="mb-1 block text-label-large text-on-surface-variant"
        >
          Not (opsiyonel)
        </label>
        <textarea
          id={`${fieldIdBase}-notes`}
          rows={2}
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
          className="block w-full rounded-shape-xs border border-outline bg-surface px-4 py-3 text-body-medium text-on-surface outline-none focus-visible:ring-2 focus-visible:ring-primary focus:border-primary"
        />
      </div>
      <FormError error={error} />
      <PanelActions
        busy={busy}
        onCancel={onCancel}
        onSubmit={submit}
        submitLabel="Uzatmayı kaydet"
      />
    </div>
  );
}

function ApproveExtensionForm({
  caseId,
  extension: x,
  onCancel,
  onDone,
}: {
  caseId: number;
  extension: DisciplineDeadlineExtension;
  onCancel: () => void;
  onDone: () => void;
}) {
  const today = todayIso();
  const [approvedOn, setApprovedOn] = useState(today);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const snackbar = useSnackbar();

  const submit = async () => {
    setBusy(true);
    setError(null);
    try {
      await disiplinApi.approveExtension(caseId, x.id, { approved_on: approvedOn });
      snackbar.success("Onay kaydedildi.");
      onDone();
    } catch (err) {
      setError(asMessage(err, "Onay kaydedilemedi."));
      setBusy(false);
    }
  };

  return (
    <PanelShell title="Müdür onayı (Form-13)" icon="approval">
      <TextField
        label="Onay tarihi"
        type="date"
        required
        value={approvedOn}
        onChange={(e) => setApprovedOn(e.target.value)}
      />
      <FormError error={error} />
      <PanelActions busy={busy} onCancel={onCancel} onSubmit={submit} submitLabel="Onayı kaydet" />
    </PanelShell>
  );
}

// ===========================================================================
// Tedbir / geçici uzaklaştırma (md. 175)
// ===========================================================================

function PrecautionsCard({
  caseObj,
  caps,
}: {
  caseObj: DisciplineCase;
  caps: DisciplineCapabilities;
}) {
  // Tedbir / geçici uzaklaştırma (md. 175) müdür yetkisindedir.
  const canManage = caps.isMudur || caps.isAdmin;
  const [precautions, setPrecautions] = useState<DisciplinePrecaution[] | null>(null);
  const [hidden, setHidden] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [adding, setAdding] = useState(false);
  const names = studentNames(caseObj);

  const load = useCallback(() => {
    disiplinApi
      .listPrecautions(caseObj.id)
      .then((list) => {
        setPrecautions(list);
        setError(null);
      })
      .catch((e: unknown) => {
        if (e instanceof ApiError && e.status === 403) {
          setHidden(true);
          return;
        }
        setError(e instanceof ApiError ? e.message : "Tedbirler yüklenemedi.");
      });
  }, [caseObj.id]);
  useEffect(load, [load]);

  if (hidden) return null;

  return (
    <Card elevation={1} className="p-6">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-title-medium text-on-surface">Tedbir / geçici uzaklaştırma</p>
        {canManage && !adding && (
          <Button variant="tonal" icon="block" onClick={() => setAdding(true)}>
            Tedbir ekle
          </Button>
        )}
      </div>
      <p className="mt-1 text-body-small text-on-surface-variant">
        Md. 175 — acele geçici uzaklaştırma: en fazla 10 iş günü, tedbirden itibaren 3 iş günü
        içinde işleme başlanır, iki kez daha uzatılabilir. Bu süre devamsızlıktan sayılmaz.
      </p>

      {adding && (
        <div className="mt-4">
          <AddPrecautionForm
            caseObj={caseObj}
            onCancel={() => setAdding(false)}
            onAdded={() => {
              setAdding(false);
              load();
            }}
          />
        </div>
      )}

      {error && (
        <div className="mt-3 flex items-start gap-2 rounded-shape-sm bg-error-container px-4 py-2 text-body-small text-on-error-container">
          <Icon name="error" size="sm" />
          <span>{error}</span>
        </div>
      )}

      {precautions === null ? (
        <SkeletonList rows={3} />
      ) : precautions.length === 0 ? (
        <p className="mt-3 text-body-medium text-on-surface-variant">Tedbir kararı kaydedilmedi.</p>
      ) : (
        <ul className="mt-3 space-y-3">
          {precautions.map((p) => (
            <PrecautionRow
              key={p.id}
              caseId={caseObj.id}
              precaution={p}
              studentName={names[p.student] ?? `Öğrenci #${p.student}`}
              canManage={canManage}
              onChanged={load}
            />
          ))}
        </ul>
      )}
    </Card>
  );
}

type PrecautionPanel = "lift" | "extend" | null;

function PrecautionRow({
  caseId,
  precaution: p,
  studentName,
  canManage,
  onChanged,
}: {
  caseId: number;
  precaution: DisciplinePrecaution;
  studentName: string;
  canManage: boolean;
  onChanged: () => void;
}) {
  const [panel, setPanel] = useState<PrecautionPanel>(null);
  const isActive = p.status === "ACTIVE";

  return (
    <li className="rounded-shape-md border border-outline-variant bg-surface-container-low p-4">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="flex flex-wrap items-center gap-2 text-body-large text-on-surface">
            <Icon name="block" size="base" className="text-primary" />
            <span className="font-medium">{studentName}</span>
            <span className="text-on-surface-variant">· {p.requested_days} iş günü</span>
          </p>
          <p className="mt-1 text-label-small text-on-surface-variant">
            Başlangıç: {formatDate(p.start_date)}
            {p.end_date && ` · bitiş: ${formatDate(p.end_date)}`}
            {p.process_start_deadline &&
              ` · işleme başlama son günü: ${formatDate(p.process_start_deadline)}`}
            {p.lifted_on && ` · sonlanma: ${formatDate(p.lifted_on)}`}
          </p>
        </div>
        <span
          className={`inline-flex items-center rounded-shape-xl px-2.5 py-0.5 text-label-small ${PRECAUTION_STATUS_CHIP[p.status]}`}
        >
          {p.status_display}
        </span>
      </div>

      <div className="mt-2 flex flex-wrap gap-2 text-label-small text-on-surface-variant">
        {p.extension_count > 0 && (
          <span className="inline-flex items-center gap-1 rounded-shape-xl bg-surface-container px-2.5 py-0.5">
            <Icon name="more_time" size="xs" />
            {p.extension_count}/2 uzatma
          </span>
        )}
        <span className="inline-flex items-center gap-1 rounded-shape-xl bg-surface-container px-2.5 py-0.5">
          <Icon name={p.mne_notified ? "check" : "close"} size="xs" />
          MEB bilgilendirme {p.mne_notified ? "yapıldı" : "yapılmadı"}
        </span>
      </div>

      {p.reason && (
        <p className="mt-2 whitespace-pre-wrap text-body-medium text-on-surface-variant">
          {p.reason}
        </p>
      )}

      {canManage && isActive && panel === null && (
        <div className="mt-2 flex flex-wrap gap-1">
          {p.extension_count < 2 && (
            <Button variant="text" icon="more_time" onClick={() => setPanel("extend")}>
              Uzat
            </Button>
          )}
          <Button variant="text" icon="event_busy" onClick={() => setPanel("lift")}>
            Sonlandır
          </Button>
        </div>
      )}

      {panel === "lift" && (
        <LiftPrecautionForm
          caseId={caseId}
          precaution={p}
          onCancel={() => setPanel(null)}
          onDone={() => {
            setPanel(null);
            onChanged();
          }}
        />
      )}
      {panel === "extend" && (
        <ExtendPrecautionForm
          caseId={caseId}
          precaution={p}
          onCancel={() => setPanel(null)}
          onDone={() => {
            setPanel(null);
            onChanged();
          }}
        />
      )}
    </li>
  );
}

function AddPrecautionForm({
  caseObj,
  onCancel,
  onAdded,
}: {
  caseObj: DisciplineCase;
  onCancel: () => void;
  onAdded: () => void;
}) {
  const today = todayIso();
  const students = caseObj.students;
  const [studentId, setStudentId] = useState<string>(
    students.length === 1 ? String(students[0].id) : "",
  );
  const [startDate, setStartDate] = useState(today);
  const [requestedDays, setRequestedDays] = useState("10");
  const [reason, setReason] = useState("");
  const [mneNotified, setMneNotified] = useState(false);
  const [notes, setNotes] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const snackbar = useSnackbar();
  const fieldIdBase = useId();

  const submit = async () => {
    setBusy(true);
    setError(null);
    try {
      if (!studentId) throw new Error("Bir öğrenci seçilmelidir.");
      const body: PrecautionCreateBody = {
        student_id: Number(studentId),
        start_date: startDate,
        requested_days: Number(requestedDays),
        reason: reason.trim(),
        mne_notified: mneNotified,
        notes: notes.trim(),
      };
      await disiplinApi.createPrecaution(caseObj.id, body);
      snackbar.success("Tedbir kaydedildi.");
      onAdded();
    } catch (err) {
      setError(asMessage(err, "Tedbir kaydedilemedi."));
      setBusy(false);
    }
  };

  return (
    <div className="space-y-4 rounded-shape-md bg-surface-container-low p-4">
      <p className="text-title-medium text-on-surface">Yeni tedbir (geçici uzaklaştırma)</p>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <Select
          label="Öğrenci"
          required
          placeholder="Seçiniz…"
          value={studentId}
          onChange={(e) => setStudentId(e.target.value)}
          options={students.map((s: CaseStudent) => ({
            value: String(s.id),
            label: s.class_label ? `${s.full_name} · ${s.class_label}` : s.full_name,
          }))}
        />
        <TextField
          label="Süre (iş günü, 1-10)"
          type="number"
          min={1}
          max={10}
          required
          value={requestedDays}
          onChange={(e) => setRequestedDays(e.target.value)}
          helperText="Md. 175/1 — en fazla 10 iş günü."
        />
      </div>
      <TextField
        label="Başlangıç tarihi"
        type="date"
        required
        value={startDate}
        onChange={(e) => setStartDate(e.target.value)}
      />
      <div>
        <label
          htmlFor={`${fieldIdBase}-reason`}
          className="mb-1 block text-label-large text-on-surface-variant"
        >
          Gerekçe (opsiyonel)
        </label>
        <textarea
          id={`${fieldIdBase}-reason`}
          rows={2}
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          className="block w-full rounded-shape-xs border border-outline bg-surface px-4 py-3 text-body-medium text-on-surface outline-none focus-visible:ring-2 focus-visible:ring-primary focus:border-primary"
        />
      </div>
      <label className="flex min-h-12 items-center gap-3 text-body-medium text-on-surface">
        <input
          type="checkbox"
          checked={mneNotified}
          onChange={(e) => setMneNotified(e.target.checked)}
          className="h-5 w-5 accent-primary"
        />
        Milli Eğitim Müdürlüğü bilgilendirildi
      </label>
      <div>
        <label
          htmlFor={`${fieldIdBase}-notes`}
          className="mb-1 block text-label-large text-on-surface-variant"
        >
          Not (opsiyonel)
        </label>
        <textarea
          id={`${fieldIdBase}-notes`}
          rows={2}
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
          className="block w-full rounded-shape-xs border border-outline bg-surface px-4 py-3 text-body-medium text-on-surface outline-none focus-visible:ring-2 focus-visible:ring-primary focus:border-primary"
        />
      </div>
      <FormError error={error} />
      <PanelActions
        busy={busy}
        onCancel={onCancel}
        onSubmit={submit}
        submitLabel="Tedbiri kaydet"
      />
    </div>
  );
}

function LiftPrecautionForm({
  caseId,
  precaution: p,
  onCancel,
  onDone,
}: {
  caseId: number;
  precaution: DisciplinePrecaution;
  onCancel: () => void;
  onDone: () => void;
}) {
  const today = todayIso();
  const [liftedOn, setLiftedOn] = useState(today);
  const [expired, setExpired] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const snackbar = useSnackbar();

  const submit = async () => {
    setBusy(true);
    setError(null);
    try {
      await disiplinApi.liftPrecaution(caseId, p.id, { lifted_on: liftedOn, expired });
      snackbar.success("Tedbir sonlandırıldı.");
      onDone();
    } catch (err) {
      setError(asMessage(err, "Tedbir sonlandırılamadı."));
      setBusy(false);
    }
  };

  return (
    <PanelShell title="Tedbiri sonlandır" icon="event_busy">
      <TextField
        label="Sonlanma tarihi"
        type="date"
        required
        value={liftedOn}
        onChange={(e) => setLiftedOn(e.target.value)}
      />
      <label className="flex min-h-12 items-center gap-3 text-body-medium text-on-surface">
        <input
          type="checkbox"
          checked={expired}
          onChange={(e) => setExpired(e.target.checked)}
          className="h-5 w-5 accent-primary"
        />
        Süre dolduğu için kendiliğinden kalktı
      </label>
      <p className="text-body-small text-on-surface-variant">
        İşaretlenmezse "kaldırıldı" (idarî karar) olarak kaydedilir.
      </p>
      <FormError error={error} />
      <PanelActions busy={busy} onCancel={onCancel} onSubmit={submit} submitLabel="Sonlandır" />
    </PanelShell>
  );
}

function ExtendPrecautionForm({
  caseId,
  precaution: p,
  onCancel,
  onDone,
}: {
  caseId: number;
  precaution: DisciplinePrecaution;
  onCancel: () => void;
  onDone: () => void;
}) {
  const [additionalDays, setAdditionalDays] = useState("1");
  const [mneNotified, setMneNotified] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const snackbar = useSnackbar();

  const submit = async () => {
    setBusy(true);
    setError(null);
    try {
      await disiplinApi.extendPrecaution(caseId, p.id, {
        additional_days: Number(additionalDays),
        mne_notified: mneNotified,
      });
      snackbar.success("Tedbir uzatıldı.");
      onDone();
    } catch (err) {
      setError(asMessage(err, "Tedbir uzatılamadı."));
      setBusy(false);
    }
  };

  return (
    <PanelShell title="Tedbiri uzat" icon="more_time">
      <p className="text-body-small text-on-surface-variant">
        Toplam süre 10 iş gününü aşamaz; en fazla iki kez uzatılabilir (md. 175/2). Mevcut:{" "}
        {p.requested_days} gün, {p.extension_count}/2 uzatma.
      </p>
      <TextField
        label="Ek süre (iş günü, 1-9)"
        type="number"
        min={1}
        max={9}
        required
        value={additionalDays}
        onChange={(e) => setAdditionalDays(e.target.value)}
      />
      <label className="flex min-h-12 items-center gap-3 text-body-medium text-on-surface">
        <input
          type="checkbox"
          checked={mneNotified}
          onChange={(e) => setMneNotified(e.target.checked)}
          className="h-5 w-5 accent-primary"
        />
        Milli Eğitim Müdürlüğü bilgilendirildi
      </label>
      <FormError error={error} />
      <PanelActions
        busy={busy}
        onCancel={onCancel}
        onSubmit={submit}
        submitLabel="Uzatmayı kaydet"
      />
    </PanelShell>
  );
}
