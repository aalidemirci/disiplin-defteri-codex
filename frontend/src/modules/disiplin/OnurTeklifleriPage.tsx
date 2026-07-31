import { useCallback, useEffect, useState } from "react";
import type { ReactNode } from "react";
import { Link } from "react-router-dom";

import { ApiError } from "../../lib/api";
import { saveBlob } from "../../lib/download";
import { todayIso } from "../../lib/format";
import Button from "../../ui/Button";
import Card from "../../ui/Card";
import Icon from "../../ui/Icon";
import Select from "../../ui/Select";
import { SkeletonList } from "../../ui/Skeleton";
import TextField from "../../ui/TextField";
import { okulApi, type SchoolTerm } from "../okul/api";
import { criteriaDisplay, odulApi, type HonorCertificate } from "../odul/api";

export default function OnurTeklifleriPage() {
  const [terms, setTerms] = useState<SchoolTerm[]>([]);
  const [termId, setTermId] = useState<number | null>(null);
  const [items, setItems] = useState<HonorCertificate[]>([]);
  const [decisionDate, setDecisionDate] = useState(todayIso());
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busyDocument, setBusyDocument] = useState(false);

  useEffect(() => {
    okulApi
      .listSchoolYears()
      .then(async (years) => {
        const active = years.find((year) => year.is_active);
        if (!active) throw new Error("Aktif ders yılı bulunamadı.");
        const rows = await okulApi.listSchoolTerms(active.id);
        setTerms(rows);
        const today = todayIso();
        setTermId(
          rows.find((term) => term.start_date <= today && today <= term.end_date)?.id ??
            rows[0]?.id ??
            null,
        );
      })
      .catch((e: unknown) => setError(e instanceof Error ? e.message : "Dönemler yüklenemedi."));
  }, []);

  const load = useCallback(() => {
    if (termId === null) {
      setItems([]);
      setLoading(false);
      return;
    }
    setLoading(true);
    odulApi
      .listCertificates({ schoolTermId: termId })
      .then((rows) => {
        setItems(rows);
        setError(null);
      })
      .catch((e: unknown) =>
        setError(e instanceof ApiError ? e.message : "Onur teklifleri yüklenemedi."),
      )
      .finally(() => setLoading(false));
  }, [termId]);

  useEffect(load, [load]);

  const committeePending = items.filter((item) => item.status === "HONOR_BOARD_RECOMMENDED");
  const principalPending = items.filter((item) => item.status === "AWARDED");
  const completed = items.filter((item) =>
    ["PRINCIPAL_APPROVED", "PRINCIPAL_REJECTED", "REJECTED"].includes(item.status),
  );
  const committeeApproved = items.filter((item) =>
    ["AWARDED", "PRINCIPAL_APPROVED", "PRINCIPAL_REJECTED"].includes(item.status),
  );

  const downloadCommitteeDecision = async () => {
    if (committeeApproved.length === 0) return;
    setBusyDocument(true);
    try {
      saveBlob(
        await odulApi.awardRecord(committeeApproved.map((item) => item.id)),
        `odul-disiplin-kurulu-onur-karari-${termId}.pdf`,
      );
    } catch (e: unknown) {
      setError(e instanceof ApiError ? e.message : "Kurul karar çizelgesi üretilemedi.");
    } finally {
      setBusyDocument(false);
    }
  };

  return (
    <div className="space-y-6">
      <div className="dd-page-header">
        <div className="min-w-0">
          <h1 className="dd-page-title">Onur belgesi teklifleri</h1>
          <p className="dd-page-description">
            Onur Kurulunun önerilerini Ödül ve Disiplin Kurulunda karara bağlayın ve kabul edilen
            kararları okul müdürü onayına sunun.
          </p>
        </div>
        <Link
          to="/disiplin"
          className="inline-flex min-h-[var(--dd-control-height)] items-center gap-2 rounded-shape-md px-3 text-label-large text-primary hover:bg-primary/8"
        >
          <Icon name="arrow_back" />
          Disipline dön
        </Link>
      </div>

      <Card elevation={0} className="grid max-w-2xl gap-3 p-4 shadow-elevation-1 sm:grid-cols-2">
        <Select
          label="Teklif dönemi"
          value={termId === null ? "" : String(termId)}
          onChange={(event) => setTermId(Number(event.target.value))}
          options={terms.map((term) => ({ value: String(term.id), label: term.name }))}
        />
        <TextField
          label="Karar / onay tarihi"
          type="date"
          value={decisionDate}
          onChange={(event) => setDecisionDate(event.target.value)}
        />
      </Card>

      {error && <ErrorBanner message={error} />}
      {loading ? (
        <SkeletonList rows={5} />
      ) : (
        <>
          <DecisionSection
            title={`Ödül ve Disiplin Kurulu kararında (${committeePending.length})`}
            empty="Onur Kurulundan gelen yeni teklif yok."
            items={committeePending}
            render={(item) => (
              <CommitteeDecisionRow
                key={item.id}
                item={item}
                decisionDate={decisionDate}
                onChanged={load}
              />
            )}
          />

          <section>
            <div className="flex flex-wrap items-center justify-between gap-2">
              <h2 className="text-title-medium text-on-surface">
                Okul müdürü onayında ({principalPending.length})
              </h2>
              {committeeApproved.length > 0 && (
                <Button
                  variant="outlined"
                  icon="description"
                  onClick={downloadCommitteeDecision}
                  disabled={busyDocument}
                >
                  {busyDocument ? "Hazırlanıyor…" : "Kurul karar çizelgesi"}
                </Button>
              )}
            </div>
            {principalPending.length === 0 ? (
              <p className="mt-2 text-body-medium text-on-surface-variant">
                Onay bekleyen kurul kararı yok.
              </p>
            ) : (
              <ul className="mt-3 space-y-3">
                {principalPending.map((item) => (
                  <PrincipalDecisionRow
                    key={item.id}
                    item={item}
                    decisionDate={decisionDate}
                    onChanged={load}
                  />
                ))}
              </ul>
            )}
          </section>

          {completed.length > 0 && (
            <section>
              <h2 className="text-title-medium text-on-surface">
                Sonuçlananlar ({completed.length})
              </h2>
              <ul className="mt-3 space-y-2">
                {completed.map((item) => (
                  <li key={item.id}>
                    <Card elevation={1} className="p-4">
                      <p className="text-title-small text-on-surface">{item.student_name}</p>
                      <p className="text-body-small text-on-surface-variant">
                        {item.status_display}
                      </p>
                    </Card>
                  </li>
                ))}
              </ul>
            </section>
          )}
        </>
      )}
    </div>
  );
}

