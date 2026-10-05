// Okul müdürü onayı (04.10.2026, kurul işleyişi Aşama 1) — Ödül ve Disiplin Kurulunun
// onur belgesi kabul kararları müdüre sunulur (md. 196/3); müdür onaylar ya da gerekçeyle
// onaylamaz. Onayda uygunluk yeniden denetlenir (M8: kurul kararından sonra ceza alan /
// puanı düşen öğrenciye onaylanmaz — md. 161, 181/1). Müdür onayı geri alınamaz;
// onaylamama "Onur Kurulu → Teklifler"den gerekçeyle geri alınabilir.
// Eski `disiplin/OnurTeklifleriPage` müdür bölümünden taşındı; kurulun kabul/ret kararı
// artık toplantı ekranında verilir. Disiplin kararlarının onayı dosya içinde kalır.

import { useCallback, useEffect, useState } from "react";

import { ApiError } from "../../lib/api";
import { formatDate, todayIso } from "../../lib/format";
import Button from "../../ui/Button";
import Card from "../../ui/Card";
import Icon from "../../ui/Icon";
import { SkeletonList } from "../../ui/Skeleton";
import TextField from "../../ui/TextField";
import { okulApi } from "../okul/api";
import { criteriaDisplay, odulApi, type HonorCertificate } from "../odul/api";

export default function MudurOnayiPanel() {
  const [pending, setPending] = useState<HonorCertificate[]>([]);
  const [completed, setCompleted] = useState<HonorCertificate[]>([]);
  const [decisionDate, setDecisionDate] = useState(todayIso());
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    setLoading(true);
    Promise.all([
      odulApi.listCertificates({ status: "AWARDED" }),
      okulApi.listSchoolYears().then((years) => {
        const active = years.find((year) => year.is_active);
        return active ? odulApi.listCertificates({ schoolYearId: active.id }) : [];
      }),
    ])
      .then(([awarded, yearRows]) => {
        setPending(awarded);
        setCompleted(
          yearRows.filter((c) => ["PRINCIPAL_APPROVED", "PRINCIPAL_REJECTED"].includes(c.status)),
        );
        setError(null);
      })
      .catch((e: unknown) =>
        setError(e instanceof ApiError ? e.message : "Onay bekleyen kararlar yüklenemedi."),
      )
      .finally(() => setLoading(false));
  }, []);

  useEffect(load, [load]);

  return (
    <div className="space-y-6">
      <p className="max-w-3xl text-body-medium text-on-surface-variant">
        Ödül ve Disiplin Kurulunun onur belgesi verilmesine ilişkin kabul kararları okul müdürünün
        onayına sunulur. Kurul karar çizelgesi ilgili toplantının ekranından üretilir.
      </p>

      <Card elevation={0} className="max-w-xs p-4 shadow-elevation-1">
        <TextField
          label="Onay tarihi"
          type="date"
          value={decisionDate}
          onChange={(event) => setDecisionDate(event.target.value)}
        />
      </Card>

      {error && <ErrorBanner message={error} />}

      {loading ? (
        <SkeletonList rows={4} />
      ) : (
        <>
          <section>
            <h2 className="text-title-medium text-on-surface">
              Okul müdürü onayında ({pending.length})
            </h2>
            {pending.length === 0 ? (
              <p className="mt-2 text-body-medium text-on-surface-variant">
                Onay bekleyen kurul kararı yok.
              </p>
            ) : (
              <ul className="mt-3 space-y-3">
                {pending.map((item) => (
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
                Sonuçlananlar — bu ders yılı ({completed.length})
              </h2>
              <ul className="mt-3 space-y-2">
                {completed.map((item) => (
                  <li key={item.id}>
                    <Card elevation={1} className="p-4">
                      <p className="text-title-small text-on-surface">{item.student_name}</p>
                      <p className="text-body-small text-on-surface-variant">
                        {item.status_display}
                        {item.principal_decided_at
                          ? ` · ${formatDate(item.principal_decided_at)}`
                          : ""}
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
        <div>
          <p className="text-title-small text-on-surface">{item.student_name}</p>
          <p className="text-body-small text-on-surface-variant">
            {criteriaDisplay(item.criteria).join(" · ")}
          </p>
          {item.awarded_at && (
            <p className="mt-1 text-label-small text-on-surface-variant">
              Kurul kabul kararı: {formatDate(item.awarded_at)}
            </p>
          )}
        </div>
        <TextField
          label="Onay açıklaması / onaylamama gerekçesi"
          value={reason}
          onChange={(event) => setReason(event.target.value)}
        />
        <div className="flex flex-wrap gap-2">
          <Button icon="verified" onClick={() => void decide(true)} disabled={busy}>
            Onayla
          </Button>
          <Button
            variant="text"
            icon="do_not_disturb_on"
            onClick={() => void decide(false)}
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
