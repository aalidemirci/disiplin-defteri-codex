// Ayarlar sayfası (F4-D4) — OYS'de birebir karşılığı YOK, sıfırdan yazıldı.
// Üç sekme: ders yılları (liste + oluşturma + tek-aktif kuralıyla aktifleştirme),
// tatiller (aktif yılın tatilleri + elle ekleme/silme + resmî tatil yükleme) ve
// okul bilgileri (resmî evrak antedini besleyen kurum künyesi). Altta disiplin
// karar tipleri ekranına bağlantı kartı. Authsuz program: rol/izin kapısı yoktur.

import { useCallback, useEffect, useState } from "react";
import type { FormEvent, ReactNode } from "react";

import { useTabParam } from "../../hooks/useTabParam";
import { ApiError } from "../../lib/api";
import { formatDate } from "../../lib/format";
import { parseApiFieldErrors } from "../../lib/formErrors";
import Button from "../../ui/Button";
import Card from "../../ui/Card";
import { useConfirm } from "../../ui/ConfirmProvider";
import HubFeatureCard from "../../ui/HubFeatureCard";
import Icon from "../../ui/Icon";
import Select from "../../ui/Select";
import { SkeletonList } from "../../ui/Skeleton";
import { useSnackbar } from "../../ui/SnackbarProvider";
import Tabs, { tabPanelProps } from "../../ui/Tabs";
import type { TabItem } from "../../ui/Tabs";
import TextField from "../../ui/TextField";
import GuvenlikAyarlari from "../guvenlik/GuvenlikAyarlari";
import UpdatePanel from "../guncelleme/UpdatePanel";
import { HOLIDAY_KIND_TR, okulApi } from "../okul/api";
import type { Holiday, HolidayKind, SchoolConfig, SchoolTerm, SchoolYear } from "../okul/api";

const TABS = ["ders-yillari", "tatiller", "okul", "guvenlik", "guncelleme"] as const;
type TabKey = (typeof TABS)[number];

const TAB_ITEMS: TabItem[] = [
  { key: "ders-yillari", label: "Ders Yılları", icon: "calendar_month" },
  { key: "tatiller", label: "Tatiller", icon: "beach_access" },
  { key: "okul", label: "Okul Bilgileri", icon: "apartment" },
  { key: "guvenlik", label: "Güvenlik", icon: "lock" },
  { key: "guncelleme", label: "Güncelleme", icon: "system_update" },
];

/** Backend hatasını alan-bazlı haritaya VEYA genel hata bandına dağıtır. */
function splitApiError(
  err: unknown,
  fallback: string,
): { fields: Record<string, string>; message: string | null } {
  const fields = parseApiFieldErrors(err) ?? {};
  if (Object.keys(fields).length > 0) return { fields, message: null };
  return { fields: {}, message: err instanceof ApiError ? err.message : fallback };
}

/**
 * Sayfa genelinde tekrar eden M3 hata bandı. `role="alert"`: bant yükleme/kaydetme
 * başarısız olunca sonradan DOM'a girer, canlı bölge olmadan ekran okuyucu susardı.
 */
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

/** Küçük bilgi kartı (mevzuat/kullanım notu). */
function InfoNote({ children }: { children: ReactNode }) {
  return (
    <Card elevation={0} className="flex items-start gap-3 bg-surface-container p-4">
      <Icon name="info" className="shrink-0 text-primary" />
      <p className="text-body-small text-on-surface-variant">{children}</p>
    </Card>
  );
}

