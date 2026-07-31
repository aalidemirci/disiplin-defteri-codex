import { useCallback, useEffect, useState } from "react";

import { ApiError } from "../../lib/api";
import Autocomplete from "../../ui/Autocomplete";
import Button from "../../ui/Button";
import Card from "../../ui/Card";
import { useConfirm } from "../../ui/ConfirmProvider";
import Dialog from "../../ui/Dialog";
import Icon from "../../ui/Icon";
import Select from "../../ui/Select";
import { SkeletonList } from "../../ui/Skeleton";
import { useSnackbar } from "../../ui/SnackbarProvider";
import TextField from "../../ui/TextField";
import { okulApi } from "../okul/api";
import type {
  ClassResponsibility,
  ClassResponsibilityWriteBody,
  Personnel,
  SchoolYear,
} from "../okul/api";

export default function SinifSorumlulariPage() {
  const [years, setYears] = useState<SchoolYear[]>([]);
  const [yearId, setYearId] = useState<number | null>(null);
  const [rows, setRows] = useState<ClassResponsibility[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [editing, setEditing] = useState<ClassResponsibility | "new" | null>(null);

  useEffect(() => {
    okulApi
      .listSchoolYears()
      .then((items) => {
        setYears(items);
        const initial = items.find((item) => item.is_active) ?? items[0] ?? null;
        setYearId(initial?.id ?? null);
      })
      .catch((err: unknown) =>
        setError(err instanceof ApiError ? err.message : "Ders yılları yüklenemedi."),
      );
  }, []);

  const load = useCallback(() => {
    if (yearId === null) {
      setRows([]);
      setLoading(false);
      return;
    }
    setLoading(true);
    okulApi
      .listClassResponsibilities(yearId)
      .then((items) => {
        setRows(items);
        setError(null);
      })
      .catch((err: unknown) =>
        setError(err instanceof ApiError ? err.message : "Sınıf sorumluları yüklenemedi."),
      )
      .finally(() => setLoading(false));
  }, [yearId]);

  useEffect(load, [load]);

  return (
    <div className="space-y-6">
      <div className="dd-page-header">
        <div>
          <h1 className="dd-page-title">Sınıf sorumluları</h1>
          <p className="dd-page-description">
            Öğrenci Excel'i aktarılınca sınıflar burada otomatik oluşur. Her şube için sınıf rehber
            öğretmenini, ilgili rehber öğretmeni ve müdür yardımcısını aynı ekrandan eşleştirin.
            Disiplin dosyası rehberliğe sevk edilirken bu bilgiler otomatik önerilir.
          </p>
        </div>
        <Button icon="add" onClick={() => setEditing("new")} disabled={yearId === null}>
          Sınıf ekle
        </Button>
      </div>

      {error && <ErrorBanner message={error} />}

      <Card elevation={1} className="p-5">
        <div className="max-w-sm">
          <Select
            label="Ders yılı"
            value={yearId === null ? "" : String(yearId)}
            onChange={(event) => setYearId(Number(event.target.value))}
            options={years.map((year) => ({
              value: String(year.id),
              label: `${year.name}${year.is_active ? " (aktif)" : ""}`,
            }))}
          />
        </div>
      </Card>

      {loading ? (
        <SkeletonList rows={4} />
      ) : rows.length === 0 ? (
        <Card elevation={1} className="p-8 text-center">
          <Icon name="group_work" size="xl" className="mx-auto text-on-surface-variant" />
          <p className="mt-3 text-title-medium text-on-surface">Henüz eşleştirme yok</p>
          <p className="mt-1 text-body-medium text-on-surface-variant">
            Önce öğrenci Excel'ini aktarın; sınıflar burada otomatik oluşacaktır. Gerekirse “Sınıf
            ekle” ile elle de şube ekleyebilirsiniz.
          </p>
        </Card>
      ) : (
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          {rows.map((row) => (
            <ResponsibilityCard
              key={row.id}
              row={row}
              onEdit={() => setEditing(row)}
              onChanged={load}
            />
          ))}
        </div>
      )}

      {editing !== null && yearId !== null && (
        <ResponsibilityDialog
          row={editing === "new" ? null : editing}
          schoolYear={yearId}
          onClose={() => setEditing(null)}
          onSaved={() => {
            setEditing(null);
            load();
          }}
        />
      )}
    </div>
  );
}

function ResponsibilityCard({
  row,
  onEdit,
  onChanged,
}: {
  row: ClassResponsibility;
  onEdit: () => void;
  onChanged: () => void;
}) {
  const confirm = useConfirm();
  const snackbar = useSnackbar();
  const [busy, setBusy] = useState(false);

  const remove = async () => {
    const approved = await confirm({
      title: "Sınıf eşleştirmesini sil",
      message: `${row.class_label} sınıfının sorumlu eşleştirmesi silinsin mi? Eski disiplin aşamalarındaki kişi adları korunur.`,
      confirmLabel: "Sil",
    });
    if (!approved) return;
    setBusy(true);
    try {
      await okulApi.deleteClassResponsibility(row.id);
      snackbar.success(`${row.class_label} eşleştirmesi silindi.`);
      onChanged();
    } catch (err) {
      snackbar.error(err instanceof ApiError ? err.message : "Eşleştirme silinemedi.");
      setBusy(false);
    }
  };

  return (
    <Card elevation={1} className="p-5">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-title-large text-on-surface">{row.class_label}</p>
          <p className="text-label-medium text-on-surface-variant">{row.school_year_name}</p>
        </div>
        <div className="flex">
          <Button variant="text" icon="edit" onClick={onEdit} disabled={busy}>
            Düzenle
          </Button>
          <Button variant="text" icon="delete" onClick={remove} disabled={busy}>
            Sil
          </Button>
        </div>
      </div>
      <dl className="mt-4 space-y-3">
        <ResponsibilityLine label="Sınıf rehber öğretmeni" person={row.class_teacher_detail} />
        <ResponsibilityLine label="Müdür yardımcısı" person={row.assistant_principal_detail} />
        <ResponsibilityLine label="Rehber öğretmen" person={row.guidance_teacher_detail} />
      </dl>
    </Card>
  );
}

function ResponsibilityLine({ label, person }: { label: string; person: Personnel | null }) {
  return (
    <div>
      <dt className="text-label-small text-on-surface-variant">{label}</dt>
      <dd className="text-body-medium text-on-surface">
        {person?.full_name ?? <span className="text-on-surface-variant">Atanmadı</span>}
      </dd>
    </div>
  );
}

function ResponsibilityDialog({
  row,
  schoolYear,
  onClose,
  onSaved,
}: {
  row: ClassResponsibility | null;
  schoolYear: number;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [level, setLevel] = useState(row?.class_level ?? 9);
  const [section, setSection] = useState(row?.class_section ?? "");
  const [classTeacher, setClassTeacher] = useState<Personnel | null>(
    row?.class_teacher_detail ?? null,
  );
  const [assistantPrincipal, setAssistantPrincipal] = useState<Personnel | null>(
    row?.assistant_principal_detail ?? null,
  );
  const [guidanceTeacher, setGuidanceTeacher] = useState<Personnel | null>(
    row?.guidance_teacher_detail ?? null,
  );
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const snackbar = useSnackbar();

  const searchPersonnel = useCallback(async (query: string) => {
    const page = await okulApi.listPersonnel({ search: query, limit: 50 });
    return page.results;
  }, []);

  const save = async () => {
    if (!section.trim()) {
      setError("Şube zorunludur.");
      return;
    }
    const body: ClassResponsibilityWriteBody = {
      school_year: schoolYear,
      class_level: level,
      class_section: section.trim(),
      class_teacher: classTeacher?.id ?? null,
      assistant_principal: assistantPrincipal?.id ?? null,
      guidance_teacher: guidanceTeacher?.id ?? null,
    };
    setBusy(true);
    setError(null);
    try {
      if (row) await okulApi.updateClassResponsibility(row.id, body);
      else await okulApi.createClassResponsibility(body);
      snackbar.success(row ? "Sınıf sorumluları güncellendi." : "Sınıf sorumluları eklendi.");
      onSaved();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Sınıf sorumluları kaydedilemedi.");
      setBusy(false);
    }
  };

  const personPicker = (
    label: string,
    person: Personnel | null,
    setter: (value: Personnel | null) => void,
  ) => (
    <Autocomplete<Personnel>
      label={label}
      selected={person}
      onSelect={setter}
      onClear={() => setter(null)}
      search={searchPersonnel}
      getKey={(item) => item.id}
      getLabel={(item) => item.full_name}
      getSublabel={(item) => [item.title, item.branch].filter(Boolean).join(" · ")}
      minChars={0}
      placeholder="Personel listesinden seçin…"
      helperText="Ad, unvan veya branş yazarak arayabilirsiniz."
    />
  );

  return (
    <Dialog
      open
      onClose={onClose}
      title={row ? `${row.class_label} sorumlularını düzenle` : "Sınıf sorumluları ekle"}
      actions={
        <>
          <Button variant="text" onClick={onClose} disabled={busy}>
            Vazgeç
          </Button>
          <Button icon="check" onClick={save} disabled={busy}>
            {busy ? "Kaydediliyor…" : "Kaydet"}
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        {error && <ErrorBanner message={error} />}
        <div className="grid grid-cols-2 gap-3">
          <Select
            label="Sınıf"
            required
            value={String(level)}
            onChange={(event) => setLevel(Number(event.target.value))}
            options={[9, 10, 11, 12].map((value) => ({
              value: String(value),
              label: String(value),
            }))}
          />
          <TextField
            label="Şube"
            required
            value={section}
            onChange={(event) => setSection(event.target.value)}
            placeholder="A"
          />
        </div>
        {personPicker("Sınıf rehber öğretmeni", classTeacher, setClassTeacher)}
        {personPicker("İlgili müdür yardımcısı", assistantPrincipal, setAssistantPrincipal)}
        {personPicker("İlgili rehber öğretmen", guidanceTeacher, setGuidanceTeacher)}
      </div>
    </Dialog>
  );
}

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
