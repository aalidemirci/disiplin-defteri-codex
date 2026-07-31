// Onur Kurulu yönetimi (ADR-0011). Ders yılı başına bir Onur Kurulu (md. 180-184):
// başkan = öğretmenler kurulunca ödül-disiplin kurulu dışından seçilen bir ÖĞRETMEN
// (md. 182); üyeler her sınıf seviyesinden birer öğrenci, son/11. sınıf ikinci başkan
// (md. 180). Üye adları KVKK kapsamındadır.
//
// OYS `modules/odul/OnurKuruluPanel.tsx`'ten UYARLANDI (F4-D3). Sapmalar: auth yok
// (rol/görünürlük kapıları kalktı, koşulsuz render); teklif zaman penceresi kartı
// (ProposalWindow) honors-lite'ta YOK — tamamen kalktı; başkan seçimi
// personnelLookupApi, öğrenci seçimi studentLookupApi (DÜZ dizi, `.results` yok);
// ders yılları `okul` modülünden (okulApi.listSchoolYears DÜZ dizi); addBoardMember
// güncel kurulun TAMAMINI döner — state dönüşle tazelenir (yeniden yükleme yok).

import { useCallback, useEffect, useId, useState } from "react";

import { ApiError } from "../../lib/api";
import { getGradeLevels, gradeLevelLabel } from "../../lib/gradeLevels";
import type { GradeLevelOption } from "../../lib/gradeLevels";
import { okulApi } from "../okul/api";
import Autocomplete from "../../ui/Autocomplete";
import Button from "../../ui/Button";
import Card from "../../ui/Card";
import Icon from "../../ui/Icon";
import { SkeletonList } from "../../ui/Skeleton";
import { useConfirm } from "../../ui/ConfirmProvider";
import { useSnackbar } from "../../ui/SnackbarProvider";
import Select from "../../ui/Select";
import TextField from "../../ui/TextField";
import { personnelLookupApi, studentLookupApi } from "../disiplin/api";
import type { PersonnelSearchRow } from "../disiplin/api";
import { odulApi } from "./api";
import type { HonorBoard, HonorBoardMember, HonorGeneralAssemblyMember } from "./api";

const TEXTAREA_CLASS =
  "block w-full rounded-shape-xs border border-outline bg-surface px-4 py-3 text-body-medium " +
  "text-on-surface outline-none focus-visible:ring-2 focus-visible:ring-primary focus:border-primary";

export default function OnurKuruluPanel() {
  const [board, setBoard] = useState<HonorBoard | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    setLoading(true);
    odulApi
      .getBoard()
      .then((r) => {
        setBoard(r.board);
        setError(null);
      })
      .catch((e: unknown) =>
        setError(e instanceof ApiError ? e.message : "Onur kurulu yüklenemedi."),
      )
      .finally(() => setLoading(false));
  }, []);
  useEffect(load, [load]);

  return (
    <div className="space-y-6">
      <p className="max-w-3xl text-body-medium text-on-surface-variant">
        Aktif ders yılı için Onur Kurulu (md. 180-184). Başkan, öğretmenler kurulunca ödül-disiplin
        kurulu dışından seçilen bir öğretmendir (md. 182); üyeler her sınıf seviyesinden birer
        öğrencidir, son/11. sınıf öğrencisi ikinci başkandır (md. 180). Onur genel kurulu seçim
        süreci sistem dışıdır; sonuç (üyeler) buradan kaydedilir.
      </p>

      {error && <ErrorBanner message={error} />}

      {loading ? (
        <SkeletonList rows={4} />
      ) : board === null ? (
        <BoardCreateCard onCreated={(b) => setBoard(b)} />
      ) : (
        <>
          <ChairCard board={board} onChanged={(b) => setBoard(b)} />
          <MembersCard board={board} onChanged={load} onBoard={(b) => setBoard(b)} />
        </>
      )}
    </div>
  );
}

