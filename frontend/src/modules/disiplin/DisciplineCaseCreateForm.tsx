// OYS `modules/disiplin/DisciplineCaseCreateForm.tsx`'ten UYARLANDI (F4-D2); sapmalar:
// VELI dilekçeci FK'sız (parentLookupApi yok — yalnız serbest ad), personel araması
// personnelLookupApi (userLookupApi yerine), studentLookupApi düz dizi döner (.results yok).
//
// Yeni disiplin dosyası açma formu (Tur 35 — ortak Autocomplete'e geçti).
//
// Autocomplete alanları:
//   1. "Dilekçeyi veren" — petitioner_role'a göre arama tipi değişir:
//        OGRETMEN → personnel/?search=
//        OGRENCI  → students/?search=
//        VELI/IDARE/DIGER → serbest metin (autocomplete yok; veli sicili yok)
//      Seçim yapılırsa ilgili FK ID backend'e gider; backend role/FK
//      tutarlılığını clean() ile zorlar (model+serializer iki katmanlı).
//   2. "İlgili öğrenciler" — çoklu seçim (chip listesi)

import { useId, useState } from "react";

import { todayIso } from "../../lib/format";
import type { FormEvent } from "react";

import { useFormErrors } from "../../hooks/useFormErrors";
import { asMessage } from "./formHelpers";
import Autocomplete from "../../ui/Autocomplete";
import Button from "../../ui/Button";
import Card from "../../ui/Card";
import Icon from "../../ui/Icon";
import Select from "../../ui/Select";
import { useSnackbar } from "../../ui/SnackbarProvider";
import TextField from "../../ui/TextField";
import { okulApi } from "../okul/api";
import { disiplinApi, PETITIONER_TR, personnelLookupApi, studentLookupApi } from "./api";
import type {
  DisciplineCase,
  DisciplineCaseCreateBody,
  PersonnelSearchRow,
  PetitionerRole,
  StudentSearchRow,
} from "./api";

interface Props {
  onCancel: () => void;
  onCreated: (c: DisciplineCase) => void;
}

// Dilekçe veren için seçili kişi türünü tutmak için birleşik bir tip.
type PetitionerPick =
  { kind: "user"; data: PersonnelSearchRow } | { kind: "student"; data: StudentSearchRow } | null;

