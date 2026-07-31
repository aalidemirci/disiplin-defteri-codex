// Kurul Toplantı Tutanağı oluşturma formu — md. 184/206. Kurul türü prop ile
// sabittir (her kurul kendi sekmesinde); mount'ta aktif kuruldan katılımcı
// taslağı (prefill) gelir; kullanıcı düzenler (oy hakkı olan üye / oy hakkı
// olmayan davetli — md. 185/6, başkan — md. 188, karşı görüş — md. 206). Disiplin
// kurulunda tutanak türü seçilir: "Disiplin dosyası görüşme" türünde kurula sevkli +
// kararlı bir dosya bağlanır; öğrenci-bazlı resmî kararlar tutanağa otomatik derlenir.
//
// OYS `modules/kurul/ToplantiForm.tsx`'ten UYARLANDI (F4-D3); sapmalar:
// listSchoolYears `./api`'den (sistem modülü yok); dosya seçeneği `students`
// (student_names/decision_count yok); katılımcıda `member_parent_id` yok.

import { useEffect, useId, useRef, useState } from "react";
import type { TextareaHTMLAttributes } from "react";

import { ApiError } from "../../lib/api";
import Button from "../../ui/Button";
import Card from "../../ui/Card";
import Icon from "../../ui/Icon";
import Select from "../../ui/Select";
import { useSnackbar } from "../../ui/SnackbarProvider";
import TextField from "../../ui/TextField";
import {
  ATTENDEE_ROLE_TR,
  DECISION_BASIS_TR,
  MINUTES_TYPE_TR,
  kurulApi,
  listSchoolYears,
} from "./api";
import type {
  AttendeeInput,
  AttendeeRole,
  CaseOption,
  CouncilMeeting,
  CouncilType,
  DecisionBasis,
  HonorMeetingKind,
  MinutesType,
} from "./api";

// M3 outlined çok-satırlı alan (ui/TextField deseni — token tüketir, ham renk yok).
function Textarea({
  label,
  id,
  className = "",
  ...rest
}: { label: string; id: string } & TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return (
    <div className={className}>
      <label htmlFor={id} className="mb-1 block text-label-large text-on-surface-variant">
        {label}
      </label>
      <div className="rounded-shape-xs border border-outline px-3 py-2 focus-within:border-primary focus-within:ring-2 focus-within:ring-primary">
        <textarea
          id={id}
          className="min-h-24 w-full resize-y bg-transparent text-body-large text-on-surface outline-none placeholder:text-on-surface-variant/60"
          {...rest}
        />
      </div>
    </div>
  );
}

// Form içi geçici katılımcı satırı (id yerel anahtar).
interface Row extends AttendeeInput {
  key: string;
}

let rowSeq = 0;
function toRow(a: AttendeeInput): Row {
  rowSeq += 1;
  return { key: `r${rowSeq}`, ...a, title: a.title ?? "", dissent_note: a.dissent_note ?? "" };
}

function emptyRow(role: AttendeeRole = "VOTING_MEMBER"): Row {
  return toRow({
    attendee_role: role,
    person_name: "",
    title: "",
    is_chair: false,
    dissent_note: "",
  });
}

interface Props {
  councilType: CouncilType;
  onCreated: (meeting: CouncilMeeting) => void;
  onCancel: () => void;
}

