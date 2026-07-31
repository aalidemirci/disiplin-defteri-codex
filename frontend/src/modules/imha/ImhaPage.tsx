// md. 157/7 İmha Aracı (F5-D2, tasarım §4.6) — OYS'de karşılığı YOK, sıfırdan yazıldı.
//
// Mevzuat: yazılı uyarı CEZA DEĞİLDİR (md. 157/7), sicile işlenmez, e-Okul'a
// girilmez (md. 157/7-ç); md. 157/7-d uyarınca uyarı belgeleri DERS YILI SONUNDA
// ya da öğrencinin NAKİL OLDUĞU TARİHTEN İTİBAREN 5 İŞ GÜNÜ içinde imha edilir.
//
// KIRMIZI ÇİZGİ: kurul kararlı (Dal B) dosyalar bu ekranda HİÇ GÖRÜNMEZ — kapsam
// yüklemi backend'dedir (selectors/purge.py), UI yalnız sonucu gösterir.
//
// Akış üç adımlıdır ve kısayolu yoktur:
//   1) Önizleme — neyin silineceğinin tam dökümü.
//   2) Tutanak (BİRİNCİ onay) — PDF üretilir + indirilir; jeton döner.
//   3) İmha (İKİNCİ onay) — jetonla uygulanır, GERİ ALINAMAZ.
// Seçim değişirse jeton düşer (tutanak artık o kapsamı temsil etmez).