export default function DisciplineCaseCreateForm({ onCancel, onCreated }: Props) {
  const today = todayIso();

  // Form alanları
  const [petitionDate, setPetitionDate] = useState(today);
  const [petitionerRole, setPetitionerRole] = useState<PetitionerRole>("OGRETMEN");
  const [petitioner, setPetitioner] = useState<PetitionerPick>(null);
  const [petitionerFreeName, setPetitionerFreeName] = useState(""); // VELI/IDARE/DIGER
  const [summary, setSummary] = useState("");
  const [students, setStudents] = useState<StudentSearchRow[]>([]);
  const [studentDraft, setStudentDraft] = useState<StudentSearchRow | null>(null);
  const [guardianDrafts, setGuardianDrafts] = useState<Record<number, string>>({});

  // Submit state
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // Backend {fields} hatalarını alan-bazlı göstermek için (Talep 1f).
  const { errors, applyApiError, clearErrors } = useFormErrors<string>();
  const snackbar = useSnackbar();
  const fieldIdBase = useId();

  // Rol değişince seçilmiş kişiyi temizle (uyumsuz olmasın).
  const onRoleChange = (role: PetitionerRole) => {
    setPetitionerRole(role);
    setPetitioner(null);
    setPetitionerFreeName("");
  };

  // Çoklu öğrenci: bir tanesi seçilince listeye ekle, draft'ı temizle.
  const addStudent = (s: StudentSearchRow) => {
    if (!students.some((x) => x.id === s.id)) {
      setStudents((prev) => [...prev, s]);
      if (s.guardian_name === "") {
        setGuardianDrafts((prev) => ({ ...prev, [s.id]: "" }));
      }
    }
    setStudentDraft(null);
  };
  const removeStudent = (id: number) => {
    setStudents((prev) => prev.filter((s) => s.id !== id));
    setGuardianDrafts((prev) => {
      const next = { ...prev };
      delete next[id];
      return next;
    });
  };

  const needsAutocomplete = petitionerRole === "OGRETMEN" || petitionerRole === "OGRENCI";

  const petitionerNameForSubmit = (): string => {
    if (petitioner?.kind === "user") return petitioner.data.full_name;
    if (petitioner?.kind === "student") return petitioner.data.full_name;
    return petitionerFreeName.trim();
  };

  const submitDisabled = (): boolean => {
    if (busy) return true;
    if (students.length === 0) return true;
    if (
      students.some(
        (student) => student.guardian_name === "" && !(guardianDrafts[student.id] ?? "").trim(),
      )
    ) {
      return true;
    }
    if (!summary.trim()) return true;
    if (needsAutocomplete && petitioner === null) return true;
    if (!needsAutocomplete && !petitionerFreeName.trim()) return true;
    return false;
  };

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (students.length === 0) {
      setError("En az bir öğrenci seçilmelidir.");
      return;
    }
    setBusy(true);
    setError(null);
    clearErrors();
    try {
      // Temel Excel şablonunda veli alanı yoktur. Disiplin dosyasına alınan
      // öğrencinin veli adı ilk kez burada istenir ve öğrenci siciline yazılır.
      await Promise.all(
        students
          .filter((student) => student.guardian_name === "")
          .map((student) =>
            okulApi.updateStudent(student.id, {
              guardian_name: (guardianDrafts[student.id] ?? "").trim(),
            }),
          ),
      );
      const body: DisciplineCaseCreateBody = {
        petition_date: petitionDate,
        petitioner_name: petitionerNameForSubmit(),
        petitioner_role: petitionerRole,
        summary: summary.trim(),
        student_ids: students.map((s) => s.id),
      };
      if (petitioner?.kind === "user") body.petitioner_user_id = petitioner.data.id;
      if (petitioner?.kind === "student") body.petitioner_student_id = petitioner.data.id;
      const c = await disiplinApi.createCase(body);
      snackbar.success("Disiplin dosyası açıldı.");
      onCreated(c);
    } catch (err) {
      // Backend {fields} → alan-bazlı kırmızı; hiçbir alan eşleşmezse genel mesaj.
      const field = applyApiError(err);
      if (!field) setError(asMessage(err, "Dosya oluşturulamadı."));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card elevation={2} className="p-6">
      <h2 className="text-title-large text-on-surface">Yeni disiplin dosyası</h2>
      <form onSubmit={onSubmit} className="mt-4 space-y-4">
        {/* Dilekçe tarihi + rolü */}
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <TextField
            label="Dilekçe tarihi"
            type="date"
            required
            value={petitionDate}
            onChange={(e) => setPetitionDate(e.target.value)}
            error={errors.petition_date}
          />
          <Select
            label="Dilekçeyi veren rolü"
            required
            value={petitionerRole}
            onChange={(e) => onRoleChange(e.target.value as PetitionerRole)}
            options={Object.entries(PETITIONER_TR).map(([value, label]) => ({ value, label }))}
            error={errors.petitioner_role}
          />
        </div>

        {/* Dilekçeyi veren — role göre tip değişen autocomplete (Tur 35) */}
        {petitionerRole === "OGRETMEN" && (
          <Autocomplete<PersonnelSearchRow>
            label="Dilekçeyi veren personel"
            required
            selected={petitioner?.kind === "user" ? petitioner.data : null}
            onSelect={(u) => setPetitioner({ kind: "user", data: u })}
            onClear={() => setPetitioner(null)}
            search={(q) => personnelLookupApi.search(q)}
            getKey={(u) => u.id}
            getLabel={(u) => u.full_name}
            getSublabel={(u) => `${u.title || "—"} · ${u.branch || "—"}`}
            placeholder="Personel adı…"
            emptyText="Personel bulunamadı."
            error={errors.petitioner_user_id ?? errors.petitioner_name}
            helperText="Sistemde kayıtlı personel arasından seçin (autocomplete)."
          />
        )}
        {petitionerRole === "OGRENCI" && (
          <Autocomplete<StudentSearchRow>
            label="Dilekçeyi veren öğrenci"
            required
            selected={petitioner?.kind === "student" ? petitioner.data : null}
            onSelect={(s) => setPetitioner({ kind: "student", data: s })}
            onClear={() => setPetitioner(null)}
            search={(q) => studentLookupApi.search(q)}
            getKey={(s) => s.id}
            getLabel={(s) => s.full_name}
            getSublabel={(s) => `${s.class_label || "—"} · No: ${s.student_number || "—"}`}
            placeholder="Öğrenci adı veya numarası…"
            emptyText="Öğrenci bulunamadı."
            error={errors.petitioner_student_id ?? errors.petitioner_name}
            helperText="Sistemde kayıtlı öğrenciler arasından seçin (autocomplete)."
          />
        )}
        {(petitionerRole === "VELI" ||
          petitionerRole === "IDARE" ||
          petitionerRole === "DIGER") && (
          <TextField
            label="Dilekçeyi veren adı"
            required
            value={petitionerFreeName}
            onChange={(e) => setPetitionerFreeName(e.target.value)}
            error={errors.petitioner_name}
            helperText="Veli/İdare/Diğer rolünde serbest metin girilir (veli sicili tutulmaz)."
          />
        )}

        {/* Olay özeti */}
        <div>
          <label
            htmlFor={fieldIdBase}
            className="mb-1 block text-label-large text-on-surface-variant"
          >
            Olay özeti <span className="text-error">*</span>
          </label>
          <textarea
            id={fieldIdBase}
            required
            rows={4}
            value={summary}
            onChange={(e) => setSummary(e.target.value)}
            aria-invalid={errors.summary ? true : undefined}
            placeholder="Kısa olgusal anlatım."
            className={`block w-full rounded-shape-xs border bg-surface px-4 py-3 text-body-medium text-on-surface outline-none focus-visible:ring-2 ${
              errors.summary
                ? "border-error focus-visible:ring-error focus:border-error"
                : "border-outline focus-visible:ring-primary focus:border-primary"
            }`}
          />
          {errors.summary && <p className="mt-1 text-body-small text-error">{errors.summary}</p>}
        </div>

        {/* İlgili öğrenciler — çoklu autocomplete (Tur 35) */}
        <div>
          <label className="mb-1 block text-label-large text-on-surface-variant">
            İlgili öğrenciler <span className="text-error">*</span>
          </label>
          {errors.student_ids && (
            <p className="mb-1 text-body-small text-error">{errors.student_ids}</p>
          )}
          {students.length > 0 && (
            <ul className="mb-2 flex flex-wrap gap-2">
              {students.map((s) => (
                <li key={s.id}>
                  <span className="inline-flex items-center gap-2 rounded-shape-xl bg-secondary-container px-3 py-1 text-label-medium text-on-secondary-container">
                    {s.full_name}
                    {s.class_label && <span className="opacity-75">· {s.class_label}</span>}
                    <button
                      type="button"
                      onClick={() => removeStudent(s.id)}
                      className="-my-2 -mr-2 ml-1 flex min-h-12 min-w-12 items-center justify-center rounded-full text-on-secondary-container/80 hover:text-on-secondary-container focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
                      aria-label="Öğrenciyi kaldır"
                    >
                      <Icon name="close" size="base" />
                    </button>
                  </span>
                </li>
              ))}
            </ul>
          )}
          <Autocomplete<StudentSearchRow>
            label=""
            ariaLabel="İlgili öğrenciler"
            selected={studentDraft}
            onSelect={addStudent}
            onClear={() => setStudentDraft(null)}
            search={async (q) => {
              const res = await studentLookupApi.search(q);
              const pickedIds = new Set(students.map((s) => s.id));
              return res.filter((m) => !pickedIds.has(m.id));
            }}
            getKey={(s) => s.id}
            getLabel={(s) => s.full_name}
            getSublabel={(s) => `${s.class_label || "—"} · No: ${s.student_number || "—"}`}
            placeholder="Ad veya okul numarası…"
            emptyText="Öğrenci bulunamadı."
            helperText="Birden fazla öğrenci ekleyebilirsiniz (aynı dosya çoklu öğrenci olabilir)."
          />
          {students.some((student) => student.guardian_name === "") && (
            <div className="mt-3 space-y-3 rounded-shape-md bg-tertiary-container p-4 text-on-tertiary-container">
              <p className="text-label-large">Eksik veli bilgisi</p>
              <p className="text-body-small">
                Excel şablonunda veli bilgisi bulunmaz. Disiplin işlemine alınan öğrencinin veli adı
                soyadı sicile kaydedilmek üzere zorunlu olarak istenir.
              </p>
              {students
                .filter((student) => student.guardian_name === "")
                .map((student) => (
                  <TextField
                    key={student.id}
                    label={`${student.full_name} — veli adı soyadı`}
                    required
                    value={guardianDrafts[student.id] ?? ""}
                    onChange={(event) =>
                      setGuardianDrafts((prev) => ({
                        ...prev,
                        [student.id]: event.target.value,
                      }))
                    }
                  />
                ))}
            </div>
          )}
        </div>

        {error && (
          <div
            role="alert"
            className="flex items-start gap-2 rounded-shape-sm bg-error-container px-4 py-3 text-body-medium text-on-error-container"
          >
            <Icon name="error" size="lg" />
            <span>{error}</span>
          </div>
        )}

        <div className="flex justify-end gap-2">
          <Button type="button" variant="text" onClick={onCancel}>
            Vazgeç
          </Button>
          <Button type="submit" icon="check" disabled={submitDisabled()}>
            {busy ? "Oluşturuluyor…" : "Dosyayı aç"}
          </Button>
        </div>
      </form>
    </Card>
  );
}
