import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { ApiError } from "../../lib/api";
import { formatDate, formatNumber, todayIso } from "../../lib/format";
import Button from "../../ui/Button";
import EmptyState from "../../ui/EmptyState";
import Icon from "../../ui/Icon";
import { SkeletonList } from "../../ui/Skeleton";
import { deadlinesApi, disiplinApi, SEVERITY_ORDER } from "../disiplin/api";
import type { CaseStage, DeadlineItem, DeadlineSeverity, DisciplineCase } from "../disiplin/api";
import { okulApi } from "../okul/api";
import type { SetupStatus } from "../okul/api";

const SEVERITY_STYLE: Record<
  DeadlineSeverity,
  { row: string; badge: string; icon: string; heading: string }
> = {
  GEÇTİ: {
    row: "border-error/20 bg-error-container/60 text-on-error-container",
    badge: "bg-error text-on-error",
    icon: "priority_high",
    heading: "Süresi geçmiş",
  },
  YAKLAŞIYOR: {
    row: "border-tertiary/20 bg-tertiary-container/60 text-on-tertiary-container",
    badge: "bg-tertiary text-on-tertiary",
    icon: "schedule",
    heading: "Süresi yaklaşan",
  },
  BİLGİ: {
    row: "border-outline-variant bg-surface-container-lowest text-on-surface",
    badge: "bg-secondary-container text-on-secondary-container",
    icon: "info",
    heading: "Bilgi",
  },
};

const STAGE_GROUPS: Array<{
  key: string;
  label: string;
  color: string;
  stages: CaseStage[];
}> = [
  { key: "inceleme", label: "İnceleme", color: "bg-primary", stages: ["PETITION"] },
  {
    key: "rehberlik",
    label: "Rehberlik",
    color: "bg-secondary",
    stages: ["GUIDANCE_REFERRED", "GUIDANCE_RETURNED"],
  },
  {
    key: "karar",
    label: "Karar süreci",
    color: "bg-tertiary",
    stages: ["DECIDED", "COMMITTEE_DONE"],
  },
  { key: "kapali", label: "Tamamlanan", color: "bg-success", stages: ["CLOSED"] },
];

const DONUT_COLORS = [
  "rgb(var(--md-primary))",
  "rgb(var(--md-secondary))",
  "rgb(var(--md-tertiary))",
  "rgb(var(--dd-success))",
];

function donutBackground(values: number[], total: number): string {
  let cursor = 0;
  const stops = values.map((value, index) => {
    const start = cursor;
    cursor += (value / total) * 100;
    return `${DONUT_COLORS[index]} ${start}% ${cursor}%`;
  });
  return `conic-gradient(${stops.join(", ")})`;
}

function greeting(): string {
  const hour = new Date().getHours();
  if (hour < 11) return "Günaydın";
  if (hour < 18) return "İyi günler";
  return "İyi akşamlar";
}

function longDate(): string {
  return new Intl.DateTimeFormat("tr-TR", {
    weekday: "long",
    day: "numeric",
    month: "long",
    year: "numeric",
  }).format(new Date());
}