export default function AyarlarPage() {
  const [tab, setTab] = useTabParam<TabKey>("tab", TABS, "ders-yillari");

  // Ders yılları SAYFA düzeyinde tutulur: hem "Ders Yılları" sekmesi hem de
  // tatil filtresi (aktif yıl) aynı listeden beslenir, aktivasyon sonrası ikisi
  // birden tazelenir.
  const [years, setYears] = useState<SchoolYear[]>([]);
  const [yearsLoading, setYearsLoading] = useState(true);
  const [yearsError, setYearsError] = useState<string | null>(null);

  const loadYears = useCallback(() => {
    setYearsLoading(true);
    okulApi
      .listSchoolYears()
      .then((rows) => {
        setYears(rows);
        setYearsError(null);
      })
      .catch((e: unknown) =>
        setYearsError(e instanceof ApiError ? e.message : "Ders yılları yüklenemedi."),
      )
      .finally(() => setYearsLoading(false));
  }, []);
  useEffect(loadYears, [loadYears]);

  const activeYear = years.find((y) => y.is_active) ?? null;

  // Okul adı yalnız Güvenlik sekmesi için: kurtarma anahtarı çıktısında hangi
  // okula ait olduğu yazar. Okunamazsa boş geçilir (çıktı yine üretilir).
  const [okulAdi, setOkulAdi] = useState("");
  useEffect(() => {
    let iptal = false;
    okulApi
      .getSchoolConfig()
      .then((c) => {
        if (!iptal) setOkulAdi(c.school_name);
      })
      .catch(() => undefined);
    return () => {
      iptal = true;
    };
  }, []);

  return (
    <div className="space-y-6">
      <div className="dd-page-header">
        <div>
          <h1 className="dd-page-title">Ayarlar</h1>
          <p className="dd-page-description">
            Ders yılı, tatil takvimi ve okul künyesi burada yönetilir. Ders yılı ve tatiller yasal
            süre hesabını (iş günü) doğrudan etkiler; okul künyesi resmî evrak antedinde kullanılır.
          </p>
        </div>
      </div>

      <Tabs
        items={TAB_ITEMS}
        active={tab}
        onChange={(key) => setTab(key as TabKey)}
        ariaLabel="Ayarlar bölümleri"
        idBase="ayarlar"
      />

      <div {...tabPanelProps("ayarlar", tab)} className="space-y-6">
        {tab === "ders-yillari" && (
          <DersYillariPanel
            years={years}
            loading={yearsLoading}
            error={yearsError}
            onReload={loadYears}
          />
        )}
        {tab === "tatiller" && (
          <TatillerPanel activeYear={activeYear} yearsLoading={yearsLoading} />
        )}
        {tab === "okul" && <OkulBilgileriPanel />}
        {tab === "guvenlik" && <GuvenlikAyarlari okulAdi={okulAdi} />}
        {tab === "guncelleme" && <UpdatePanel />}
      </div>

      <section className="space-y-3">
        <h2 className="text-title-medium text-on-surface">Diğer ayarlar</h2>
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
          <HubFeatureCard
            to="/ayarlar/sinif-sorumlulari"
            icon="group_work"
            title="Sınıf sorumluları"
            description="Şube bazında sınıf öğretmeni, müdür yardımcısı ve rehber öğretmeni eşleştirin."
          />
          <HubFeatureCard
            to="/disiplin/karar-tipleri"
            icon="gavel"
            title="Disiplin karar tipleri"
            description="Kınama, uzaklaştırma vb. karar tiplerinin tanımları ve metinleri."
          />
          {/* Kurulum tamamlandıktan sonra sihirbaza gezinilebilir tek yol burasıdır
              (menüde yer almaz); adımları gözden geçirmek isteyen kullanıcı sıkışmasın. */}
          <HubFeatureCard
            to="/kurulum"
            icon="checklist"
            title="Kurulum sihirbazı"
            description="Okul bilgileri, ders yılı ve tatil takvimi adımlarını yeniden gözden geçirin."
          />
          {/* Yıl devri ve imha yılda bir koşulan, geri alınamaz işlemler — üst
              menüye konmaz, bilinçli olarak buradan açılır. */}
          <HubFeatureCard
            to="/yil-devri"
            icon="calendar_add_on"
            title="Yıl devri"
            description="Yeni ders yılına geçiş: yıl tanımı, tatiller, kurul ve öğrenci sınıflarının yükseltilmesi."
          />
          <HubFeatureCard
            to="/imha"
            icon="delete_forever"
            title="Uyarı belgesi imhası"
            description="Müdür uyarısı kayıtlarının md. 157/7 gereği imhası; tutanak üretilir, kayıtlar geri alınamaz."
          />
        </div>
      </section>
    </div>
  );
}

// ---------------------------------------------------------------------------
// 1. Ders yılları
// ---------------------------------------------------------------------------