function DecisionSection({
  title,
  empty,
  items,
  render,
}: {
  title: string;
  empty: string;
  items: HonorCertificate[];
  render: (item: HonorCertificate) => ReactNode;
}) {
  return (
    <section>
      <h2 className="text-title-medium text-on-surface">{title}</h2>
      {items.length === 0 ? (
        <p className="mt-2 text-body-medium text-on-surface-variant">{empty}</p>
      ) : (
        <ul className="mt-3 space-y-3">{items.map(render)}</ul>
      )}
    </section>
  );
}

function ProposalSummary({ item }: { item: HonorCertificate }) {
  return (
    <div>
      <p className="text-title-small text-on-surface">{item.student_name}</p>
      <p className="text-body-small text-on-surface-variant">
        {criteriaDisplay(item.criteria).join(" · ")}
      </p>
      {item.justification && (
        <p className="mt-1 text-body-small text-on-surface-variant">{item.justification}</p>
      )}
    </div>
  );
}

function CommitteeDecisionRow({
  item,
  decisionDate,
  onChanged,
}: {
  item: HonorCertificate;
  decisionDate: string;
  onChanged: () => void;
}) {
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const decide = async (approve: boolean) => {
    if (!approve && !reason.trim()) return setError("Ret gerekçesi zorunludur.");
    setBusy(true);
    setError(null);
    try {
      if (approve) {
        await odulApi.awardCertificate(item.id, { awarded_on: decisionDate });
      } else {
        await odulApi.rejectCertificate(item.id, {
          decided_on: decisionDate,
          reason: reason.trim(),
        });
      }
      onChanged();
    } catch (e: unknown) {
      setError(e instanceof ApiError ? e.message : "Kurul kararı kaydedilemedi.");
      setBusy(false);
    }
  };

  return (
    <li>
      <Card elevation={1} className="space-y-3 p-5">
        <ProposalSummary item={item} />
        <TextField
          label="Ret gerekçesi"
          value={reason}
          onChange={(event) => setReason(event.target.value)}
        />
        <div className="flex flex-wrap gap-2">
          <Button icon="gavel" onClick={() => decide(true)} disabled={busy}>
            Kabul et
          </Button>
          <Button variant="text" icon="block" onClick={() => decide(false)} disabled={busy}>
            Reddet
          </Button>
        </div>
        {error && <ErrorBanner message={error} />}
      </Card>
    </li>
  );
}

function PrincipalDecisionRow({
  item,
  decisionDate,
  onChanged,
}: {
  item: HonorCertificate;
  decisionDate: string;
  onChanged: () => void;
}) {
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const decide = async (approve: boolean) => {
    if (!approve && !reason.trim()) return setError("Onaylamama gerekçesi zorunludur.");
    setBusy(true);
    setError(null);
    try {
      if (approve) {
        await odulApi.principalApproveCertificate(item.id, {
          decided_on: decisionDate,
          explanation: reason.trim(),
        });
      } else {
        await odulApi.principalRejectCertificate(item.id, {
          decided_on: decisionDate,
          reason: reason.trim(),
        });
      }
      onChanged();
    } catch (e: unknown) {
      setError(e instanceof ApiError ? e.message : "Müdür onayı kaydedilemedi.");
      setBusy(false);
    }
  };

  return (
    <li>
      <Card elevation={1} className="space-y-3 p-5">
        <ProposalSummary item={item} />
        <TextField
          label="Onay açıklaması / onaylamama gerekçesi"
          value={reason}
          onChange={(event) => setReason(event.target.value)}
        />
        <div className="flex flex-wrap gap-2">
          <Button icon="verified" onClick={() => decide(true)} disabled={busy}>
            Onayla
          </Button>
          <Button
            variant="text"
            icon="do_not_disturb_on"
            onClick={() => decide(false)}
            disabled={busy}
          >
            Onaylama
          </Button>
        </div>
        {error && <ErrorBanner message={error} />}
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
