// Kurul gündemi (04.10.2026, kurul işleyişi Aşama 1) — kurulun önünde bekleyen işler.
//
// Onur Kurulu: teklif aşamasındaki onur belgesi teklifleri (md. 161/1 → 183/b).
// Ödül ve Disiplin Kurulu: Onur Kurulunca uygun görülüp kurula sunulanlar (md. 161/1).
// Teklifler seçilir → "Toplantı aç" (katılanlar aktif kuruldan gelir) → toplantı ekranında
// madde madde karara bağlanır. Karar bekleyen maddesi olan açık toplantılar ayrıca
// listelenir; teklif aynı anda yalnız bir toplantıda karar bekleyebilir.

import { useCallback, useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";

import { ApiError } from "../../lib/api";
import { formatDate } from "../../lib/format";
import Button from "../../ui/Button";
import Card from "../../ui/Card";
import Icon from "../../ui/Icon";
import { SkeletonList } from "../../ui/Skeleton";
import { criteriaDisplay, type HonorCertificate } from "../odul/api";
import { COUNCIL_TYPE_TR, hasPendingItems, kurulApi } from "./api";
import type { CouncilMeeting, CouncilType } from "./api";
import ToplantiForm from "./ToplantiForm";

interface Props {
  councilType: CouncilType;
  /** Toplantılar sekmesinin anahtarı (açılan toplantıya yönlendirme). */
  meetingsTab: string;
}

const INTRO: Record<CouncilType, string> = {
  HONOR:
    "Onur Kurulu ayda en az bir kez toplanır ve onur belgesi verilmesi istenen öğrenciler " +
    "için Ödül ve Disiplin Kuruluna öneride bulunur (md. 183). Aşağıdaki teklifler Onur " +
    "Kurulunun görüşünü bekliyor.",
  DISCIPLINE:
    "Ödül ve Disiplin Kurulu, Onur Kurulunun uygun gördüğü teklifleri görüşüp onur belgesi " +
    "verilmesine karar verir (md. 161/1, 189/ç). Kararlar karar defterine yazılır ve okul " +
    "müdürüne sunulur (md. 196).",
};

const EMPTY: Record<CouncilType, string> = {
  HONOR: "Onur Kurulunun görüşünü bekleyen teklif yok.",
  DISCIPLINE: "Onur Kurulundan gelen, kurul kararı bekleyen öneri yok.",
};

export default function GundemPanel({ councilType, meetingsTab }: Props) {
  const [, setSearchParams] = useSearchParams();
  const [candidates, setCandidates] = useState<HonorCertificate[]>([]);
  const [openMeetings, setOpenMeetings] = useState<CouncilMeeting[]>([]);
  const [selected, setSelected] = useState<number[]>([]);
  const [opening, setOpening] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    setLoading(true);
    Promise.all([kurulApi.agendaCandidates(councilType), kurulApi.listMeetings(councilType)])
      .then(([rows, meetings]) => {
        setCandidates(rows);
        setOpenMeetings(meetings.filter(hasPendingItems));
        setSelected((prev) => prev.filter((id) => rows.some((row) => row.id === id)));
        setError(null);
      })
      .catch((e: unknown) => setError(e instanceof ApiError ? e.message : "Gündem yüklenemedi."))
      .finally(() => setLoading(false));
  }, [councilType]);

  useEffect(load, [load]);

  const goToMeeting = (id: number) => {
    setSearchParams({ sekme: meetingsTab, toplanti: String(id) });
  };

  const selectedCertificates = candidates.filter((c) => selected.includes(c.id));

  if (opening) {
    return (
      <ToplantiForm
        councilType={councilType}
        agendaCertificates={selectedCertificates}
        onCreated={(meeting) => {
          setOpening(false);
          goToMeeting(meeting.id);
        }}
        onCancel={() => setOpening(false)}
      />
    );
  }

  return (
    <div className="space-y-6">
      <p className="max-w-3xl text-body-medium text-on-surface-variant">{INTRO[councilType]}</p>

      {error && (
        <div className="flex items-start gap-2 rounded-shape-sm bg-error-container px-4 py-3 text-body-small text-on-error-container">
          <Icon name="error" size="sm" />
          <span>{error}</span>
        </div>
      )}

      {loading ? (
        <SkeletonList rows={4} />
      ) : (
        <>
          {openMeetings.length > 0 && (
            <section className="space-y-2">
              <h2 className="text-title-medium text-on-surface">
                Karar bekleyen toplantılar ({openMeetings.length})
              </h2>
              <ul className="space-y-2">
                {openMeetings.map((m) => (
                  <li key={m.id}>
                    <Card
                      elevation={1}
                      className="flex flex-wrap items-center justify-between gap-2 p-4"
                    >
                      <span className="text-body-medium text-on-surface">
                        {COUNCIL_TYPE_TR[m.council_type]} — Toplantı {m.meeting_no_display} ·{" "}
                        {formatDate(m.meeting_date)} ·{" "}
                        {m.agenda_items.filter((i) => i.outcome === "PENDING").length} madde karar
                        bekliyor
                      </span>
                      <Button variant="text" icon="open_in_new" onClick={() => goToMeeting(m.id)}>
                        Toplantıyı aç
                      </Button>
                    </Card>
                  </li>
                ))}
              </ul>
            </section>
          )}

          <section className="space-y-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <h2 className="text-title-medium text-on-surface">
                Gündeme alınmayı bekleyen teklifler ({candidates.length})
              </h2>
              {candidates.length > 0 && (
                <Button
                  icon="event"
                  onClick={() => setOpening(true)}
                  disabled={selected.length === 0}
                >
                  Seçilenlerle toplantı aç ({selected.length})
                </Button>
              )}
            </div>
            {candidates.length === 0 ? (
              <p className="text-body-medium text-on-surface-variant">{EMPTY[councilType]}</p>
            ) : (
              <>
                <Button
                  variant="text"
                  onClick={() =>
                    setSelected(
                      selected.length === candidates.length ? [] : candidates.map((c) => c.id),
                    )
                  }
                >
                  {selected.length === candidates.length ? "Seçimi temizle" : "Tümünü seç"}
                </Button>
                <ul className="space-y-2">
                  {candidates.map((c) => (
                    <li key={c.id}>
                      <Card elevation={1} className="p-4">
                        <label className="flex items-start gap-3">
                          <input
                            type="checkbox"
                            className="mt-1 size-5 accent-primary"
                            checked={selected.includes(c.id)}
                            onChange={(e) =>
                              setSelected((prev) =>
                                e.target.checked
                                  ? [...prev, c.id]
                                  : prev.filter((id) => id !== c.id),
                              )
                            }
                          />
                          <span>
                            <span className="block text-title-small text-on-surface">
                              {c.student_name}
                              {c.term_name && (
                                <span className="ml-2 text-label-small text-on-surface-variant">
                                  {c.term_name}
                                </span>
                              )}
                            </span>
                            <span className="block text-body-small text-on-surface-variant">
                              {criteriaDisplay(c.criteria).join(" · ")}
                            </span>
                            {c.justification && (
                              <span className="mt-1 block text-body-small text-on-surface-variant">
                                {c.justification}
                              </span>
                            )}
                            {councilType === "DISCIPLINE" && c.recommended_at && (
                              <span className="mt-1 block text-label-small text-on-surface-variant">
                                Onur Kurulu uygun görüşü: {formatDate(c.recommended_at)}
                              </span>
                            )}
                          </span>
                        </label>
                      </Card>
                    </li>
                  ))}
                </ul>
              </>
            )}
          </section>
        </>
      )}
    </div>
  );
}