function DersYillariPanel({
  years,
  loading,
  error,
  onReload,
}: {
  years: SchoolYear[];
  loading: boolean;
  error: string | null;
  onReload: () => void;
}) {
  return (
    <div className="space-y-6">
      {error && <ErrorBanner message={error} />}

      <Card elevation={1} className="p-6">
        <p className="text-title-medium text-on-surface">Ders yılları</p>
        <p className="mt-1 text-body-medium text-on-surface-variant">
          Aynı anda yalnız BİR ders yılı aktif olabilir. Kurul, tutanak ve disiplin kayıtları aktif
          yıla bağlanır.
        </p>

        {loading ? (
          <SkeletonList rows={3} className="mt-4" />
        ) : years.length === 0 ? (
          <p className="mt-4 text-body-medium text-on-surface-variant">
            Henüz ders yılı tanımlanmadı. Aşağıdaki formdan ilk yılı oluşturun.
          </p>
        ) : (
          <ul className="mt-4 divide-y divide-outline-variant/50">
            {years.map((y) => (
              <SchoolYearRow key={y.id} year={y} onChanged={onReload} />
            ))}
          </ul>
        )}
      </Card>

      <SchoolYearCreateCard onCreated={onReload} />
    </div>
  );
}

function SchoolYearRow({ year, onChanged }: { year: SchoolYear; onChanged: () => void }) {
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [editingTerms, setEditingTerms] = useState(false);
  const snackbar = useSnackbar();
  const confirm = useConfirm();

  const activate = async () => {
    const ok = await confirm({
      title: "Ders yılını aktifleştir",
      message: `'${year.name}' aktif ders yılı yapılsın mı? Aynı anda yalnız bir yıl aktif olabilir; diğer yıllar pasife çekilir.`,
      confirmLabel: "Aktifleştir",
    });
    if (!ok) return;
    setBusy(true);
    setErr(null);
    try {
      await okulApi.activateSchoolYear(year.id);
      snackbar.success(`'${year.name}' aktif ders yılı oldu.`);
      onChanged();
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : "Ders yılı aktifleştirilemedi.");
      setBusy(false);
    }
  };

  return (
    <li className="space-y-3 py-3">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="min-w-0">
          <p className="flex flex-wrap items-center gap-2 text-body-large text-on-surface">
            {year.name}
            {year.is_active && (
              <span className="inline-flex items-center gap-1 rounded-shape-xl bg-primary-container px-2 py-0.5 text-label-small text-on-primary-container">
                <Icon name="check_circle" size="sm" />
                Aktif
              </span>
            )}
          </p>
          <p className="text-label-small text-on-surface-variant">
            {formatDate(year.start_date)} – {formatDate(year.end_date)}
          </p>
          {err && (
            <p role="alert" className="text-label-small text-error">
              {err}
            </p>
          )}
        </div>
        <div className="flex gap-2">
          <Button
            variant="text"
            icon="date_range"
            onClick={() => setEditingTerms((value) => !value)}
          >
            Dönemler
          </Button>
          {!year.is_active && (
            <Button variant="text" icon="play_circle" onClick={activate} disabled={busy}>
              Aktifleştir
            </Button>
          )}
        </div>
      </div>
      {editingTerms && <SchoolTermEditor year={year} />}
    </li>
  );
}

function SchoolTermEditor({ year }: { year: SchoolYear }) {
  const snackbar = useSnackbar();
  const [terms, setTerms] = useState<SchoolTerm[]>([]);
  const [firstEnd, setFirstEnd] = useState("");
  const [secondStart, setSecondStart] = useState("");
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    okulApi
      .listSchoolTerms(year.id)
      .then((rows) => {
        setTerms(rows);
        setFirstEnd(rows.find((term) => term.sequence === 1)?.end_date ?? "");
        setSecondStart(rows.find((term) => term.sequence === 2)?.start_date ?? "");
      })
      .catch((err: unknown) =>
        setError(err instanceof ApiError ? err.message : "Dönemler yüklenemedi."),
      )
      .finally(() => setBusy(false));
  }, [year.id]);

  const save = async () => {
    if (!firstEnd || !secondStart) {
      setError("Her iki dönem sınır tarihi de seçilmelidir.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const rows = await okulApi.configureSchoolTerms(year.id, {
        first_term_end: firstEnd,
        second_term_start: secondStart,
      });
      setTerms(rows);
      snackbar.success(`${year.name} dönem takvimi kaydedildi.`);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Dönemler kaydedilemedi.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="rounded-shape-sm bg-surface-container-low p-4">
      <p className="text-body-small text-on-surface-variant">
        1. dönem ders yılı başlangıcında, 2. dönem ders yılı bitişinde sonlanır. Aradaki boşluk
        yarıyıl tatilidir.
      </p>
      <div className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-2">
        <TextField
          label="1. dönem bitişi"
          type="date"
          value={firstEnd}
          onChange={(event) => setFirstEnd(event.target.value)}
        />
        <TextField
          label="2. dönem başlangıcı"
          type="date"
          value={secondStart}
          onChange={(event) => setSecondStart(event.target.value)}
        />
      </div>
      {terms.length === 2 && (
        <p className="mt-2 text-label-small text-on-surface-variant">
          {formatDate(terms[0].start_date)} – {formatDate(terms[0].end_date)} ·{" "}
          {formatDate(terms[1].start_date)} – {formatDate(terms[1].end_date)}
        </p>
      )}
      {error && <p className="mt-2 text-label-small text-error">{error}</p>}
      <div className="mt-3 flex justify-end">
        <Button variant="tonal" onClick={() => void save()} disabled={busy}>
          {busy ? "Kaydediliyor…" : "Dönemleri kaydet"}
        </Button>
      </div>
    </div>
  );
}