export default function PanelPage() {
  const [items, setItems] = useState<DeadlineItem[]>([]);
  const [cases, setCases] = useState<DisciplineCase[]>([]);
  const [status, setStatus] = useState<SetupStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [casesLoading, setCasesLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [statusError, setStatusError] = useState<string | null>(null);
  const [caseError, setCaseError] = useState<string | null>(null);

  const load = useCallback(() => {
    setLoading(true);
    setCasesLoading(true);
    deadlinesApi
      .list()
      .then((rows) => {
        setItems(rows);
        setError(null);
      })
      .catch((e: unknown) =>
        setError(e instanceof ApiError ? e.message : "Yaklaşan süreler yüklenemedi."),
      )
      .finally(() => setLoading(false));

    okulApi
      .getSetupStatus()
      .then((nextStatus) => {
        setStatus(nextStatus);
        setStatusError(null);
      })
      .catch((e: unknown) =>
        setStatusError(e instanceof ApiError ? e.message : "Kurulum durumu okunamadı."),
      );

    // Eski test taklitleri yalnız süre istemcisini sağlayabilir. Üretimde istemci
    // daima vardır; korumalı erişim panelin bağımsız yükleme ilkesini de sürdürür.
    const request = disiplinApi?.listCases?.();
    if (!request) {
      setCasesLoading(false);
      return;
    }
    request
      .then((rows) => {
        setCases(rows);
        setCaseError(null);
      })
      .catch((e: unknown) =>
        setCaseError(e instanceof ApiError ? e.message : "Dosya özeti yüklenemedi."),
      )
      .finally(() => setCasesLoading(false));
  }, []);

  useEffect(load, [load]);

  const overdueCount = items.filter((item) => item.severity === "GEÇTİ").length;
  const upcomingCount = items.filter((item) => item.severity === "YAKLAŞIYOR").length;
  const todayCount = items.filter((item) => item.due_date === todayIso()).length;
  const priorityCount = overdueCount + upcomingCount;
  const openCases = cases.filter((item) => !item.closed_at);
  const closedCases = cases.filter((item) => item.closed_at);

  const stageGroups = useMemo(
    () =>
      STAGE_GROUPS.map((group) => ({
        ...group,
        value: cases.filter((item) => group.stages.includes(item.current_stage)).length,
      })),
    [cases],
  );

  return (
    <div className="space-y-5">
      <section className="flex flex-wrap items-end justify-between gap-5 py-1">
        <div>
          <p className="text-label-medium font-semibold capitalize tracking-wide text-primary">
            {longDate()}
          </p>
          <h1 className="sr-only">Panel</h1>
          <h2 className="mt-1 text-headline-medium font-semibold tracking-tight text-on-surface">
            {greeting()}, bugün{" "}
            {loading ? "işlemleriniz yükleniyor" : `${formatNumber(priorityCount)} işlem bekliyor`}.
          </h2>
          <p className="mt-1 text-body-medium text-on-surface-variant">
            {status?.school_name
              ? `${status.school_name} • disiplin süreçleri ve yasal süre özeti`
              : "Disiplin süreçleri ve yasal süre özeti"}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outlined" icon="refresh" onClick={load}>
            Yenile
          </Button>
          <Link
            to="/disiplin?yeni=1"
            className="group relative inline-flex min-h-[var(--dd-control-height)] items-center gap-2 overflow-hidden rounded-shape-md bg-primary px-4 text-label-large font-semibold text-on-primary shadow-elevation-1 transition hover:shadow-elevation-2 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-2"
          >
            <span aria-hidden="true" className="state-layer" />
            <Icon name="add" size="lg" className="relative z-10" />
            <span className="relative z-10">Yeni dosya</span>
          </Link>
        </div>
      </section>

      {status && !status.setup_completed && (
        <Banner
          icon="settings_suggest"
          tone="border-secondary/20 bg-secondary-container text-on-secondary-container"
          text="Kurulum sihirbazı henüz tamamlanmadı. Okul bilgisi, ders yılı ve sicil aktarımı için ayarları tamamlayın."
          action={{ to: "/ayarlar", label: "Ayarlar'a git" }}
        />
      )}
      {status && status.setup_completed && !status.has_active_school_year && (
        <Banner
          icon="event_busy"
          tone="border-secondary/20 bg-secondary-container text-on-secondary-container"
          text="Aktif ders yılı yok. Kurul tanımı ve süre hesapları için Ayarlar'dan bir ders yılını aktive edin."
          action={{ to: "/ayarlar", label: "Ayarlar'a git" }}
        />
      )}
      {statusError && (
        <Banner
          icon="error"
          tone="border-error/20 bg-error-container text-on-error-container"
          text={statusError}
          alert
        />
      )}

      {priorityCount > 0 && !loading && (
        <Link
          to="#panel-sureler"
          className="group flex flex-wrap items-center gap-3 rounded-shape-lg border border-tertiary/25 bg-tertiary-container/60 px-4 py-3 text-on-tertiary-container transition hover:border-tertiary/40 hover:bg-tertiary-container focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-tertiary"
        >
          <span className="flex h-9 w-9 items-center justify-center rounded-shape-md bg-tertiary text-on-tertiary">
            <Icon name="notifications_active" size="lg" filled />
          </span>
          <span className="min-w-0 flex-1 text-body-medium font-semibold">
            {overdueCount > 0
              ? `${formatNumber(overdueCount)} yasal sürenin tarihi geçti`
              : `${formatNumber(upcomingCount)} yasal sürenin son günü yaklaşıyor`}
          </span>
          <span className="flex items-center gap-1 text-label-large font-semibold">
            Süreleri incele
            <Icon name="arrow_forward" size="lg" />
          </span>
        </Link>
      )}

      <section aria-labelledby="panel-ozet">
        <h2 id="panel-ozet" className="sr-only">
          Özet
        </h2>
        <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
          <StatCard
            label="Açık dosya"
            value={casesLoading ? null : openCases.length}
            icon="folder_open"
            helper={caseError ? "Yüklenemedi" : `${formatNumber(closedCases.length)} tamamlanan`}
            accent="primary"
          />
          <StatCard
            label="Süresi geçmiş"
            value={loading ? null : overdueCount}
            icon="priority_high"
            helper={overdueCount > 0 ? "Öncelik verin" : "Geciken işlem yok"}
            accent={overdueCount > 0 ? "error" : "neutral"}
          />
          <StatCard
            label="Süresi yaklaşan"
            value={loading ? null : upcomingCount}
            icon="schedule"
            helper={todayCount > 0 ? `${formatNumber(todayCount)} işlem bugün` : "Takvim izleniyor"}
            accent={upcomingCount > 0 ? "warning" : "neutral"}
          />
          <StatCard
            label="Öğrenci"
            value={status?.student_count ?? null}
            icon="school"
            helper="Sicil kaydı"
            accent="blue"
          />
          <StatCard
            label="Personel"
            value={status?.personnel_count ?? null}
            icon="badge"
            helper="Aktif personel"
            accent="blue"
          />
          <StatCard
            label="Tatil günü"
            value={status?.holiday_count ?? null}
            icon="calendar_month"
            helper="Süre hesabında"
            accent="success"
          />
        </div>
      </section>

      <div className="grid min-w-0 gap-4 xl:grid-cols-[minmax(0,1.75fr)_minmax(20rem,0.8fr)]">
        <section
          id="panel-sureler"
          aria-labelledby="panel-sureler-title"
          className="dd-panel min-w-0"
        >
          <div className="flex flex-wrap items-center justify-between gap-3 border-b border-outline-variant/70 px-5 py-4">
            <div>
              <h2
                id="panel-sureler-title"
                className="text-title-large font-semibold text-on-surface"
              >
                Öncelikli işler
              </h2>
              <p className="mt-0.5 text-body-small text-on-surface-variant">
                Yasal sürelere göre sıralanan işlem listeniz
              </p>
            </div>
            <Link
              to="/disiplin"
              className="flex items-center gap-1 rounded-shape-sm px-2 py-1 text-label-large font-semibold text-primary hover:bg-primary/8"
            >
              Tüm dosyalar
              <Icon name="arrow_forward" size="lg" />
            </Link>
          </div>

          <div className="p-4">
            {error && (
              <Banner
                icon="error"
                tone="border-error/20 bg-error-container text-on-error-container"
                text={error}
                alert
              />
            )}

            {loading ? (
              <SkeletonList rows={4} />
            ) : items.length === 0 && !error ? (
              <EmptyState
                icon="task_alt"
                title="Takipte gecikmiş veya yaklaşan süre yok"
                description="Süresi dolan itiraz sevkleri, kurul karar süreleri ve tedbirler burada listelenir."
              />
            ) : (
              <div className="space-y-5">
                {SEVERITY_ORDER.map((severity) => {
                  const group = items.filter((item) => item.severity === severity);
                  if (group.length === 0) return null;
                  return <DeadlineGroup key={severity} severity={severity} items={group} />;
                })}
              </div>
            )}
          </div>
        </section>

        <section className="dd-panel">
          <div className="border-b border-outline-variant/70 px-5 py-4">
            <h2 className="text-title-large font-semibold text-on-surface">Dosya durumu</h2>
            <p className="mt-0.5 text-body-small text-on-surface-variant">
              Tüm kayıtların süreç dağılımı
            </p>
          </div>
          <div className="p-5">
            {casesLoading ? (
              <div className="h-48 animate-pulse rounded-shape-lg bg-surface-container" />
            ) : caseError ? (
              <p className="text-body-medium text-error">{caseError}</p>
            ) : cases.length === 0 ? (
              <EmptyState compact icon="donut_large" title="Henüz dosya kaydı yok" />
            ) : (
              <>
                <div
                  className="mx-auto flex h-36 w-36 items-center justify-center rounded-full shadow-inner"
                  style={{
                    background: donutBackground(
                      stageGroups.map((group) => group.value),
                      cases.length,
                    ),
                  }}
                >
                  <div className="flex h-24 w-24 flex-col items-center justify-center rounded-full bg-surface-container-lowest shadow-elevation-1">
                    <span className="text-headline-medium font-semibold text-on-surface">
                      {formatNumber(cases.length)}
                    </span>
                    <span className="text-body-small text-on-surface-variant">Toplam</span>
                  </div>
                </div>
                <div className="mt-5 space-y-2.5">
                  {stageGroups.map((group) => (
                    <div key={group.key} className="flex items-center gap-3 text-body-medium">
                      <span className={`h-2.5 w-2.5 rounded-full ${group.color}`} />
                      <span className="flex-1 text-on-surface-variant">{group.label}</span>
                      <span className="font-semibold text-on-surface">
                        {formatNumber(group.value)}
                      </span>
                    </div>
                  ))}
                </div>
              </>
            )}
          </div>
        </section>
      </div>

      <div className="grid gap-4 lg:grid-cols-[minmax(0,1.3fr)_minmax(22rem,0.7fr)]">
        <section className="dd-panel p-5">
          <div className="mb-4 flex items-center justify-between gap-3">
            <div>
              <h2 className="text-title-large font-semibold text-on-surface">Hızlı işlemler</h2>
              <p className="mt-0.5 text-body-small text-on-surface-variant">
                En sık kullandığınız işlemlere doğrudan ulaşın
              </p>
            </div>
          </div>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <QuickAction to="/disiplin?yeni=1" icon="note_add" label="Yeni dosya" />
            <QuickAction to="/kisiler" icon="person_add" label="Kişi ekle" />
            <QuickAction to="/disiplin" icon="description" label="Evrak üret" />
            <QuickAction to="/ayarlar" icon="calendar_month" label="Takvimi aç" />
          </div>
        </section>

        <section className="dd-panel p-5">
          <h2 className="text-title-large font-semibold text-on-surface">Sistem özeti</h2>
          <p className="mt-0.5 text-body-small text-on-surface-variant">Kurulum ve veri durumu</p>
          <div className="mt-4 space-y-3">
            <SummaryRow
              icon="verified_user"
              label="Kurulum"
              value={status?.setup_completed ? "Tamamlandı" : "Eksik"}
              positive={Boolean(status?.setup_completed)}
            />
            <SummaryRow
              icon="event_available"
              label="Aktif ders yılı"
              value={status?.has_active_school_year ? "Hazır" : "Tanımlanmadı"}
              positive={Boolean(status?.has_active_school_year)}
            />
            <SummaryRow icon="cloud_off" label="Veri konumu" value="Bu cihaz" positive />
          </div>
        </section>
      </div>
    </div>
  );
}

function Banner({
  icon,
  tone,
  text,
  action,
  alert = false,
}: {
  icon: string;
  tone: string;
  text: string;
  action?: { to: string; label: string };
  alert?: boolean;
}) {
  return (
    <div
      role={alert ? "alert" : undefined}
      className={`flex flex-wrap items-center gap-3 rounded-shape-lg border px-4 py-3 ${tone}`}
    >
      <Icon name={icon} size="lg" />
      <span className="min-w-0 flex-1 text-body-medium">{text}</span>
      {action && (
        <Link
          to={action.to}
          className="inline-flex min-h-10 items-center rounded-shape-sm px-3 text-label-large font-semibold hover:bg-black/5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
        >
          {action.label}
        </Link>
      )}
    </div>
  );
}

function StatCard({
  label,
  value,
  icon,
  helper,
  accent,
}: {
  label: string;
  value: number | null;
  icon: string;
  helper: string;
  accent: "primary" | "error" | "warning" | "success" | "blue" | "neutral";
}) {
  const accents = {
    primary: "bg-primary-container text-primary",
    error: "bg-error-container text-error",
    warning: "bg-tertiary-container text-tertiary",
    success: "bg-success-container text-success",
    blue: "bg-secondary-container text-secondary",
    neutral: "bg-surface-container text-on-surface-variant",
  };
  return (
    <div className="dd-card-hover rounded-shape-lg border border-outline-variant/70 bg-surface-container-lowest p-4">
      <p className="flex items-center gap-2 text-label-large text-on-surface-variant">
        <span
          className={`flex h-9 w-9 items-center justify-center rounded-shape-md ${accents[accent]}`}
        >
          <Icon name={icon} size="lg" />
        </span>
        {label}
      </p>
      <p className="mt-3 text-headline-medium font-semibold tracking-tight text-on-surface">
        {value === null ? "—" : formatNumber(value)}
      </p>
      <p className="mt-1 truncate text-body-small text-on-surface-variant">{helper}</p>
    </div>
  );
}

function DeadlineGroup({ severity, items }: { severity: DeadlineSeverity; items: DeadlineItem[] }) {
  const style = SEVERITY_STYLE[severity];
  return (
    <div className="space-y-2">
      <h3 className="flex items-center gap-2 text-label-large font-semibold text-on-surface-variant">
        <Icon name={style.icon} size="lg" />
        {style.heading} ({formatNumber(items.length)})
      </h3>
      <ul className="space-y-2">
        {items.map((item, index) => (
          <li key={`${item.link}-${item.statute_ref}-${item.title}-${index}`}>
            <DeadlineRow item={item} />
          </li>
        ))}
      </ul>
    </div>
  );
}

function DeadlineRow({ item }: { item: DeadlineItem }) {
  const style = SEVERITY_STYLE[item.severity];
  return (
    <Link
      to={item.link}
      className={`group relative grid min-h-14 grid-cols-[auto_minmax(0,1fr)_auto] items-center gap-x-3 overflow-hidden rounded-shape-md border px-3 py-2.5 transition hover:shadow-elevation-1 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-2 focus-visible:ring-offset-surface ${style.row}`}
    >
      <span aria-hidden="true" className="state-layer" />
      <span
        className={`relative z-10 flex h-9 w-9 items-center justify-center rounded-shape-md ${style.badge}`}
      >
        <Icon name={style.icon} size="lg" />
      </span>
      <span className="relative z-10 min-w-0">
        <span className="flex flex-wrap items-center gap-x-2">
          <span className="font-mono text-label-medium font-semibold">{item.case_no}</span>
          <span className="truncate text-body-medium font-medium">{item.title}</span>
        </span>
        <span className="mt-0.5 flex flex-wrap gap-x-3 text-body-small opacity-75">
          <span>Son gün: {formatDate(item.due_date)}</span>
          <span>{item.statute_ref}</span>
        </span>
      </span>
      <Icon name="chevron_right" size="lg" className="relative z-10 opacity-70" />
    </Link>
  );
}

function QuickAction({ to, icon, label }: { to: string; icon: string; label: string }) {
  return (
    <Link
      to={to}
      className="dd-card-hover flex min-h-28 flex-col items-center justify-center gap-3 rounded-shape-lg border border-outline-variant/70 bg-surface-container-low px-3 py-4 text-center text-label-large font-semibold text-on-surface focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
    >
      <span className="flex h-11 w-11 items-center justify-center rounded-shape-lg bg-primary-container text-primary">
        <Icon name={icon} size="xl" />
      </span>
      {label}
    </Link>
  );
}

function SummaryRow({
  icon,
  label,
  value,
  positive,
}: {
  icon: string;
  label: string;
  value: string;
  positive: boolean;
}) {
  return (
    <div className="flex items-center gap-3 rounded-shape-md bg-surface-container-low p-3">
      <span
        className={`flex h-9 w-9 items-center justify-center rounded-shape-md ${
          positive ? "bg-success-container text-success" : "bg-tertiary-container text-tertiary"
        }`}
      >
        <Icon name={icon} size="lg" />
      </span>
      <span className="min-w-0 flex-1 text-body-medium text-on-surface-variant">{label}</span>
      <span className="text-label-large font-semibold text-on-surface">{value}</span>
    </div>
  );
}
