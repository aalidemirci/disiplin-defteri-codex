// Disiplin dosyaları liste sayfası.
//
// OYS `modules/disiplin/DisiplinPage.tsx`'ten UYARLANDI (F4-D2). Sapmalar: auth/rol
// kalktı (tek kullanıcı — useAuth/hasAnyRole yok, tüm eylemler koşulsuz görünür);
// başlık metnindeki rol-bazlı görünürlük (limited/full) cümlesi kaldırıldı.

import { useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { ApiError } from "../../lib/api";
import { formatDate } from "../../lib/format";
import Button from "../../ui/Button";
import Card from "../../ui/Card";
import Icon from "../../ui/Icon";
import { SkeletonList } from "../../ui/Skeleton";
import Select from "../../ui/Select";
import TextField from "../../ui/TextField";
import { disiplinApi, STAGE_TR } from "./api";
import type { CaseStage, DisciplineCase } from "./api";
import DisciplineCaseCreateForm from "./DisciplineCaseCreateForm";
import { caseSteps } from "./workflow";

const STAGE_CHIP: Record<CaseStage, string> = {
  PETITION: "bg-tertiary-container text-on-tertiary-container",
  GUIDANCE_REFERRED: "bg-primary-container text-on-primary-container",
  GUIDANCE_RETURNED: "bg-secondary-container text-on-secondary-container",
  DECIDED: "bg-secondary-container text-on-secondary-container",
  COMMITTEE_DONE: "bg-primary-container text-on-primary-container",
  CLOSED: "bg-surface-container-high text-on-surface-variant",
};

export default function DisiplinPage() {
  const [searchParams] = useSearchParams();
  const [items, setItems] = useState<DisciplineCase[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [fStage, setFStage] = useState<CaseStage | "">("");
  const [query, setQuery] = useState(() => searchParams.get("ara") ?? "");
  const [onlyOpen, setOnlyOpen] = useState(true);
  const [creating, setCreating] = useState(() => searchParams.get("yeni") === "1");

  useEffect(() => {
    const incomingQuery = searchParams.get("ara");
    if (incomingQuery !== null) setQuery(incomingQuery);
    if (searchParams.get("yeni") === "1") setCreating(true);
  }, [searchParams]);

  const load = () => {
    setLoading(true);
    disiplinApi
      .listCases()
      .then((r) => {
        setItems(r);
        setError(null);
      })
      .catch((e: unknown) => setError(e instanceof ApiError ? e.message : "Dosyalar yüklenemedi."))
      .finally(() => setLoading(false));
  };
  useEffect(load, []);

  const filtered = useMemo(
    () =>
      items.filter((c) => {
        const normalizedQuery = query.trim().toLocaleLowerCase("tr-TR");
        const matchesQuery =
          !normalizedQuery ||
          c.case_no.toLocaleLowerCase("tr-TR").includes(normalizedQuery) ||
          c.students.some((student) =>
            student.full_name.toLocaleLowerCase("tr-TR").includes(normalizedQuery),
          );
        return (
          matchesQuery && (!fStage || c.current_stage === fStage) && (!onlyOpen || !c.closed_at)
        );
      }),
    [items, fStage, onlyOpen, query],
  );

  return (
    <div className="space-y-[var(--dd-page-gap)]">
      <div className="dd-page-header">
        <div className="min-w-0">
          <h1 className="dd-page-title">Disiplin</h1>
          <p className="dd-page-description">
            Disiplin dosyaları, aşama akışı (dilekçe → rehberlik → müdür/kurul kararı → kapanış) ve
            dosya ekleri. KVKK kapsamında hassas kişisel veri içerir.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {!creating && (
            <Button icon="add" onClick={() => setCreating(true)}>
              Yeni dosya
            </Button>
          )}
          <Link
            to="/disiplin/kurul"
            className="inline-flex min-h-[var(--dd-control-height)] items-center gap-2 rounded-shape-md border border-outline-variant bg-surface-container-lowest px-3 text-label-large font-semibold text-on-surface transition hover:border-primary/40 hover:bg-surface-container-low focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
          >
            <Icon name="groups" size="lg" />
            Disiplin Kurulu
          </Link>
          <Link
            to="/disiplin/onur-teklifleri"
            className="inline-flex min-h-[var(--dd-control-height)] items-center gap-2 rounded-shape-md border border-outline-variant bg-surface-container-lowest px-3 text-label-large font-semibold text-on-surface transition hover:border-primary/40 hover:bg-surface-container-low focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
          >
            <Icon name="workspace_premium" size="lg" />
            Onur teklifleri
          </Link>
          <Link
            to="/disiplin/karar-tipleri"
            className="inline-flex min-h-[var(--dd-control-height)] items-center gap-2 rounded-shape-md border border-outline-variant bg-surface-container-lowest px-3 text-label-large font-semibold text-on-surface transition hover:border-primary/40 hover:bg-surface-container-low focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
          >
            <Icon name="rule" size="lg" />
            Karar tipleri
          </Link>
          <Button variant="text" icon="refresh" onClick={load}>
            Yenile
          </Button>
        </div>
      </div>

      {creating && (
        <DisciplineCaseCreateForm
          onCancel={() => setCreating(false)}
          onCreated={(c) => {
            setItems((prev) => [c, ...prev]);
            setCreating(false);
          }}
        />
      )}

      {/* Filtreler */}
      <Card
        elevation={0}
        className="grid items-end gap-3 p-[var(--dd-panel-padding)] shadow-elevation-1 md:grid-cols-[minmax(14rem,2fr)_minmax(11rem,1fr)_auto]"
      >
        <TextField
          label="Dosyalarda ara"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Dosya no veya öğrenci adı"
        />
        <div>
          <Select
            label="Aşama"
            placeholder="Tümü"
            value={fStage}
            onChange={(e) => setFStage(e.target.value as CaseStage | "")}
            options={Object.entries(STAGE_TR).map(([value, label]) => ({ value, label }))}
          />
        </div>
        <label className="flex min-h-[var(--dd-field-height)] items-center gap-2 rounded-shape-sm px-2 text-body-medium text-on-surface">
          <input
            type="checkbox"
            checked={onlyOpen}
            onChange={(e) => setOnlyOpen(e.target.checked)}
            className="h-5 w-5 accent-primary"
          />
          Yalnızca açık dosyalar
        </label>
      </Card>

      {error && (
        <div className="flex items-start gap-2 rounded-shape-sm bg-error-container px-4 py-3 text-body-medium text-on-error-container">
          <Icon name="error" size="lg" />
          <span>{error}</span>
        </div>
      )}

      {loading ? (
        <SkeletonList rows={5} />
      ) : filtered.length === 0 ? (
        <Card elevation={1} className="p-6">
          <p className="text-body-medium text-on-surface-variant">
            Gösterilecek dosya yok.{items.length > 0 && " Filtreleri değiştirin."}
          </p>
        </Card>
      ) : (
        <Card elevation={0} className="overflow-x-auto p-0 shadow-elevation-1 scrollbar-thin">
          <div className="flex items-center justify-between border-b border-outline-variant bg-surface-container-low px-4 py-3">
            <p className="text-label-medium text-on-surface-variant">
              {filtered.length} dosya gösteriliyor
            </p>
          </div>
          <table className="w-full text-body-small">
            <thead className="sticky top-0 z-10 bg-surface-container-low text-left text-on-surface-variant">
              <tr>
                <th className="px-3 py-2 font-medium">Dosya no</th>
                <th className="px-3 py-2 font-medium">Dilekçe tarihi</th>
                <th className="px-3 py-2 font-medium">İlgili öğrenciler</th>
                <th className="px-3 py-2 font-medium">Aşama</th>
                <th className="px-3 py-2 font-medium">Süreç</th>
                <th className="px-3 py-2 font-medium">Kapanış</th>
                <th className="px-3 py-2 font-medium"></th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((c) => (
                <tr
                  key={c.id}
                  className="border-t border-outline-variant/50 transition-colors hover:bg-on-surface/8"
                >
                  <td className="px-3 py-2 font-mono text-label-medium text-on-surface-variant">
                    {c.case_no}
                  </td>
                  <td className="px-3 py-2 text-on-surface-variant">
                    {formatDate(c.petition_date)}
                  </td>
                  <td className="px-3 py-2 text-on-surface">
                    <StudentsCell students={c.students} />
                  </td>
                  <td className="px-3 py-2">
                    <span
                      className={`inline-flex items-center rounded-shape-xl px-2 py-0.5 text-label-small ${STAGE_CHIP[c.current_stage]}`}
                    >
                      {STAGE_TR[c.current_stage]}
                    </span>
                  </td>
                  <td className="px-3 py-2">
                    <StageProgress stage={c.current_stage} />
                  </td>
                  <td className="px-3 py-2 text-on-surface-variant">
                    {c.closed_at ? formatDate(c.closed_at) : "—"}
                  </td>
                  <td className="px-3 py-2 text-right">
                    <Link
                      to={`/disiplin/${c.id}`}
                      className="inline-flex min-h-[var(--dd-control-height)] items-center gap-1 rounded-shape-xs px-2 text-label-large text-primary hover:bg-primary/8 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
                    >
                      Detay
                      <Icon name="chevron_right" size="sm" />
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}
    </div>
  );
}

// Kompakt süreç göstergesi (aşama rayının liste-içi mini sürümü, Tur 108).
// Liste yanıtında events yok → dal bilinmez; durum yalnız güncel aşamadan türetilir.
function StageProgress({ stage }: { stage: CaseStage }) {
  const steps = caseSteps(stage, null);
  return (
    <div className="flex items-center gap-1" title={`Aşama: ${STAGE_TR[stage]}`}>
      {steps.map((s) => (
        <span
          key={s.key}
          aria-hidden="true"
          className={`h-2 w-2 rounded-full ${
            s.status === "done"
              ? "bg-primary"
              : s.status === "current"
                ? "bg-primary ring-2 ring-primary/40"
                : "bg-outline-variant"
          }`}
        />
      ))}
      <span className="sr-only">{STAGE_TR[stage]}</span>
    </div>
  );
}

function StudentsCell({ students }: { students: DisciplineCase["students"] }) {
  if (students.length === 0) return <span className="text-on-surface-variant">—</span>;
  if (students.length === 1) {
    const s = students[0];
    return (
      <span>
        {s.full_name}
        {s.class_label && <span className="ml-1 text-on-surface-variant">({s.class_label})</span>}
      </span>
    );
  }
  return (
    <span title={students.map((s) => s.full_name).join(", ")}>
      {students[0].full_name}{" "}
      <span className="text-on-surface-variant">+{students.length - 1} öğrenci</span>
    </span>
  );
}