export default function ToplantiForm({ councilType, onCreated, onCancel }: Props) {
  const snackbar = useSnackbar();
  const idBase = useId();
  const isDiscipline = councilType === "DISCIPLINE";
  const [meetingDate, setMeetingDate] = useState("");
  const [honorMeetingKind, setHonorMeetingKind] = useState<HonorMeetingKind>("BOARD");
  const [decisionBasis, setDecisionBasis] = useState<DecisionBasis>("UNANIMITY");
  const [agenda, setAgenda] = useState("");
  const [decisionText, setDecisionText] = useState("");
  const [notes, setNotes] = useState("");
  const [minutesType, setMinutesType] = useState<MinutesType>("GENERAL");
  const [caseOptions, setCaseOptions] = useState<CaseOption[] | null>(null);
  const [caseId, setCaseId] = useState("");
  const [rows, setRows] = useState<Row[]>([emptyRow()]);
  const [busy, setBusy] = useState(false);
  const [prefilling, setPrefilling] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const prefillRequested = useRef(false);

  const loadPrefill = async (
    type: CouncilType,
    meetingKind: HonorMeetingKind = honorMeetingKind,
  ) => {
    setPrefilling(true);
    setError(null);
    try {
      const data = await kurulApi.prefill(type, meetingKind);
      if (data.attendees.length > 0) {
        setRows(data.attendees.map(toRow));
        snackbar.success("Aktif kurul üyeleri yüklendi; düzenleyebilirsiniz.");
      } else {
        snackbar.show("Aktif kurul bulunamadı; katılımcıları elle ekleyin.");
      }
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Üyeler yüklenemedi.");
    } finally {
      setPrefilling(false);
    }
  };

  // Tür prop'la sabit olduğundan mount'ta bir kez otomatik prefill yapılır.
  useEffect(() => {
    if (prefillRequested.current) return;
    prefillRequested.current = true;
    void loadPrefill(councilType);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [councilType]);

  // Dosya görüşme türü seçilince sevkli + kararlı dosya listesi yüklenir.
  const onMinutesTypeChange = async (type: MinutesType) => {
    setMinutesType(type);
    if (type !== "CASE_REVIEW") {
      setCaseId("");
      return;
    }
    if (caseOptions !== null) return;
    try {
      const data = await kurulApi.caseOptions();
      setCaseOptions(data.cases);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Dosya listesi yüklenemedi.");
    }
  };

  const updateRow = (key: string, patch: Partial<Row>) => {
    setRows((prev) => prev.map((r) => (r.key === key ? { ...r, ...patch } : r)));
  };

  // Başkan tekildir: bir satır başkan işaretlenince diğerleri temizlenir (md. 188).
  const setChair = (key: string) => {
    setRows((prev) => prev.map((r) => ({ ...r, is_chair: r.key === key })));
  };

  const addRow = () => setRows((prev) => [...prev, emptyRow()]);
  const removeRow = (key: string) => setRows((prev) => prev.filter((r) => r.key !== key));

  const onSubmit = async () => {
    setError(null);
    if (!meetingDate) {
      setError("Toplantı tarihi seçilmelidir.");
      return;
    }
    if (minutesType === "CASE_REVIEW" && !caseId) {
      setError("Dosya görüşme tutanağı için bir disiplin dosyası seçilmelidir.");
      return;
    }
    const filled = rows.filter((r) => r.person_name.trim());
    if (filled.filter((r) => r.attendee_role === "VOTING_MEMBER").length === 0) {
      setError("En az bir oy hakkı olan üye eklenmelidir (md. 191).");
      return;
    }
    if (filled.filter((r) => r.is_chair).length !== 1) {
      setError("Tam olarak bir başkan işaretlenmelidir (md. 188).");
      return;
    }
    setBusy(true);
    try {
      const years = await listSchoolYears();
      const activeYear = years.school_years.find((y) => y.is_active);
      if (!activeYear) {
        throw new Error("Aktif ders yılı bulunamadı. Önce Ayarlar'dan bir ders yılı aktive edin.");
      }
      const created = await kurulApi.createMeeting({
        school_year_id: activeYear.id,
        council_type: councilType,
        honor_meeting_kind: honorMeetingKind,
        meeting_date: meetingDate,
        agenda: agenda.trim(),
        decision_text: decisionText.trim(),
        decision_basis: decisionBasis,
        notes: notes.trim(),
        minutes_type: isDiscipline ? minutesType : "GENERAL",
        discipline_case_id: minutesType === "CASE_REVIEW" && caseId ? Number(caseId) : null,
        attendees: filled.map((r, i) => ({
          attendee_role: r.attendee_role,
          person_name: r.person_name.trim(),
          title: (r.title ?? "").trim(),
          is_chair: !!r.is_chair,
          dissent_note: (r.dissent_note ?? "").trim(),
          order: i,
          member_user_id: r.member_user_id ?? null,
          member_student_id: r.member_student_id ?? null,
        })),
      });
      snackbar.success(`Tutanak kaydedildi (Toplantı No: ${created.meeting_no_display}).`);
      onCreated(created);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : (err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card elevation={2} className="space-y-5 p-6">
      <h2 className="text-title-large text-on-surface">Yeni Kurul Toplantı Tutanağı</h2>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <TextField
          label="Toplantı Tarihi"
          type="date"
          value={meetingDate}
          onChange={(e) => setMeetingDate(e.target.value)}
        />
        <Select
          label="Karar Esası"
          value={decisionBasis}
          onChange={(e) => setDecisionBasis(e.target.value as DecisionBasis)}
          options={(Object.keys(DECISION_BASIS_TR) as DecisionBasis[]).map((v) => ({
            value: v,
            label: DECISION_BASIS_TR[v],
          }))}
        />
        {isDiscipline && (
          <Select
            label="Tutanak Türü"
            value={minutesType}
            onChange={(e) => void onMinutesTypeChange(e.target.value as MinutesType)}
            options={(["CASE_REVIEW", "GENERAL"] as MinutesType[]).map((v) => ({
              value: v,
              label: MINUTES_TYPE_TR[v],
            }))}
          />
        )}
        {!isDiscipline && (
          <Select
            label="Toplantı türü"
            value={honorMeetingKind}
            onChange={(event) => {
              const kind = event.target.value as HonorMeetingKind;
              setHonorMeetingKind(kind);
              void loadPrefill(councilType, kind);
            }}
            options={[
              { value: "BOARD", label: "Onur Kurulu (aylık)" },
              { value: "GENERAL_ASSEMBLY", label: "Onur Genel Kurulu (dönemlik)" },
            ]}
          />
        )}
      </div>

      {isDiscipline && minutesType === "CASE_REVIEW" && (
        <div className="space-y-3">
          <Select
            label="Görüşülen Disiplin Dosyası"
            value={caseId}
            onChange={(e) => setCaseId(e.target.value)}
            options={[
              { value: "", label: caseOptions === null ? "Yükleniyor…" : "Dosya seçin…" },
              ...(caseOptions ?? []).map((c) => ({
                value: String(c.id),
                label: `${c.case_no} — ${c.students.join(", ")}`,
              })),
            ]}
          />
          {caseOptions !== null && caseOptions.length === 0 && (
            <Card elevation={0} className="flex items-start gap-2 bg-surface-container-low p-3">
              <Icon name="info" className="shrink-0 text-primary" />
              <p className="text-body-small text-on-surface-variant">
                Bağlanabilecek dosya yok: dosya kurula sevk edilmiş ve en az bir öğrenci için resmî
                kurul kararı (dosya detayı → Kararlar) girilmiş olmalıdır.
              </p>
            </Card>
          )}
          <Card elevation={0} className="flex items-start gap-2 bg-surface-container-low p-3">
            <Icon name="info" className="shrink-0 text-primary" />
            <p className="text-body-small text-on-surface-variant">
              Seçilen dosyanın öğrenci bazlı resmî kararları (ceza türü, gerekçe, karar no/tarihi)
              tutanağa <strong>otomatik eklenir</strong>; burada ayrıca karar girmeniz gerekmez.
              Birden çok öğrenci varsa her biri aynı tutanakta ayrı satırda karara bağlanır.
            </p>
          </Card>
        </div>
      )}

      <Textarea
        id={`${idBase}-agenda`}
        label="Gündem"
        value={agenda}
        onChange={(e) => setAgenda(e.target.value)}
        placeholder="Toplantıda görüşülen konular…"
      />
      <Textarea
        id={`${idBase}-decision`}
        label="Karar (Gerekçeli — md. 206)"
        value={decisionText}
        onChange={(e) => setDecisionText(e.target.value)}
        placeholder="Gerekçeli karar metni…"
      />

      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <h3 className="text-title-medium text-on-surface">Katılanlar</h3>
          <Button
            variant="text"
            icon="download"
            onClick={() => void loadPrefill(councilType, honorMeetingKind)}
            disabled={prefilling}
          >
            Aktif kuruldan yükle
          </Button>
        </div>

        {rows.map((r) => (
          <Card key={r.key} elevation={0} className="space-y-3 bg-surface-container-low p-4">
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              <TextField
                label="Ad Soyad"
                value={r.person_name}
                onChange={(e) => updateRow(r.key, { person_name: e.target.value })}
              />
              <TextField
                label="Görev / Ünvan"
                value={r.title ?? ""}
                onChange={(e) => updateRow(r.key, { title: e.target.value })}
              />
            </div>
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              <Select
                label="Rol"
                value={r.attendee_role}
                onChange={(e) =>
                  updateRow(r.key, {
                    attendee_role: e.target.value as AttendeeRole,
                    // Davetli başkan olamaz (md. 185/6).
                    is_chair: e.target.value === "VOTING_MEMBER" ? r.is_chair : false,
                  })
                }
                options={(Object.keys(ATTENDEE_ROLE_TR) as AttendeeRole[]).map((v) => ({
                  value: v,
                  label: ATTENDEE_ROLE_TR[v],
                }))}
              />
              <label className="flex min-h-12 items-center gap-2 text-body-medium text-on-surface">
                <input
                  type="radio"
                  name={`${idBase}-chair`}
                  checked={!!r.is_chair}
                  disabled={r.attendee_role !== "VOTING_MEMBER"}
                  onChange={() => setChair(r.key)}
                  className="size-5 accent-primary"
                />
                Başkan (md. 188)
              </label>
            </div>
            {r.attendee_role === "VOTING_MEMBER" && (
              <TextField
                label="Karşı görüş gerekçesi (md. 206 — varsa)"
                value={r.dissent_note ?? ""}
                onChange={(e) => updateRow(r.key, { dissent_note: e.target.value })}
              />
            )}
            <div className="flex justify-end">
              <Button
                variant="text"
                icon="delete"
                onClick={() => removeRow(r.key)}
                aria-label="Katılımcıyı kaldır"
              >
                Kaldır
              </Button>
            </div>
          </Card>
        ))}

        <Button variant="outlined" icon="add" onClick={addRow}>
          Katılımcı ekle
        </Button>
      </div>

      <Textarea
        id={`${idBase}-notes`}
        label="Açıklama (opsiyonel)"
        value={notes}
        onChange={(e) => setNotes(e.target.value)}
      />

      {error && (
        <div className="flex items-start gap-2 rounded-shape-sm bg-error-container p-3 text-body-small text-on-error-container">
          <Icon name="error" className="shrink-0" />
          <span>{error}</span>
        </div>
      )}

      <div className="flex justify-end gap-3">
        <Button variant="text" onClick={onCancel} disabled={busy}>
          Vazgeç
        </Button>
        <Button icon="save" onClick={() => void onSubmit()} disabled={busy}>
          {busy ? "Kaydediliyor…" : "Tutanağı Kaydet"}
        </Button>
      </div>
    </Card>
  );
}
