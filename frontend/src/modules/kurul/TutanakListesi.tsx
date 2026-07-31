// Kurul Toplantı Tutanakları listesi — md. 184/206 karar defteri. Her kurulun
// kendi sekmesine gömülür (Onur Kurulu → "Toplantılar", Disiplin Kurulu →
// "Toplantı Tutanakları"); kurul türü prop ile sabitlenir. Disiplin tarafında
// tutanak türü (dosya görüşme / diğer) sütunu + görüşülen dosya bağlantısı
// gösterilir. 403 kilit kartı savunmacı olarak korunur (authsuz masaüstünde
// pratikte oluşmaz).
//
// OYS `modules/kurul/TutanakListesi.tsx`'ten UYARLANDI (F4-D3); sapmalar:
// serializer display türevi taşımadığından tür etiketi MINUTES_TYPE_TR'den,
// katılımcı sayısı `attendees.length`'ten türetilir (attendee_count yok).

import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { ApiError } from "../../lib/api";
import Button from "../../ui/Button";
import Card from "../../ui/Card";
import Icon from "../../ui/Icon";
import Skeleton from "../../ui/Skeleton";
import { useConfirm } from "../../ui/ConfirmProvider";
import { useSnackbar } from "../../ui/SnackbarProvider";
import { COUNCIL_TYPE_TR, DECISION_BASIS_TR, MINUTES_TYPE_TR, kurulApi } from "./api";
import type { CouncilMeeting, CouncilType } from "./api";
import { saveBlob } from "../../lib/download";
import ToplantiForm from "./ToplantiForm";

interface Props {
  councilType: CouncilType;
}