import { useCallback, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";

import { useTabParam } from "../../hooks/useTabParam";
import { ApiError } from "../../lib/api";
import { saveBlob } from "../../lib/download";
import { formatDate } from "../../lib/format";
import Button from "../../ui/Button";
import Card from "../../ui/Card";
import { useConfirm } from "../../ui/ConfirmProvider";
import EmptyState from "../../ui/EmptyState";
import Icon from "../../ui/Icon";
import Select from "../../ui/Select";
import { SkeletonList } from "../../ui/Skeleton";
import { useSnackbar } from "../../ui/SnackbarProvider";
import Tabs, { tabPanelProps } from "../../ui/Tabs";
import type { TabItem } from "../../ui/Tabs";
import TextField from "../../ui/TextField";
import { imhaApi } from "./api";
import type {
  PurgeCaseItem,
  PurgeExecuteResult,
  PurgePreview,
  PurgeRecordResult,
  StudentPurgePreview,
} from "./api";

const TABS = ["yil-sonu", "nakil"] as const;
type TabKey = (typeof TABS)[number];

const TAB_ITEMS: TabItem[] = [
  { key: "yil-sonu", label: "Ders Yılı Sonu", icon: "event_available" },
  { key: "nakil", label: "Nakil (Tekil)", icon: "move_down" },
];

function errorMessage(err: unknown, fallback: string): string {
  return err instanceof ApiError ? err.message : fallback;
}

/** Kalıcı hata bandı — sonradan DOM'a girdiği için canlı bölge (role="alert"). */
function ErrorBanner({ message }: { message: string }) {
  return (
    <div
      role="alert"
      className="flex items-start gap-2 rounded-shape-sm bg-error-container px-4 py-3 text-body-medium text-on-error-container"
    >
      <Icon name="error" size="lg" />
      <span>{message}</span>
    </div>
  );
}

function InfoNote({ children }: { children: ReactNode }) {
  return (
    <Card elevation={0} className="flex items-start gap-3 bg-surface-container p-4">
      <Icon name="info" className="shrink-0 text-primary" />
      <p className="text-body-small text-on-surface-variant">{children}</p>
    </Card>
  );
}

/** Tutanak üretildikten sonra ikinci onayı bekleyen durum bandı. */
function RecordBanner({ filename, storedPath }: { filename: string; storedPath: string }) {
  return (
    <div
      role="status"
      className="flex items-start gap-2 rounded-shape-sm bg-tertiary-container px-4 py-3 text-body-medium text-on-tertiary-container"
    >
      <Icon name="task" size="lg" />
      <span>
        İmha tutanağı üretildi ve indirildi: <strong>{filename}</strong>. Program veri dizininde de
        saklandı ({storedPath}). Tutanağı imzalatıp dosyaladıktan sonra ikinci onayı verin — imha bu
        adımda GERİ ALINAMAZ biçimde uygulanır.
      </span>
    </div>
  );
}

function ResultCard({ result }: { result: PurgeExecuteResult }) {
  return (
    <Card elevation={1} className="space-y-2 p-4">
      <h3 className="text-title-medium text-on-surface">İmha tamamlandı</h3>
      <ul className="space-y-1 text-body-medium text-on-surface-variant">
        <li>İmha edilen dosya: {result.purged_cases}</li>
        <li>İmha edilen uyarı kaydı: {result.purged_warnings}</li>
        <li>İmha edilen evrak kütük satırı: {result.purged_documents}</li>
        <li>İmha edilen aşama kaydı: {result.purged_events}</li>
        <li>İmha edilen dosya eki: {result.purged_attachments}</li>
      </ul>
      {result.case_numbers.length > 0 && (
        <p className="text-body-small text-on-surface-variant">
          Dosya numaraları: {result.case_numbers.join(", ")}
        </p>
      )}
      <p className="text-body-small text-on-surface-variant">
        Kalıcı iz (imha tutanağı): {result.record_path}
      </p>
    </Card>
  );
}

// ---------------------------------------------------------------------------
// Ders yılı sonu (toplu) paneli
// ---------------------------------------------------------------------------
function YilSonuPanel({
  preview,
  loading,
  error,
  onReload,
}: {
  preview: PurgePreview | null;
  loading: boolean;
  error: string | null;
  onReload: () => void;
}) {
  const confirm = useConfirm();
  const snackbar = useSnackbar();
  const [selected, setSelected] = useState<number[]>([]);
  const [record, setRecord] = useState<PurgeRecordResult | null>(null);
  const [result, setResult] = useState<PurgeExecuteResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  const cases = useMemo(() => preview?.cases ?? [], [preview]);

  // Önizleme tazelendiğinde varsayılan seçim = tüm kapsam; jeton/sonuç sıfırlanır.
  useEffect(() => {
    setSelected(cases.map((c) => c.case_id));
    setRecord(null);
  }, [cases]);

  const toggle = (caseId: number) => {
    // Kapsam değişti → tutanak artık bu kapsamı temsil etmiyor, jeton düşer.
    setRecord(null);
    setSelected((prev) =>
      prev.includes(caseId) ? prev.filter((id) => id !== caseId) : [...prev, caseId],
    );
  };

  const selectedCases = cases.filter((c) => selected.includes(c.case_id));
  const totals = selectedCases.reduce(
    (acc, c) => ({
      warnings: acc.warnings + c.warning_count,
      documents: acc.documents + c.document_count,
    }),
    { warnings: 0, documents: 0 },
  );

  const produceRecord = async () => {
    const ok = await confirm({
      title: "İmha tutanağı üretilsin mi?",
      message:
        `${selectedCases.length} dosya, ${totals.warnings} uyarı kaydı ve ${totals.documents} ` +
        "evrak kütük satırı için md. 157/7-d imha tutanağı üretilecek. Tutanak, kayıtlar " +
        "silindikten sonra geriye kalan TEK izdir.",
      confirmLabel: "Tutanağı üret",
    });
    if (!ok) return;
    setBusy(true);
    setActionError(null);
    try {
      const produced = await imhaApi.recordForCases(selected);
      saveBlob(produced.blob, produced.filename);
      setRecord(produced);
      snackbar.success("İmha tutanağı üretildi ve indirildi.");
    } catch (e: unknown) {
      setActionError(errorMessage(e, "İmha tutanağı üretilemedi."));
    } finally {
      setBusy(false);
    }
  };

  const applyPurge = async () => {
    if (!record) return;
    const ok = await confirm({
      title: "İmha uygulansın mı? (geri alınamaz)",
      message:
        `${selectedCases.length} dosya ve bağlı tüm uyarı/evrak kayıtları KALICI olarak ` +
        "silinecek; bu işlem geri alınamaz. Öğrenci sicilleri silinmez. Devam edilsin mi?",
      confirmLabel: "İmha et",
    });
    if (!ok) return;
    setBusy(true);
    setActionError(null);
    try {
      const executed = await imhaApi.execute(record.token);
      setResult(executed);
      setRecord(null);
      snackbar.success("İmha tamamlandı.");
      onReload();
    } catch (e: unknown) {
      setActionError(errorMessage(e, "İmha uygulanamadı."));
    } finally {
      setBusy(false);
    }
  };

  if (loading) return <SkeletonList rows={4} />;
  if (error) return <ErrorBanner message={error} />;

  return (
    <div className="space-y-4">
      <InfoNote>
        md. 157/7-d: yazılı uyarı ve veli görüşmesine ilişkin belgeler{" "}
        <strong>ders yılı sonunda</strong> imha edilir. Aşağıda yalnızca{" "}
        <strong>yazılı uyarıyla kapanmış (Dal A)</strong> dosyalar listelenir; kurul kararlı (Dal B)
        dosyalar bu aracın kapsamı dışındadır ve listede yer almaz.
        {preview?.active_school_year_name && (
          <>
            {" "}
            Aktif ders yılı: <strong>{preview.active_school_year_name}</strong> (bitiş{" "}
            {formatDate(preview.active_school_year_end)}).
          </>
        )}
      </InfoNote>

      {result && <ResultCard result={result} />}
      {actionError && <ErrorBanner message={actionError} />}
      {record && <RecordBanner filename={record.filename} storedPath={record.storedPath} />}

      {cases.length === 0 ? (
        <EmptyState
          icon="delete_sweep"
          title="İmha edilecek uyarı dosyası yok"
          description="Yazılı uyarıyla kapanmış (Dal A) bir dosya bulunmuyor."
        />
      ) : (
        <>
          <Card elevation={1} className="overflow-x-auto p-0">
            <table className="w-full min-w-table border-collapse text-body-small">
              <caption className="sr-only">
                md. 157/7 kapsamında imha edilebilir disiplin dosyaları
              </caption>
              <thead>
                <tr className="border-b border-outline-variant text-left text-label-medium text-on-surface-variant">
                  <th className="p-3">Seç</th>
                  <th className="p-3">Dosya No</th>
                  <th className="p-3">Öğrenci(ler)</th>
                  <th className="p-3">Dilekçe</th>
                  <th className="p-3">Kapanış</th>
                  <th className="p-3">Silinecek kayıtlar</th>
                </tr>
              </thead>
              <tbody>
                {cases.map((item: PurgeCaseItem) => (
                  <tr key={item.case_id} className="border-t border-outline-variant/50">
                    <td className="p-3">
                      <label className="flex min-h-12 items-center">
                        <input
                          type="checkbox"
                          checked={selected.includes(item.case_id)}
                          onChange={() => toggle(item.case_id)}
                          className="h-5 w-5 accent-primary"
                          aria-label={`${item.case_no} dosyasını imha kapsamına al`}
                        />
                      </label>
                    </td>
                    <td className="p-3 text-on-surface">
                      {item.case_no}
                      {item.in_active_school_year && (
                        <span className="ml-2 rounded-shape-xs bg-tertiary-container px-2 py-0.5 text-label-small text-on-tertiary-container">
                          aktif ders yılı
                        </span>
                      )}
                    </td>
                    <td className="p-3">{item.students.join(", ") || "—"}</td>
                    <td className="p-3">{formatDate(item.petition_date)}</td>
                    <td className="p-3">{formatDate(item.closed_on)}</td>
                    <td className="p-3">
                      {item.warning_count} uyarı · {item.document_count} evrak ·{" "}
                      {item.attachment_count} ek
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Card>

          <p className="text-body-small text-on-surface-variant">
            Seçili: {selectedCases.length} dosya · {totals.warnings} uyarı kaydı ·{" "}
            {totals.documents} evrak kütük satırı.
          </p>

          <div className="flex flex-wrap gap-3">
            <Button
              variant="tonal"
              icon="picture_as_pdf"
              onClick={() => void produceRecord()}
              disabled={busy || selectedCases.length === 0}
            >
              1. Tutanağı üret ve indir
            </Button>
            <Button
              variant="filled"
              icon="delete_forever"
              onClick={() => void applyPurge()}
              disabled={busy || record === null}
            >
              2. İmhayı uygula
            </Button>
          </div>
          {record === null && selectedCases.length > 0 && (
            <p className="text-body-small text-on-surface-variant">
              İmha, tutanak üretilmeden uygulanamaz (md. 157/7-d — kalıcı iz zorunluluğu).
            </p>
          )}
        </>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Nakil (tekil) paneli
// ---------------------------------------------------------------------------
function NakilPanel({
  preview,
  loading,
  error,
  onReload,
}: {
  preview: PurgePreview | null;
  loading: boolean;
  error: string | null;
  onReload: () => void;
}) {
  const confirm = useConfirm();
  const snackbar = useSnackbar();
  const [studentId, setStudentId] = useState("");
  const [transferDate, setTransferDate] = useState("");
  const [detail, setDetail] = useState<StudentPurgePreview | null>(null);
  const [detailError, setDetailError] = useState<string | null>(null);
  const [record, setRecord] = useState<PurgeRecordResult | null>(null);
  const [result, setResult] = useState<PurgeExecuteResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  const options = (preview?.students ?? []).map((s) => ({
    value: String(s.student_id),
    label: `${s.full_name}${s.class_label ? ` — ${s.class_label}` : ""} (${s.warning_count} uyarı)`,
  }));

  useEffect(() => {
    if (!studentId) {
      setDetail(null);
      return;
    }
    let cancelled = false;
    setRecord(null);
    imhaApi
      .previewStudent(Number(studentId), transferDate || undefined)
      .then((data) => {
        if (cancelled) return;
        setDetail(data);
        setDetailError(null);
      })
      .catch((e: unknown) => {
        if (cancelled) return;
        setDetail(null);
        setDetailError(errorMessage(e, "Öğrenci imha önizlemesi yüklenemedi."));
      });
    return () => {
      cancelled = true;
    };
  }, [studentId, transferDate]);

  const produceRecord = async () => {
    if (!detail) return;
    const ok = await confirm({
      title: "İmha tutanağı üretilsin mi?",
      message:
        `${detail.student_name} için ${detail.totals.warnings} uyarı kaydı ve ` +
        `${detail.totals.documents} uyarı yazısı kütük satırı imha edilecek ` +
        `(${detail.totals.cases} dosya bütünüyle silinir). Önce tutanak üretilir.`,
      confirmLabel: "Tutanağı üret",
    });
    if (!ok) return;
    setBusy(true);
    setActionError(null);
    try {
      const produced = await imhaApi.recordForStudent(Number(studentId), transferDate || undefined);
      saveBlob(produced.blob, produced.filename);
      setRecord(produced);
      snackbar.success("İmha tutanağı üretildi ve indirildi.");
    } catch (e: unknown) {
      setActionError(errorMessage(e, "İmha tutanağı üretilemedi."));
    } finally {
      setBusy(false);
    }
  };

  const applyPurge = async () => {
    if (!record || !detail) return;
    const ok = await confirm({
      title: "İmha uygulansın mı? (geri alınamaz)",
      message:
        `${detail.student_name} adlı öğrencinin md. 157/7 uyarı izleri KALICI olarak ` +
        "silinecek; bu işlem geri alınamaz. Öğrenci sicili silinmez. Devam edilsin mi?",
      confirmLabel: "İmha et",
    });
    if (!ok) return;
    setBusy(true);
    setActionError(null);
    try {
      const executed = await imhaApi.execute(record.token);
      setResult(executed);
      setRecord(null);
      setDetail(null);
      setStudentId("");
      snackbar.success("İmha tamamlandı.");
      onReload();
    } catch (e: unknown) {
      setActionError(errorMessage(e, "İmha uygulanamadı."));
    } finally {
      setBusy(false);
    }
  };

  if (loading) return <SkeletonList rows={3} />;
  if (error) return <ErrorBanner message={error} />;

  return (
    <div className="space-y-4">
      <InfoNote>
        md. 157/7-d: öğrenci nakil olduğunda uyarı belgeleri{" "}
        <strong>nakil tarihinden itibaren 5 iş günü içinde</strong> imha edilir. Nakil tarihini
        girin — program son günü iş günü hesabıyla (resmî tatiller dahil) gösterir. Nakil tarihi
        öğrenci sicilinde tutulmaz; buraya elle girilir.
      </InfoNote>

      {result && <ResultCard result={result} />}
      {actionError && <ErrorBanner message={actionError} />}
      {detailError && <ErrorBanner message={detailError} />}
      {record && <RecordBanner filename={record.filename} storedPath={record.storedPath} />}

      {options.length === 0 ? (
        <EmptyState
          icon="move_down"
          title="İmha edilecek uyarı izi olan öğrenci yok"
          description="Yazılı uyarıyla kapanmış (Dal A) bir dosyada uyarı kaydı bulunmuyor."
        />
      ) : (
        <>
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
            <Select
              label="Öğrenci"
              options={options}
              placeholder="Öğrenci seçin"
              value={studentId}
              onChange={(e) => setStudentId(e.target.value)}
            />
            <TextField
              label="Nakil tarihi"
              type="date"
              value={transferDate}
              onChange={(e) => setTransferDate(e.target.value)}
              helperText="Boş bırakılabilir; girilirse +5 iş günü son günü hesaplanır."
            />
          </div>

          {detail && detail.purge_deadline && (
            <div
              role="status"
              className={`flex items-start gap-2 rounded-shape-sm px-4 py-3 text-body-medium ${
                detail.overdue
                  ? "bg-error-container text-on-error-container"
                  : "bg-secondary-container text-on-secondary-container"
              }`}
            >
              <Icon name={detail.overdue ? "warning" : "schedule"} size="lg" />
              <span>
                Yasal imha son günü: <strong>{formatDate(detail.purge_deadline)}</strong> (nakil
                tarihi + 5 iş günü — md. 157/7-d).{" "}
                {detail.overdue
                  ? "Süre GEÇTİ — imha gecikmiştir."
                  : `Kalan süre: ${detail.working_days_left} iş günü.`}
              </span>
            </div>
          )}

          {detail && detail.warnings.length === 0 && (
            <EmptyState
              icon="inbox"
              compact
              title="Bu öğrenci için imha edilebilir uyarı kaydı yok."
            />
          )}

          {detail && detail.warnings.length > 0 && (
            <>
              <Card elevation={1} className="overflow-x-auto p-0">
                <table className="w-full min-w-table border-collapse text-body-small">
                  <caption className="sr-only">
                    {detail.student_name} adlı öğrencinin imha edilebilir uyarı kayıtları
                  </caption>
                  <thead>
                    <tr className="border-b border-outline-variant text-left text-label-medium text-on-surface-variant">
                      <th className="p-3">Dosya No</th>
                      <th className="p-3">Uyarı Tarihi</th>
                      <th className="p-3">Uyarı Yazısı</th>
                      <th className="p-3">Kapsam</th>
                    </tr>
                  </thead>
                  <tbody>
                    {detail.warnings.map((w) => (
                      <tr key={w.warning_id} className="border-t border-outline-variant/50">
                        <td className="p-3 text-on-surface">{w.case_no}</td>
                        <td className="p-3">{formatDate(w.warning_date)}</td>
                        <td className="p-3">{w.warning_letter_count} kütük satırı</td>
                        <td className="p-3">
                          {w.whole_case_purgeable
                            ? "Dosyanın tamamı silinir"
                            : "Yalnız bu öğrencinin izleri silinir"}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </Card>

              <div className="flex flex-wrap gap-3">
                <Button
                  variant="tonal"
                  icon="picture_as_pdf"
                  onClick={() => void produceRecord()}
                  disabled={busy}
                >
                  1. Tutanağı üret ve indir
                </Button>
                <Button
                  variant="filled"
                  icon="delete_forever"
                  onClick={() => void applyPurge()}
                  disabled={busy || record === null}
                >
                  2. İmhayı uygula
                </Button>
              </div>
            </>
          )}
        </>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
export default function ImhaPage() {
  const [tab, setTab] = useTabParam<TabKey>("tab", TABS, "yil-sonu");
  const [preview, setPreview] = useState<PurgePreview | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    setLoading(true);
    imhaApi
      .preview()
      .then((data) => {
        setPreview(data);
        setError(null);
      })
      .catch((e: unknown) => setError(errorMessage(e, "İmha önizlemesi yüklenemedi.")))
      .finally(() => setLoading(false));
  }, []);
  useEffect(load, [load]);

  return (
    <div className="space-y-6">
      <div className="dd-page-header">
        <div>
          <h1 className="dd-page-title">İmha Aracı</h1>
          <p className="dd-page-description">
            Yazılı uyarı bir disiplin cezası değildir (md. 157/7) ve öğrencinin siciline işlenmez;
            bu nedenle uyarı belgeleri ders yılı sonunda ya da öğrencinin nakil tarihinden itibaren
            5 iş günü içinde imha edilir (md. 157/7-d). Kurul kararlı dosyalar imha edilemez.
          </p>
        </div>
      </div>

      <Tabs
        items={TAB_ITEMS}
        active={tab}
        onChange={(key) => setTab(key as TabKey)}
        ariaLabel="İmha türü"
        idBase="imha"
      />

      <div {...tabPanelProps("imha", tab)} className="space-y-6">
        {tab === "yil-sonu" && (
          <YilSonuPanel preview={preview} loading={loading} error={error} onReload={load} />
        )}
        {tab === "nakil" && (
          <NakilPanel preview={preview} loading={loading} error={error} onReload={load} />
        )}
      </div>
    </div>
  );
}
