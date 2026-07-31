import { useCallback, useEffect, useState } from "react";

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
import { criteriaDisplay, odulApi, type HonorCertificate } from "./api";

export default function KurulKarariPanel() {
  const [terms, setTerms] = useState<SchoolTerm[]>([]);
  const [termId, setTermId] = useState<number | null>(null);
  const [items, setItems] = useState<HonorCertificate[]>([]);
  const [meetingDate, setMeetingDate] = useState(todayIso());
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busyChart, setBusyChart] = useState(false);

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
      .catch((e: unknown) => setError(e instanceof ApiError ? e.message : "Teklifler yüklenemedi."))
      .finally(() => setLoading(false));
  }, [termId]);

  useEffect(load, [load]);

  const proposed = items.filter((item) => item.status === "PROPOSED");
  const recommended = items.filter((item) => item.status === "HONOR_BOARD_RECOMMENDED");

  const downloadChart = async () => {
    if (recommended.length === 0) return;
    setBusyChart(true);
    try {
      saveBlob(
        await odulApi.recommendationRecord(recommended.map((item) => item.id)),
        `onur-kurulu-teklif-cizelgesi-${termId}.pdf`,
      );
    } catch (e: unknown) {
      setError(e instanceof ApiError ? e.message : "Teklif çizelgesi üretilemedi.");
    } finally {
      setBusyChart(false);
    }
  };

  return (
    <div className="space-y-6">
      <p className="max-w-3xl text-body-medium text-on-surface-variant">
        Onur Kurulu teklifleri inceler; uygun gördüklerini Ödül ve Disiplin Kuruluna önerir. Bu
        ekran belge verme veya nihai ödül kararı üretmez (md. 183/b).
      </p>
      <div className="grid max-w-2xl gap-3 sm:grid-cols-2">
        <Select
          label="Teklif dönemi"
          value={termId === null ? "" : String(termId)}
          onChange={(event) => setTermId(Number(event.target.value))}
          options={terms.map((term) => ({ value: String(term.id), label: term.name }))}
        />
        <TextField
          label="Onur Kurulu toplantı tarihi"
          type="date"
          value={meetingDate}
          onChange={(event) => setMeetingDate(event.target.value)}
        />
      </div>
      {error && <ErrorBanner message={error} />}
      {loading ? (
        <SkeletonList rows={4} />
      ) : (
        <>
          <section>
            <h2 className="text-title-medium text-on-surface">
              Karar bekleyen teklifler ({proposed.length})
            </h2>
            {proposed.length === 0 ? (
              <p className="mt-2 text-body-medium text-on-surface-variant">
                Karar bekleyen teklif yok.
              </p>
            ) : (
              <ul className="mt-3 space-y-3">
                {proposed.map((item) => (
                  <ProposalDecisionRow
                    key={item.id}
                    item={item}
                    meetingDate={meetingDate}
                    onChanged={load}
                  />
                ))}
              </ul>
            )}
          </section>
          <section>
            <div className="flex flex-wrap items-center justify-between gap-2">
              <h2 className="text-title-medium text-on-surface">
                Ödül ve Disiplin Kuruluna önerilenler ({recommended.length})
              </h2>
              {recommended.length > 0 && (
                <Button
                  variant="outlined"
                  icon="table_view"
                  onClick={downloadChart}
                  disabled={busyChart}
                >
                  {busyChart ? "Hazırlanıyor…" : "Teklif çizelgesi üret"}
                </Button>
              )}
            </div>
            <p className="mt-1 text-body-small text-on-surface-variant">
              Nihai değerlendirme Disiplin modülündeki “Onur teklifleri” ekranında yapılır.
            </p>
          </section>
        </>
      )}
    </div>
  );
}

function ProposalDecisionRow({
  item,
  meetingDate,
  onChanged,
}: {
  item: HonorCertificate;
  meetingDate: string;
  onChanged: () => void;
}) {
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const decide = async (recommend: boolean) => {
    if (!recommend && !reason.trim()) {
      setError("Uygun görmeme gerekçesi zorunludur.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      if (recommend) {
        await odulApi.recommendCertificate(item.id, { recommended_on: meetingDate });
      } else {
        await odulApi.rejectCertificate(item.id, {
          decided_on: meetingDate,
          reason: reason.trim(),
        });
      }
      onChanged();
    } catch (e: unknown) {
      setError(e instanceof ApiError ? e.message : "Karar kaydedilemedi.");
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
          {item.justification && (
            <p className="mt-1 text-body-small text-on-surface-variant">{item.justification}</p>
          )}
        </div>
        <TextField
          label="Uygun görülmeme gerekçesi"
          value={reason}
          onChange={(event) => setReason(event.target.value)}
        />
        <div className="flex flex-wrap gap-2">
          <Button icon="thumb_up" onClick={() => decide(true)} disabled={busy}>
            Uygun gör ve öner
          </Button>
          <Button variant="text" icon="block" onClick={() => decide(false)} disabled={busy}>
            Uygun görme
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