export default function TutanakListesi({ councilType }: Props) {
  const snackbar = useSnackbar();
  const confirm = useConfirm();
  const [meetings, setMeetings] = useState<CouncilMeeting[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [forbidden, setForbidden] = useState(false);
  const [creating, setCreating] = useState(false);
  const isDiscipline = councilType === "DISCIPLINE";

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await kurulApi.listMeetings(councilType);
      setMeetings(data);
      setForbidden(false);
    } catch (err) {
      if (err instanceof ApiError && err.status === 403) {
        setForbidden(true);
      } else {
        setError(err instanceof ApiError ? err.message : "Tutanaklar yüklenemedi.");
      }
    } finally {
      setLoading(false);
    }
  }, [councilType]);

  useEffect(() => {
    void load();
  }, [load]);

  const onDownload = async (m: CouncilMeeting) => {
    try {
      const blob = await kurulApi.minutes(m.id);
      saveBlob(blob, `kurul-toplanti-tutanagi-${m.meeting_no_display}.pdf`);
    } catch (err) {
      snackbar.error(err instanceof ApiError ? err.message : "Tutanak indirilemedi.");
    }
  };

  const onDelete = async (m: CouncilMeeting) => {
    const ok = await confirm({
      title: "Tutanağı sil",
      message: `${COUNCIL_TYPE_TR[m.council_type]} — Toplantı ${m.meeting_no_display} tutanağı silinsin mi? (Geri alınabilir soft-delete)`,
      confirmLabel: "Sil",
    });
    if (!ok) return;
    try {
      await kurulApi.deleteMeeting(m.id);
      snackbar.success("Tutanak silindi.");
      void load();
    } catch (err) {
      snackbar.error(err instanceof ApiError ? err.message : "Tutanak silinemedi.");
    }
  };

  if (forbidden) {
    return (
      <Card elevation={1} className="flex flex-col items-center gap-2 p-10 text-center">
        <Icon name="lock" className="text-on-surface-variant" />
        <p className="text-body-medium text-on-surface-variant">
          Bu kurulun toplantı tutanaklarını görüntüleme yetkiniz yok.
        </p>
      </Card>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <p className="max-w-3xl text-body-medium text-on-surface-variant">
          {isDiscipline
            ? "Ödül-Disiplin Kurulu (md. 185-191) toplantı kararlarının karar defteri. " +
              "Dosya görüşme tutanağında seçilen dosyanın öğrenci bazlı resmî kararları " +
              "tutanağa otomatik derlenir; toplantılar T001, T002 biçiminde numaralanır."
            : "Onur Kurulu (md. 180-184) toplantı kararlarının karar defteri (md. 184). " +
              "Her tutanak gerekçeli karar + oy birliği/çoğunluğu (md. 191/206) + katılan " +
              "üyeler ile imzalı PDF olarak üretilir; toplantılar T001, T002 biçiminde numaralanır."}
        </p>
        {!creating && (
          <Button icon="add" onClick={() => setCreating(true)}>
            Yeni Toplantı
          </Button>
        )}
      </div>

      {creating && (
        <ToplantiForm
          councilType={councilType}
          onCreated={() => {
            setCreating(false);
            void load();
          }}
          onCancel={() => setCreating(false)}
        />
      )}

      {error && (
        <Card elevation={0} className="flex items-start gap-2 bg-error-container p-4">
          <Icon name="error" className="shrink-0 text-on-error-container" />
          <span className="text-body-small text-on-error-container">{error}</span>
        </Card>
      )}

      <Card elevation={1} className="overflow-hidden">
        {loading ? (
          <div className="space-y-2 p-4">
            <Skeleton className="h-10 w-full" />
            <Skeleton className="h-10 w-full" />
            <Skeleton className="h-10 w-full" />
          </div>
        ) : meetings.length === 0 ? (
          <div className="flex flex-col items-center gap-2 p-10 text-center">
            <Icon name="groups" className="text-on-surface-variant" />
            <p className="text-body-medium text-on-surface-variant">
              Bu kurul için henüz tutanak bulunmuyor.
            </p>
          </div>
        ) : (
          <table className="w-full text-body-medium">
            <thead>
              <tr className="border-b border-outline-variant text-label-large text-on-surface-variant">
                <th className="px-4 py-3 text-left">No</th>
                {isDiscipline && <th className="px-4 py-3 text-left">Tür</th>}
                {isDiscipline && <th className="px-4 py-3 text-left">Dosya</th>}
                {!isDiscipline && <th className="px-4 py-3 text-left">Toplantı</th>}
                {!isDiscipline && <th className="px-4 py-3 text-left">Dönem</th>}
                <th className="px-4 py-3 text-left">Tarih</th>
                <th className="px-4 py-3 text-left">Karar Esası</th>
                <th className="px-4 py-3 text-left">Katılımcı</th>
                <th className="px-4 py-3 text-right">İşlem</th>
              </tr>
            </thead>
            <tbody>
              {meetings.map((m) => (
                <tr
                  key={m.id}
                  className="border-b border-outline-variant last:border-0 hover:bg-on-surface/8"
                >
                  <td className="px-4 py-3 text-on-surface">{m.meeting_no_display}</td>
                  {isDiscipline && (
                    <td className="px-4 py-3 text-on-surface-variant">
                      {MINUTES_TYPE_TR[m.minutes_type]}
                    </td>
                  )}
                  {isDiscipline && (
                    <td className="px-4 py-3">
                      {m.discipline_case && m.discipline_case_no ? (
                        <Link
                          to={`/disiplin/${m.discipline_case}`}
                          className="text-primary underline-offset-2 hover:underline"
                        >
                          {m.discipline_case_no}
                        </Link>
                      ) : (
                        <span className="text-on-surface-variant">—</span>
                      )}
                    </td>
                  )}
                  {!isDiscipline && (
                    <td className="px-4 py-3 text-on-surface-variant">
                      {m.honor_meeting_kind_display ??
                        (m.honor_meeting_kind === "GENERAL_ASSEMBLY"
                          ? "Onur Genel Kurulu"
                          : "Onur Kurulu")}
                    </td>
                  )}
                  {!isDiscipline && (
                    <td className="px-4 py-3 text-on-surface-variant">{m.term_name ?? "—"}</td>
                  )}
                  <td className="px-4 py-3 text-on-surface">
                    {new Date(m.meeting_date).toLocaleDateString("tr-TR")}
                  </td>
                  <td className="px-4 py-3 text-on-surface-variant">
                    {DECISION_BASIS_TR[m.decision_basis]}
                  </td>
                  <td className="px-4 py-3 text-on-surface-variant">{m.attendees.length}</td>
                  <td className="px-4 py-3">
                    <div className="flex justify-end gap-1">
                      <Button
                        variant="text"
                        icon="picture_as_pdf"
                        onClick={() => void onDownload(m)}
                      >
                        Tutanak
                      </Button>
                      <Button
                        variant="text"
                        icon="delete"
                        onClick={() => void onDelete(m)}
                        aria-label="Tutanağı sil"
                      >
                        Sil
                      </Button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>
    </div>
  );
}