function SchoolYearCreateCard({ onCreated }: { onCreated: () => void }) {
  const [name, setName] = useState("");
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const [firstTermEnd, setFirstTermEnd] = useState("");
  const [secondTermStart, setSecondTermStart] = useState("");
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const snackbar = useSnackbar();

  const submit = async (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setFormError(null);
    // İstemci tarafı yalnız BOŞ alanları yakalar; tarih sırası doğrulaması
    // backend'in tek doğruluk kaynağıdır (400 → alan altında gösterilir).
    const missing: Record<string, string> = {};
    if (!name.trim()) missing.name = "Ders yılı adı yazılmalıdır.";
    if (!startDate) missing.start_date = "Başlangıç tarihi seçilmelidir.";
    if (!endDate) missing.end_date = "Bitiş tarihi seçilmelidir.";
    if (!firstTermEnd) missing.first_term_end = "1. dönem bitişi seçilmelidir.";
    if (!secondTermStart) missing.second_term_start = "2. dönem başlangıcı seçilmelidir.";
    if (Object.keys(missing).length > 0) {
      setFieldErrors(missing);
      return;
    }
    setFieldErrors({});
    setBusy(true);
    try {
      const created = await okulApi.createSchoolYear({
        name: name.trim(),
        start_date: startDate,
        end_date: endDate,
      });
      await okulApi.configureSchoolTerms(created.id, {
        first_term_end: firstTermEnd,
        second_term_start: secondTermStart,
      });
      snackbar.success("Ders yılı oluşturuldu.");
      setName("");
      setStartDate("");
      setEndDate("");
      setFirstTermEnd("");
      setSecondTermStart("");
      onCreated();
    } catch (err) {
      const split = splitApiError(err, "Ders yılı oluşturulamadı.");
      setFieldErrors(split.fields);
      setFormError(split.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card elevation={1} className="p-6">
      <p className="text-title-medium text-on-surface">Yeni ders yılı</p>
      <p className="mt-1 text-body-medium text-on-surface-variant">
        Yeni yıl PASİF doğar; hazır olduğunuzda listeden aktifleştirirsiniz.
      </p>
      <form className="mt-4 space-y-4" onSubmit={submit} noValidate>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
          <TextField
            label="Ders yılı adı"
            required
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="2026-2027"
            error={fieldErrors.name}
          />
          <TextField
            label="Başlangıç"
            required
            type="date"
            value={startDate}
            onChange={(e) => setStartDate(e.target.value)}
            error={fieldErrors.start_date}
          />
          <TextField
            label="Bitiş"
            required
            type="date"
            value={endDate}
            onChange={(e) => setEndDate(e.target.value)}
            error={fieldErrors.end_date}
          />
        </div>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <TextField
            label="1. dönem bitişi"
            required
            type="date"
            value={firstTermEnd}
            onChange={(event) => setFirstTermEnd(event.target.value)}
            error={fieldErrors.first_term_end}
          />
          <TextField
            label="2. dönem başlangıcı"
            required
            type="date"
            value={secondTermStart}
            onChange={(event) => setSecondTermStart(event.target.value)}
            error={fieldErrors.second_term_start}
          />
        </div>
        {formError && <ErrorBanner message={formError} />}
        <div className="flex justify-end">
          <Button type="submit" icon="add" disabled={busy}>
            {busy ? "Oluşturuluyor…" : "Ders yılı oluştur"}
          </Button>
        </div>
      </form>
    </Card>
  );
}

// ---------------------------------------------------------------------------
// 2. Tatiller
// ---------------------------------------------------------------------------

const KIND_CHIP: Record<HolidayKind, string> = {
  OFFICIAL: "bg-primary-container text-on-primary-container",
  RELIGIOUS: "bg-tertiary-container text-on-tertiary-container",
  OTHER: "bg-secondary-container text-on-secondary-container",
};

/** Tatil kaydı ders yılına BAĞLANMAZ; yıl eşleşmesi tarih kapsamasıyla bulunur. */
function overlapsYear(holiday: Holiday, year: SchoolYear | null): boolean {
  if (year === null) return true;
  return holiday.start_date <= year.end_date && holiday.end_date >= year.start_date;
}

function TatillerPanel({
  activeYear,
  yearsLoading,
}: {
  activeYear: SchoolYear | null;
  yearsLoading: boolean;
}) {
  const [holidays, setHolidays] = useState<Holiday[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showAll, setShowAll] = useState(false);
  const [seedBusy, setSeedBusy] = useState(false);
  const [seedInfo, setSeedInfo] = useState<string | null>(null);
  const snackbar = useSnackbar();

  const load = useCallback(() => {
    setLoading(true);
    okulApi
      .listHolidays()
      .then((rows) => {
        setHolidays(rows);
        setError(null);
      })
      .catch((e: unknown) => setError(e instanceof ApiError ? e.message : "Tatiller yüklenemedi."))
      .finally(() => setLoading(false));
  }, []);
  useEffect(load, [load]);

  const seed = async () => {
    setSeedBusy(true);
    setError(null);
    try {
      const result = await okulApi.seedHolidays();
      setSeedInfo(`${result.created} tatil eklendi, ${result.skipped} kayıt zaten vardı.`);
      snackbar.success(
        `Resmî tatiller yüklendi: ${result.created} yeni, ${result.skipped} mevcut.`,
      );
      load();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Resmî tatiller yüklenemedi.");
    } finally {
      setSeedBusy(false);
    }
  };

  const visible = showAll ? holidays : holidays.filter((h) => overlapsYear(h, activeYear));

  return (
    <div className="space-y-6">
      {error && <ErrorBanner message={error} />}

      <InfoNote>
        Buraya YALNIZ resmî ve idari tatiller girilir; ara tatil / yarıyıl tatili{" "}
        <strong>girilmez</strong> — o günlerde memur çalışır ve yasal disiplin süreleri işlemeye
        devam eder. Dini bayramlar Diyanet ilanından önce <strong>tahmini</strong> olarak yüklenir,
        gerekirse silip yeniden girebilirsiniz.
      </InfoNote>

      <Card elevation={1} className="p-6">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <p className="text-title-medium text-on-surface">Tatil takvimi</p>
            <p className="mt-1 text-body-medium text-on-surface-variant">
              {yearsLoading
                ? "Aktif ders yılı çözülüyor…"
                : activeYear
                  ? `Aktif ders yılı: ${activeYear.name} (${formatDate(activeYear.start_date)} – ${formatDate(activeYear.end_date)})`
                  : "Aktif ders yılı yok — tüm tatiller listeleniyor."}
            </p>
          </div>
          <Button variant="tonal" icon="event_repeat" onClick={seed} disabled={seedBusy}>
            {seedBusy ? "Yükleniyor…" : "Resmî tatilleri yükle"}
          </Button>
        </div>

        {seedInfo && <p className="mt-3 text-body-small text-on-surface-variant">{seedInfo}</p>}

        {activeYear && (
          <label className="mt-3 flex min-h-12 items-center gap-3 text-body-medium text-on-surface">
            <input
              type="checkbox"
              checked={showAll}
              onChange={(e) => setShowAll(e.target.checked)}
              className="h-5 w-5 accent-primary"
            />
            Aktif yıl dışındaki tatilleri de göster
          </label>
        )}

        {loading ? (
          <SkeletonList rows={4} className="mt-4" />
        ) : visible.length === 0 ? (
          <p className="mt-4 text-body-medium text-on-surface-variant">
            Listelenecek tatil yok. Resmî tatilleri yükleyebilir veya aşağıdan elle
            ekleyebilirsiniz.
          </p>
        ) : (
          <ul className="mt-4 divide-y divide-outline-variant/50">
            {visible.map((h) => (
              <HolidayRow key={h.id} holiday={h} onRemoved={load} />
            ))}
          </ul>
        )}
      </Card>

      <HolidayCreateCard onCreated={load} />
    </div>
  );
}

function HolidayRow({ holiday, onRemoved }: { holiday: Holiday; onRemoved: () => void }) {
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const snackbar = useSnackbar();
  const confirm = useConfirm();

  const remove = async () => {
    const ok = await confirm({
      title: "Tatili sil",
      message: `'${holiday.name}' tatili silinsin mi? İş günü hesabı bu tarihten sonra o günleri çalışma günü sayar.`,
      confirmLabel: "Sil",
    });
    if (!ok) return;
    setBusy(true);
    setErr(null);
    try {
      await okulApi.deleteHoliday(holiday.id);
      snackbar.success("Tatil silindi.");
      onRemoved();
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : "Tatil silinemedi.");
      setBusy(false);
    }
  };

  const sameDay = holiday.start_date === holiday.end_date;

  return (
    <li className="flex flex-wrap items-center justify-between gap-3 py-3">
      <div className="min-w-0">
        <p className="flex flex-wrap items-center gap-2 text-body-medium text-on-surface">
          <span
            className={`inline-flex items-center rounded-shape-xl px-2 py-0.5 text-label-small ${KIND_CHIP[holiday.kind]}`}
          >
            {HOLIDAY_KIND_TR[holiday.kind]}
          </span>
          {holiday.name}
          {holiday.is_estimated && (
            <span className="inline-flex items-center rounded-shape-xl bg-surface-container-highest px-2 py-0.5 text-label-small text-on-surface-variant">
              tahmini
            </span>
          )}
        </p>
        <p className="text-label-small text-on-surface-variant">
          {sameDay
            ? formatDate(holiday.start_date)
            : `${formatDate(holiday.start_date)} – ${formatDate(holiday.end_date)}`}
        </p>
        {err && (
          <p role="alert" className="text-label-small text-error">
            {err}
          </p>
        )}
      </div>
      <Button variant="text" icon="delete" onClick={remove} disabled={busy}>
        Sil
      </Button>
    </li>
  );
}

function HolidayCreateCard({ onCreated }: { onCreated: () => void }) {
  const [name, setName] = useState("");
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const [kind, setKind] = useState<HolidayKind>("OFFICIAL");
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const snackbar = useSnackbar();

  const submit = async (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setFormError(null);
    const missing: Record<string, string> = {};
    if (!name.trim()) missing.name = "Tatil adı yazılmalıdır.";
    if (!startDate) missing.start_date = "Başlangıç tarihi seçilmelidir.";
    if (!endDate) missing.end_date = "Bitiş tarihi seçilmelidir.";
    if (Object.keys(missing).length > 0) {
      setFieldErrors(missing);
      return;
    }
    setFieldErrors({});
    setBusy(true);
    try {
      await okulApi.createHoliday({
        name: name.trim(),
        start_date: startDate,
        end_date: endDate,
        kind,
      });
      snackbar.success("Tatil eklendi.");
      setName("");
      setStartDate("");
      setEndDate("");
      setKind("OFFICIAL");
      onCreated();
    } catch (err) {
      const split = splitApiError(err, "Tatil eklenemedi.");
      setFieldErrors(split.fields);
      setFormError(split.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card elevation={1} className="p-6">
      <p className="text-title-medium text-on-surface">Tatil ekle</p>
      <p className="mt-1 text-body-medium text-on-surface-variant">
        Tek günlük tatilde başlangıç ve bitiş aynı tarih seçilir.
      </p>
      <form className="mt-4 space-y-4" onSubmit={submit} noValidate>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <TextField
            label="Tatil adı"
            required
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="29 Ekim Cumhuriyet Bayramı"
            error={fieldErrors.name}
          />
          <Select
            label="Tür"
            value={kind}
            onChange={(e) => setKind(e.target.value as HolidayKind)}
            options={(Object.entries(HOLIDAY_KIND_TR) as [HolidayKind, string][]).map(
              ([value, label]) => ({ value, label }),
            )}
            error={fieldErrors.kind}
          />
          <TextField
            label="Başlangıç"
            required
            type="date"
            value={startDate}
            onChange={(e) => setStartDate(e.target.value)}
            error={fieldErrors.start_date}
          />
          <TextField
            label="Bitiş"
            required
            type="date"
            value={endDate}
            onChange={(e) => setEndDate(e.target.value)}
            error={fieldErrors.end_date}
          />
        </div>
        {formError && <ErrorBanner message={formError} />}
        <div className="flex justify-end">
          <Button type="submit" icon="add" disabled={busy}>
            {busy ? "Ekleniyor…" : "Tatili ekle"}
          </Button>
        </div>
      </form>
    </Card>
  );
}

// ---------------------------------------------------------------------------
// 3. Okul bilgileri (kurum künyesi)
// ---------------------------------------------------------------------------

function OkulBilgileriPanel() {
  const [config, setConfig] = useState<SchoolConfig | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [schoolName, setSchoolName] = useState("");
  const [province, setProvince] = useState("");
  const [district, setDistrict] = useState("");
  const [principalName, setPrincipalName] = useState("");
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const snackbar = useSnackbar();

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    okulApi
      .getSchoolConfig()
      .then((data) => {
        if (cancelled) return;
        setConfig(data);
        setSchoolName(data.school_name);
        setProvince(data.province);
        setDistrict(data.district);
        setPrincipalName(data.principal_name);
        setError(null);
      })
      .catch((e: unknown) => {
        if (cancelled) return;
        setError(e instanceof ApiError ? e.message : "Okul bilgileri yüklenemedi.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const submit = async (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setError(null);
    if (!schoolName.trim()) {
      setFieldErrors({ school_name: "Okul adı yazılmalıdır (evrak antedinde görünür)." });
      return;
    }
    setFieldErrors({});
    setBusy(true);
    try {
      const saved = await okulApi.updateSchoolConfig({
        school_name: schoolName.trim(),
        province: province.trim(),
        district: district.trim(),
        principal_name: principalName.trim(),
      });
      setConfig(saved);
      snackbar.success("Okul bilgileri kaydedildi.");
    } catch (err) {
      const split = splitApiError(err, "Okul bilgileri kaydedilemedi.");
      setFieldErrors(split.fields);
      setError(split.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-6">
      {error && <ErrorBanner message={error} />}

      <InfoNote>
        Bu bilgiler <strong>resmî evrak antedinde</strong> kullanılır: üretilen tüm tebliğ, tutanak
        ve karar belgelerinin başlığında okul adı, il/ilçe ve müdür adı buradan basılır. Yanlış
        girilirse çıktı belgeler de yanlış olur.
      </InfoNote>

      <Card elevation={1} className="p-6">
        <p className="text-title-medium text-on-surface">Okul bilgileri</p>
        {loading ? (
          <SkeletonList rows={4} className="mt-4" />
        ) : (
          <form className="mt-4 space-y-4" onSubmit={submit} noValidate>
            <TextField
              label="Okul adı"
              required
              value={schoolName}
              onChange={(e) => setSchoolName(e.target.value)}
              placeholder="Örnek Anadolu Lisesi"
              error={fieldErrors.school_name}
            />
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              <TextField
                label="İl"
                value={province}
                onChange={(e) => setProvince(e.target.value)}
                error={fieldErrors.province}
              />
              <TextField
                label="İlçe"
                value={district}
                onChange={(e) => setDistrict(e.target.value)}
                error={fieldErrors.district}
              />
            </div>
            <TextField
              label="Okul müdürü"
              value={principalName}
              onChange={(e) => setPrincipalName(e.target.value)}
              helperText="Belgelerin imza bloğunda görünür."
              error={fieldErrors.principal_name}
            />
            <div className="flex flex-wrap items-center justify-between gap-3">
              <p className="text-label-small text-on-surface-variant">
                Kurulum durumu: {config?.setup_completed ? "tamamlandı" : "tamamlanmadı"}
              </p>
              <Button type="submit" icon="save" disabled={busy}>
                {busy ? "Kaydediliyor…" : "Kaydet"}
              </Button>
            </div>
          </form>
        )}
      </Card>
    </div>
  );
}