function ErrorBanner({ message }: { message: string }) {
  return (
    <div className="flex items-start gap-2 rounded-shape-sm bg-error-container px-4 py-3 text-body-medium text-on-error-container">
      <Icon name="error" size="lg" />
      <span>{message}</span>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Kurul oluşturma (kurul henüz yoksa)
// ---------------------------------------------------------------------------

function BoardCreateCard({ onCreated }: { onCreated: (b: HonorBoard) => void }) {
  const snackbar = useSnackbar();
  const [chair, setChair] = useState<PersonnelSearchRow | null>(null);
  const [substituteChair, setSubstituteChair] = useState<PersonnelSearchRow | null>(null);
  const [notes, setNotes] = useState("");
  const fieldIdBase = useId();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const onSubmit = async () => {
    if (!chair) {
      setError("Başkan (öğretmen) seçilmelidir.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      // Aktif ders yılını çöz (okul modülü ucundan; düz dizi döner).
      const years = await okulApi.listSchoolYears();
      const active = years.find((y) => y.is_active);
      if (!active) {
        throw new Error("Aktif ders yılı bulunamadı. Önce Ayarlar'dan bir yıl aktive edin.");
      }
      const created = await odulApi.createBoard({
        school_year_id: active.id,
        chair_id: chair.id,
        substitute_chair_id: substituteChair?.id ?? null,
        notes: notes.trim(),
      });
      snackbar.success("Onur kurulu oluşturuldu.");
      onCreated(created);
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err.message
          : err instanceof Error
            ? err.message
            : "Onur kurulu oluşturulamadı.",
      );
      setBusy(false);
    }
  };

  return (
    <Card elevation={1} className="p-6">
      <p className="text-title-medium text-on-surface">Onur kurulu oluştur</p>
      <p className="mt-1 text-body-medium text-on-surface-variant">
        Aktif ders yılı için yeni bir onur kurulu tanımlanır. Önce başkanı (öğretmen) seçin; üyeler
        oluşturulduktan sonra eklenir.
      </p>
      <div className="mt-4 space-y-4">
        <Autocomplete<PersonnelSearchRow>
          label="Onur kurulu başkanı (öğretmen)"
          required
          selected={chair}
          onSelect={setChair}
          onClear={() => setChair(null)}
          search={(q) => personnelLookupApi.search(q)}
          getKey={(u) => u.id}
          getLabel={(u) => u.full_name}
          getSublabel={(u) => `${u.title || "—"} · ${u.branch || "—"}`}
          placeholder="Öğretmen adı…"
          helperText="Md. 182: başkan, ödül-disiplin kurulu dışından seçilen bir öğretmendir."
        />
        <Autocomplete<PersonnelSearchRow>
          label="Başkan yedeği (öğretmen)"
          selected={substituteChair}
          onSelect={setSubstituteChair}
          onClear={() => setSubstituteChair(null)}
          search={(q) => personnelLookupApi.search(q)}
          getKey={(u) => u.id}
          getLabel={(u) => u.full_name}
          getSublabel={(u) => `${u.title || "—"} · ${u.branch || "—"}`}
          placeholder="Yedek öğretmen adı…"
          helperText="Başkanla aynı kişi olamaz ve ödül-disiplin kurulu dışından seçilir."
        />
        <div>
          <label
            htmlFor={fieldIdBase}
            className="mb-1 block text-label-large text-on-surface-variant"
          >
            Notlar (opsiyonel)
          </label>
          <textarea
            id={fieldIdBase}
            rows={2}
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            className={TEXTAREA_CLASS}
          />
        </div>
        {error && <InlineError message={error} />}
        <div className="flex justify-end">
          <Button icon="groups" onClick={onSubmit} disabled={busy || !chair}>
            {busy ? "Oluşturuluyor…" : "Kurulu oluştur"}
          </Button>
        </div>
      </div>
    </Card>
  );
}

// ---------------------------------------------------------------------------
// Başkan kartı + değiştirme (md. 182)
// ---------------------------------------------------------------------------

function ChairCard({
  board,
  onChanged,
}: {
  board: HonorBoard;
  onChanged: (b: HonorBoard) => void;
}) {
  const snackbar = useSnackbar();
  const [editing, setEditing] = useState(false);
  const [editingSubstitute, setEditingSubstitute] = useState(false);
  const [chair, setChair] = useState<PersonnelSearchRow | null>(null);
  const [substituteChair, setSubstituteChair] = useState<PersonnelSearchRow | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const save = async () => {
    if (!chair) return;
    setBusy(true);
    setError(null);
    try {
      const updated = await odulApi.setBoardChair({ chair_id: chair.id });
      onChanged(updated);
      setEditing(false);
      setChair(null);
      snackbar.success("Başkan güncellendi.");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Başkan güncellenemedi.");
    } finally {
      setBusy(false);
    }
  };

  const saveSubstitute = async () => {
    if (!substituteChair) return;
    setBusy(true);
    setError(null);
    try {
      const updated = await odulApi.setBoardSubstituteChair(substituteChair.id);
      onChanged(updated);
      setEditingSubstitute(false);
      setSubstituteChair(null);
      snackbar.success("Başkan yedeği güncellendi.");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Başkan yedeği güncellenemedi.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card elevation={1} className="p-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <p className="text-label-large text-on-surface-variant">Onur kurulu başkanı (öğretmen)</p>
          <p className="mt-1 flex items-center gap-2 text-title-medium text-on-surface">
            <Icon name="shield_person" className="text-primary" />
            {board.chair_name || "—"}
          </p>
          {board.substitute_chair_name && (
            <p className="mt-1 text-body-medium text-on-surface-variant">
              Başkan yedeği: {board.substitute_chair_name}
            </p>
          )}
        </div>
        <div className="flex flex-wrap gap-2">
          {!editing && (
            <Button variant="text" icon="edit" onClick={() => setEditing(true)}>
              Başkanı değiştir
            </Button>
          )}
          {!editingSubstitute && (
            <Button variant="text" icon="person_edit" onClick={() => setEditingSubstitute(true)}>
              Yedeği değiştir
            </Button>
          )}
        </div>
      </div>

      {editing && (
        <div className="mt-4 space-y-3 rounded-shape-md bg-surface-container-low p-4">
          <Autocomplete<PersonnelSearchRow>
            label="Yeni başkan (öğretmen)"
            required
            selected={chair}
            onSelect={setChair}
            onClear={() => setChair(null)}
            search={(q) => personnelLookupApi.search(q)}
            getKey={(u) => u.id}
            getLabel={(u) => u.full_name}
            getSublabel={(u) => `${u.title || "—"} · ${u.branch || "—"}`}
            placeholder="Öğretmen adı…"
          />
          {error && <InlineError message={error} />}
          <div className="flex justify-end gap-2">
            <Button
              type="button"
              variant="text"
              onClick={() => {
                setEditing(false);
                setChair(null);
                setError(null);
              }}
            >
              Vazgeç
            </Button>
            <Button icon="check" onClick={save} disabled={busy || !chair}>
              {busy ? "Kaydediliyor…" : "Kaydet"}
            </Button>
          </div>
        </div>
      )}
      {editingSubstitute && (
        <div className="mt-4 space-y-3 rounded-shape-md bg-surface-container-low p-4">
          <Autocomplete<PersonnelSearchRow>
            label="Yeni başkan yedeği"
            required
            selected={substituteChair}
            onSelect={setSubstituteChair}
            onClear={() => setSubstituteChair(null)}
            search={(q) => personnelLookupApi.search(q)}
            getKey={(person) => person.id}
            getLabel={(person) => person.full_name}
            getSublabel={(person) => `${person.title || "—"} · ${person.branch || "—"}`}
            placeholder="Öğretmen adı…"
          />
          {error && <InlineError message={error} />}
          <div className="flex justify-end gap-2">
            <Button
              variant="text"
              onClick={() => {
                setEditingSubstitute(false);
                setSubstituteChair(null);
                setError(null);
              }}
            >
              Vazgeç
            </Button>
            <Button icon="check" onClick={saveSubstitute} disabled={busy || !substituteChair}>
              {busy ? "Kaydediliyor…" : "Kaydet"}
            </Button>
          </div>
        </div>
      )}
    </Card>
  );
}

// ---------------------------------------------------------------------------
// Üyeler kartı (asıl/yedek; yalnız öğrenci — md. 180) + ekleme/çıkarma
// ---------------------------------------------------------------------------

function MembersCard({
  board,
  onChanged,
  onBoard,
}: {
  board: HonorBoard;
  onChanged: () => void;
  onBoard: (b: HonorBoard) => void;
}) {
  const [adding, setAdding] = useState(false);
  const principals = board.members
    .filter((m) => m.is_active && !m.is_substitute)
    .sort((a, b) => (a.grade_level ?? 0) - (b.grade_level ?? 0) || a.order - b.order);
  const substitutes = board.members
    .filter((m) => m.is_active && m.is_substitute)
    .sort((a, b) => a.order - b.order);

  return (
    <Card elevation={1} className="p-6">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-title-medium text-on-surface">
          Aktif üyeler ({principals.length + substitutes.length})
        </p>
        {!adding && (
          <Button variant="tonal" icon="person_add" onClick={() => setAdding(true)}>
            Üye ekle
          </Button>
        )}
      </div>

      {adding && (
        <div className="mt-4">
          <AddMemberForm
            onCancel={() => setAdding(false)}
            onAdded={(b) => {
              setAdding(false);
              // Üye ekleme güncel kurulun tamamını döner — state dönüşle tazelenir.
              onBoard(b);
            }}
          />
        </div>
      )}

      <div className="mt-4 grid grid-cols-1 gap-6 lg:grid-cols-2">
        <MemberGroup
          title="Asıl üyeler"
          members={principals}
          emptyText="Henüz asıl üye eklenmedi."
          onRemoved={onChanged}
        />
        <MemberGroup
          title="Yedek üyeler"
          members={substitutes}
          emptyText="Henüz yedek üye eklenmedi."
          onRemoved={onChanged}
        />
      </div>
    </Card>
  );
}

function MemberGroup({
  title,
  members,
  emptyText,
  onRemoved,
}: {
  title: string;
  members: HonorBoardMember[];
  emptyText: string;
  onRemoved: () => void;
}) {
  return (
    <div>
      <p className="text-label-large text-on-surface-variant">{title}</p>
      {members.length === 0 ? (
        <p className="mt-2 text-body-medium text-on-surface-variant">{emptyText}</p>
      ) : (
        <ul className="mt-2 divide-y divide-outline-variant/50">
          {members.map((m) => (
            <MemberRow key={m.id} member={m} onRemoved={onRemoved} />
          ))}
        </ul>
      )}
    </div>
  );
}

function MemberRow({ member: m, onRemoved }: { member: HonorBoardMember; onRemoved: () => void }) {
  const snackbar = useSnackbar();
  const confirm = useConfirm();
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const remove = async () => {
    if (
      !(await confirm({
        message: `'${m.member_name}' onur kurulundan çıkarılsın mı?`,
        confirmLabel: "Çıkar",
      }))
    )
      return;
    setBusy(true);
    setErr(null);
    try {
      await odulApi.removeBoardMember(m.id);
      onRemoved();
      snackbar.success("Üye çıkarıldı.");
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : "Çıkarılamadı.");
      setBusy(false);
    }
  };

  return (
    <li className="flex flex-wrap items-center justify-between gap-3 py-3">
      <div className="min-w-0">
        <p className="flex flex-wrap items-center gap-2 text-body-medium text-on-surface">
          <span className="inline-flex items-center rounded-shape-xl bg-tertiary-container px-2 py-0.5 text-label-small text-on-tertiary-container">
            {m.grade_level != null ? gradeLevelLabel(m.grade_level) : "Öğrenci"}
          </span>
          {m.is_second_chair && (
            <span className="inline-flex items-center rounded-shape-xl bg-primary-container px-2 py-0.5 text-label-small text-on-primary-container">
              İkinci başkan
            </span>
          )}
          {m.member_name}
        </p>
        {m.title && <p className="text-label-small text-on-surface-variant">{m.title}</p>}
        {err && <p className="text-label-small text-error">{err}</p>}
      </div>
      <Button variant="text" icon="person_remove" onClick={remove} disabled={busy}>
        Çıkar
      </Button>
    </li>
  );
}

// ---------------------------------------------------------------------------
// Üye ekleme formu — öğrenci seçici + sınıf seviyesi + ikinci başkan/yedek
// ---------------------------------------------------------------------------

interface StudentOption {
  id: number;
  label: string;
  sublabel?: string;
}

function AddMemberForm({
  onCancel,
  onAdded,
}: {
  onCancel: () => void;
  onAdded: (b: HonorBoard) => void;
}) {
  const snackbar = useSnackbar();
  const [student, setStudent] = useState<StudentOption | null>(null);
  const [gradeLevel, setGradeLevel] = useState("");
  const [isSecondChair, setIsSecondChair] = useState(false);
  const [isSubstitute, setIsSubstitute] = useState(false);
  const [order, setOrder] = useState("0");
  const [title, setTitle] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [levels, setLevels] = useState<GradeLevelOption[]>([]);
  const [assemblyMembers, setAssemblyMembers] = useState<HonorGeneralAssemblyMember[]>([]);

  // Seçilebilir seviyeler (Hazırlık opt-in iken 0 dahil; Tur 120). Uç erişilemezse
  // 9-12'ye düş (Hazırlık görünmez ama form çalışır).
  useEffect(() => {
    let active = true;
    getGradeLevels()
      .then((r) => {
        if (active) setLevels(r.levels);
      })
      .catch(() => {
        if (active) setLevels([9, 10, 11, 12].map((v) => ({ value: v, label: String(v) })));
      });
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    odulApi
      .listGeneralAssemblyMembers()
      .then((rows) => setAssemblyMembers(rows.filter((row) => row.is_active)))
      .catch(() => setAssemblyMembers([]));
  }, []);

  // Öğrenci lookup'ı DÜZ dizi döner (`.results` yok).
  const searchStudent = (q: string): Promise<StudentOption[]> =>
    studentLookupApi.search(q).then((rows) => {
      const activeIds = new Set(assemblyMembers.map((member) => member.member_student));
      return rows
        .filter((row) => activeIds.has(row.id))
        .map((s) => ({
          id: s.id,
          label: s.full_name,
          sublabel: `${s.class_label} · #${s.student_number}`,
        }));
    });

  const submit = async () => {
    if (!student) {
      setError("Bir öğrenci seçilmelidir.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      // Dönen değer güncel kurulun TAMAMI — üst bileşen state'i bununla tazeler.
      const updated = await odulApi.addBoardMember({
        student_id: student.id,
        assembly_member_id:
          assemblyMembers.find((member) => member.member_student === student.id)?.id ?? null,
        grade_level: gradeLevel ? Number(gradeLevel) : null,
        is_second_chair: isSecondChair,
        is_substitute: isSubstitute,
        order: Number(order) || 0,
        title: title.trim(),
      });
      onAdded(updated);
      snackbar.success("Üye eklendi.");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Üye eklenemedi.");
      setBusy(false);
    }
  };

  return (
    <div className="space-y-4 rounded-shape-md bg-surface-container-low p-4">
      <p className="text-title-medium text-on-surface">Yeni öğrenci üye</p>

      <Autocomplete<StudentOption>
        label="Öğrenci seç"
        required
        selected={student}
        onSelect={setStudent}
        onClear={() => setStudent(null)}
        search={searchStudent}
        getKey={(s) => s.id}
        getLabel={(s) => s.label}
        getSublabel={(s) => s.sublabel ?? ""}
        placeholder="Öğrenci adı…"
        helperText="Yalnız Onur Genel Kurulunda aktif temsilciliği bulunan öğrenciler gösterilir."
      />

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <Select
          label="Sınıf seviyesi"
          value={gradeLevel}
          onChange={(e) => setGradeLevel(e.target.value)}
          options={[
            { value: "", label: "— belirtilmemiş —" },
            ...levels.map((l) => ({ value: String(l.value), label: gradeLevelLabel(l.value) })),
          ]}
          helperText="Temsil ettiği seviye (md. 180; Hazırlık opt-in ise listede)."
        />
        <TextField
          label="Sıra"
          type="number"
          min={0}
          value={order}
          onChange={(e) => setOrder(e.target.value)}
          helperText="Aynı grup içinde gösterim sırası."
        />
      </div>

      <TextField
        label="Ünvan / görev (opsiyonel)"
        value={title}
        onChange={(e) => setTitle(e.target.value)}
        helperText="Örn. 'İkinci başkan', 'Yedek ikinci başkan'."
      />

      <div className="flex flex-wrap gap-x-6 gap-y-2">
        <label className="flex min-h-12 items-center gap-3 text-body-medium text-on-surface">
          <input
            type="checkbox"
            checked={isSecondChair}
            onChange={(e) => setIsSecondChair(e.target.checked)}
            className="h-5 w-5 accent-primary"
          />
          İkinci başkan (son/11. sınıf, md. 180)
        </label>
        <label className="flex min-h-12 items-center gap-3 text-body-medium text-on-surface">
          <input
            type="checkbox"
            checked={isSubstitute}
            onChange={(e) => setIsSubstitute(e.target.checked)}
            className="h-5 w-5 accent-primary"
          />
          Yedek üye
        </label>
      </div>

      {error && <InlineError message={error} />}

      <div className="flex justify-end gap-2">
        <Button type="button" variant="text" onClick={onCancel}>
          Vazgeç
        </Button>
        <Button icon="check" onClick={submit} disabled={busy || !student}>
          {busy ? "Ekleniyor…" : "Üyeyi ekle"}
        </Button>
      </div>
    </div>
  );
}

function InlineError({ message }: { message: string }) {
  return (
    <div className="flex items-start gap-2 rounded-shape-sm bg-error-container px-4 py-2 text-body-small text-on-error-container">
      <Icon name="error" size="sm" />
      <span>{message}</span>
    </div>
  );
}
