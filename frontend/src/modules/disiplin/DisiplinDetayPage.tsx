// Disiplin dosyası detay sayfası. Bölümler:
//   - Üst bilgi kartı (dosya no, aşama, dilekçe + özet, öğrenciler)
//   - Eylem çubuğu (state-machine'e göre sonraki aşamalar + override)
//   - Olay zaman çizelgesi (events) — her event card'ı aşamaya özgü alanlar gösterir
//   - Ekler (yükleme/indirme/silme)
//
// OYS `modules/disiplin/DisiplinDetayPage.tsx`'ten UYARLANDI (F4-D2). Sapmalar: auth yok
// (caps=ALL_CAPABILITIES; rol kapıları sabit açık, Limited/KVKK blokları yapısal korunur ama
// tetiklenmez); CaseStudent `student_id`→`id` (öğrenci çipi bağlantısız — hedef sayfa yok);
// rehber sevki personel sicili + sınıf sorumluluğundan önerilir, olayda ad snapshot'ı tutulur; ek yanıtı düz
// `is_duplicate` (warnings zarfı yok → snackbar bilgisi); toplantı katılanları `attendee_names`
// + kayıtta event bağı yok (uç kabul etmiyor); uyarıda `issued_by_name` yok; kişi arama
// studentLookupApi (düz dizi) / personnelLookupApi.

import { useCallback, useEffect, useId, useState } from "react";
import type { FormEvent } from "react";
import { Link, useParams } from "react-router-dom";

import { ApiError } from "../../lib/api";
import { saveBlob } from "../../lib/download";
import { SkeletonList } from "../../ui/Skeleton";
import { formatDate, formatDateTime, todayIso } from "../../lib/format";
import DecisionsSection from "./DecisionsSection";
import DocumentsSection from "./DocumentsSection";
import PeriodsSection from "./PeriodsSection";
import Autocomplete from "../../ui/Autocomplete";
import Button from "../../ui/Button";
import Card from "../../ui/Card";
import Dialog from "../../ui/Dialog";
import Icon from "../../ui/Icon";
import Select from "../../ui/Select";
import { useConfirm } from "../../ui/ConfirmProvider";
import { useSnackbar } from "../../ui/SnackbarProvider";
import Stepper from "../../ui/Stepper";
import Tabs, { tabPanelProps } from "../../ui/Tabs";
import TextField from "../../ui/TextField";
import { okulApi } from "../okul/api";
import type { Personnel } from "../okul/api";
import {
  ALL_CAPABILITIES,
  BRANCH_TR,
  caseBranch,
  caseSteps,
  earlierStages,
  nextStepFor,
} from "./workflow";
import type { CaseBranch, CardAction } from "./workflow";
import {
  ATTACHMENT_TYPE_TR,
  COMMITTEE_MEMBER_TYPE_TR,
  disiplinApi,
  isTerminalStage,
  PARTICIPANT_PERSON_TYPE_TR,
  PARTICIPANT_ROLE_TR,
  personnelLookupApi,
  PETITIONER_TR,
  PRINCIPAL_DECISION_TR,
  STAGE_TR,
  studentLookupApi,
} from "./api";
import type {
  AttachmentType,
  CaseStage,
  CaseStudent,
  DisciplineAttachment,
  DisciplineCase,
  DisciplineCommittee,
  DisciplineDecisionType,
  DisciplineEvent,
  DisciplineEventCreateBody,
  DisciplineMeeting,
  DisciplineParticipant,
  DisciplineWarning,
  ParticipantCreateBody,
  ParticipantPersonType,
  ParticipantRole,
  PetitionerRole,
  PrincipalDecision,
  TriageSuggestion,
} from "./api";

const STAGE_CHIP: Record<CaseStage, string> = {
  PETITION: "bg-tertiary-container text-on-tertiary-container",
  GUIDANCE_REFERRED: "bg-primary-container text-on-primary-container",
  GUIDANCE_RETURNED: "bg-secondary-container text-on-secondary-container",
  DECIDED: "bg-secondary-container text-on-secondary-container",
  COMMITTEE_DONE: "bg-primary-container text-on-primary-container",
  CLOSED: "bg-surface-container-high text-on-surface-variant",
};

// Aşama geri al (yalnız ADMIN; Tur 155, Talep 4 Faz 4c) — dosyayı seçilen daha erken aşamaya
// geri alır. Gerçek koruma (admin/orphan/gerekçe) backend'de; bu form yalnız hedef+gerekçe alır.
function RevertStageForm({
  caseId,
  currentStage,
  onCancel,
  onDone,
}: {
  caseId: number;
  currentStage: CaseStage;
  onCancel: () => void;
  onDone: () => void;
}) {
  const targets = earlierStages(currentStage);
  const fieldIdBase = useId();
  const [target, setTarget] = useState<string>(targets[targets.length - 1] ?? "");
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const snackbar = useSnackbar();

  const submit = async () => {
    setBusy(true);
    setError(null);
    try {
      if (!reason.trim()) throw new Error("Gerekçe zorunludur.");
      await disiplinApi.revertStage(caseId, {
        target_stage: target as CaseStage,
        reason: reason.trim(),
      });
      snackbar.success("Aşama geri alındı.");
      onDone();
    } catch (err) {
      const msg = err instanceof ApiError || err instanceof Error ? err.message : "Geri alınamadı.";
      setError(msg);
      setBusy(false);
    }
  };

  return (
    <div className="mt-4 space-y-3 rounded-shape-md border border-outline-variant bg-surface-container-low p-4">
      <p className="flex items-center gap-2 text-title-small text-on-surface">
        <Icon name="undo" size="base" className="text-primary" />
        Aşamayı geri al (yalnız yönetici)
      </p>
      <p className="text-body-small text-on-surface-variant">
        Dosyayı daha erken bir aşamaya geri alır (düzeltme). Gerekçe, işlemi bilinçli yapmanız için
        istenir; program bu metni saklamaz — kalıcı iz gerekiyorsa Evraklar sekmesindeki evrak
        kütüğüne “Belge ekle (manuel)” ile kısa bir not düşün. Karar aşaması öncesine geri almak
        için dosyada karar varsa önce kararı silmelisiniz.
      </p>
      <Select
        label="Hedef aşama"
        value={target}
        onChange={(e) => setTarget(e.target.value)}
        options={targets.map((s) => ({ value: s, label: STAGE_TR[s] }))}
      />
      <div>
        <label
          htmlFor={fieldIdBase}
          className="mb-1 block text-label-large text-on-surface-variant"
        >
          Gerekçe <span className="text-error">*</span>
        </label>
        <textarea
          id={fieldIdBase}
          rows={2}
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          className="block w-full rounded-shape-xs border border-outline bg-surface px-4 py-3 text-body-medium text-on-surface outline-none focus-visible:ring-2 focus-visible:ring-primary focus:border-primary"
        />
      </div>
      {error && (
        <div className="flex items-start gap-2 rounded-shape-sm bg-error-container px-4 py-2 text-body-small text-on-error-container">
          <Icon name="error" size="sm" />
          <span>{error}</span>
        </div>
      )}
      <div className="flex justify-end gap-2">
        <Button type="button" variant="text" onClick={onCancel}>
          Vazgeç
        </Button>
        <Button icon="undo" onClick={submit} disabled={busy || !target}>
          {busy ? "Geri alınıyor…" : "Aşamayı geri al"}
        </Button>
      </div>
    </div>
  );
}

// Dosyayı kapat (Tur 180, Talep 1a) — kurul başkanı/ADMIN. Uygunluk backend'de
// hesaplanıp `close_eligible`/`close_eligible_on` ile gelir; uygun değilse buton pasif,
// ADMIN gerekçeyle erken (override) kapatabilir.
function CloseCaseForm({
  caseObj,
  isAdmin,
  onCancel,
  onDone,
}: {
  caseObj: DisciplineCase;
  isAdmin: boolean;
  onCancel: () => void;
  onDone: () => void;
}) {
  const fieldId = useId();
  const eligible = caseObj.close_eligible === true;
  const eligibleOn = caseObj.close_eligible_on;
  const eligibleReason = caseObj.close_eligible_reason;
  const [overrideReason, setOverrideReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const snackbar = useSnackbar();

  const doClose = async (override: boolean) => {
    setBusy(true);
    setError(null);
    try {
      await disiplinApi.closeCase(
        caseObj.id,
        override ? { override: true, override_reason: overrideReason.trim() } : {},
      );
      snackbar.success("Dosya kapatıldı.");
      onDone();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Dosya kapatılamadı.");
      setBusy(false);
    }
  };

  return (
    <div className="space-y-3 rounded-shape-md border border-outline-variant bg-surface-container-low p-4">
      <p className="flex items-center gap-2 text-title-small text-on-surface">
        <Icon name="lock" size="base" className="text-primary" />
        Dosyayı kapat
      </p>
      {eligible ? (
        <p className="text-body-small text-on-surface-variant">
          Karar(lar) kesinleşti; dosya kapatılabilir. Kapanış sonrası yeni aşama eklenemez
          (gerekirse ADMIN aşamayı geri alır).
        </p>
      ) : (
        <div className="flex items-start gap-2 rounded-shape-sm bg-tertiary-container px-4 py-3 text-body-small text-on-tertiary-container">
          <Icon name="schedule" size="base" />
          <span>
            Dosya henüz kapatılamaz;{" "}
            {eligibleReason || "karar(lar) kesinleşmedi (tebliğ / itiraz süresi / tampon)"}
            {eligibleOn ? ` — en erken ${formatDate(eligibleOn)}` : ""}.
            {isAdmin && " ADMIN olarak gerekçeyle erken kapatabilirsiniz."}
          </span>
        </div>
      )}
      {!eligible && isAdmin && (
        <div>
          <label htmlFor={fieldId} className="mb-1 block text-label-large text-on-surface-variant">
            Erken kapatma gerekçesi <span className="text-error">*</span>
          </label>
          <textarea
            id={fieldId}
            rows={2}
            value={overrideReason}
            onChange={(e) => setOverrideReason(e.target.value)}
            placeholder="Örn. veli elden tebligat almadı, PTT ile tebliğe çıkıldı…"
            className="block w-full rounded-shape-xs border border-outline bg-surface px-4 py-3 text-body-medium text-on-surface outline-none focus-visible:ring-2 focus-visible:ring-primary focus:border-primary"
          />
          <p className="mt-1 text-label-small text-on-surface-variant">
            Gerekçe, erken kapatmayı bilinçli yapmanız için istenir; program bu metni saklamaz —
            kalıcı iz gerekiyorsa evrak kütüğüne manuel bir belge notu ekleyin.
          </p>
        </div>
      )}
      {error && (
        <div className="flex items-start gap-2 rounded-shape-sm bg-error-container px-4 py-2 text-body-small text-on-error-container">
          <Icon name="error" size="sm" />
          <span>{error}</span>
        </div>
      )}
      <div className="flex justify-end gap-2">
        <Button type="button" variant="text" onClick={onCancel} disabled={busy}>
          Vazgeç
        </Button>
        {eligible ? (
          <Button icon="lock" onClick={() => void doClose(false)} disabled={busy}>
            {busy ? "Kapatılıyor…" : "Dosyayı kapat"}
          </Button>
        ) : (
          isAdmin && (
            <Button
              icon="lock"
              onClick={() => void doClose(true)}
              disabled={busy || !overrideReason.trim()}
            >
              {busy ? "Kapatılıyor…" : "Erken kapat (override)"}
            </Button>
          )
        )}
      </div>
    </div>
  );
}

// Dosya künyesi düzeltme (bulgu #22) — dilekçe tarihi/veren/rol/özet. Dosyanın
// öğrenci listesi ve aşaması BURADAN değişmez (onların kendi yolları var);
// backend `PATCH cases/<id>/` yalnız bu dört alanı kabul eder ve kapalı dosyada
// reddeder — buton da o durumda gösterilmez.
function CaseIdentityDialog({
  caseObj,
  onClose,
  onSaved,
}: {
  caseObj: DisciplineCase;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [petitionDate, setPetitionDate] = useState(caseObj.petition_date);
  const [petitionerName, setPetitionerName] = useState(caseObj.petitioner_name);
  const [petitionerRole, setPetitionerRole] = useState<PetitionerRole>(caseObj.petitioner_role);
  const [summary, setSummary] = useState(caseObj.summary);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const snackbar = useSnackbar();
  const fieldId = useId();

  const submit = async () => {
    setBusy(true);
    setError(null);
    try {
      if (!petitionDate) throw new Error("Dilekçe tarihi zorunludur.");
      if (!petitionerName.trim()) throw new Error("Dilekçeyi veren kişi zorunludur.");
      await disiplinApi.patchCase(caseObj.id, {
        petition_date: petitionDate,
        petitioner_name: petitionerName.trim(),
        petitioner_role: petitionerRole,
        summary: summary.trim(),
      });
      snackbar.success("Dosya künyesi güncellendi.");
      onSaved();
    } catch (err) {
      const msg =
        err instanceof ApiError
          ? err.message
          : err instanceof Error
            ? err.message
            : "Künye güncellenemedi.";
      setError(msg);
      setBusy(false);
    }
  };

  return (
    <Dialog
      open
      onClose={onClose}
      title="Dosya künyesini düzenle"
      wide
      actions={
        <>
          <Button type="button" variant="text" onClick={onClose} disabled={busy}>
            Vazgeç
          </Button>
          <Button icon="check" onClick={submit} disabled={busy}>
            {busy ? "Kaydediliyor…" : "Kaydet"}
          </Button>
        </>
      }
    >
      <div className="space-y-4 text-on-surface">
        <p className="text-body-small text-on-surface-variant">
          Yalnız dosya künyesi düzeltilir; öğrenciler Taraflar sekmesinden, aşama ise eylem
          çubuğundan yönetilir.
        </p>
        <TextField
          label="Dilekçe tarihi"
          type="date"
          required
          value={petitionDate}
          onChange={(e) => setPetitionDate(e.target.value)}
        />
        <TextField
          label="Dilekçeyi veren kişi"
          required
          value={petitionerName}
          onChange={(e) => setPetitionerName(e.target.value)}
          placeholder="Ad soyad"
        />
        <Select
          label="Dilekçeyi verenin rolü"
          required
          value={petitionerRole}
          onChange={(e) => setPetitionerRole(e.target.value as PetitionerRole)}
          options={(Object.entries(PETITIONER_TR) as [PetitionerRole, string][]).map(
            ([value, label]) => ({ value, label }),
          )}
        />
        <div>
          <label htmlFor={fieldId} className="mb-1 block text-label-large text-on-surface-variant">
            Olay özeti
          </label>
          <textarea
            id={fieldId}
            rows={4}
            value={summary}
            onChange={(e) => setSummary(e.target.value)}
            className="block w-full rounded-shape-xs border border-outline bg-surface px-4 py-3 text-body-medium text-on-surface outline-none focus-visible:ring-2 focus-visible:ring-primary focus:border-primary"
          />
        </div>

        {error && (
          <div className="flex items-start gap-2 rounded-shape-sm bg-error-container px-4 py-2 text-body-small text-on-error-container">
            <Icon name="error" size="sm" />
            <span>{error}</span>
          </div>
        )}
      </div>
    </Dialog>
  );
}

export default function DisiplinDetayPage() {
  const { id } = useParams<{ id: string }>();
  const caseId = Number(id);
  // Auth yok (tek kullanıcı): operatör tüm aktörleri üstlenir — OYS rol kapıları
  // (CAN_UPDATE_DISCIPLINE_CASE, ADMIN) sabit açık (workflow.ALL_CAPABILITIES).
  const caps = ALL_CAPABILITIES;
  const canUpdate = caps.isMudur || caps.isAdmin;
  const isAdmin = caps.isAdmin;

  const [data, setData] = useState<DisciplineCase | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [adding, setAdding] = useState<CaseStage | "OVERRIDE" | "CLOSE" | null>(null);
  const [uploading, setUploading] = useState(false);
  const [tab, setTab] = useState("genel");
  const [reverting, setReverting] = useState(false);
  const [editingIdentity, setEditingIdentity] = useState(false);

  // `silent`: iskelet göstermeden arka planda tazeler — bölüm içi işlemlerden
  // (katılımcı senkronu gibi) sonra kartların yerinde kalması için.
  const load = useCallback(
    (silent = false) => {
      if (!silent) setLoading(true);
      disiplinApi
        .getCase(caseId)
        .then((c) => {
          setData(c);
          setError(null);
        })
        .catch((e: unknown) => setError(e instanceof ApiError ? e.message : "Dosya yüklenemedi."))
        .finally(() => setLoading(false));
    },
    [caseId],
  );
  useEffect(() => {
    if (Number.isFinite(caseId)) load();
  }, [caseId, load]);

  if (loading) {
    return <SkeletonList rows={5} />;
  }
  if (error || !data) {
    return (
      <div className="space-y-4">
        <Link to="/disiplin" className="text-label-large text-primary hover:underline">
          ← Disiplin listesine dön
        </Link>
        <Card elevation={1} className="p-6">
          <p className="text-body-medium text-error">{error ?? "Dosya bulunamadı."}</p>
        </Card>
      </div>
    );
  }

  // OYS'de backend Limited (KVKK) görünümde events döndürmezdi; tek kullanıcılı
  // masaüstünde detay daima tam döner — bayrak yapısal sadakat için korunur.
  const isLimited = data.events === undefined;
  const terminal = isTerminalStage(data.current_stage);
  const branch = caseBranch(data.events);
  const steps = caseSteps(data.current_stage, branch, data.events);
  // Rol-duyarlı ekran (Tur 112) → tek kullanıcıda tüm yetenekler sabit açık;
  // kurul başkanı eşlemesi (committee_chair_id) gereksizleşti.
  const nextStep = nextStepFor(data.current_stage, branch, caps);
  const runAction = (action: CardAction): void => {
    if (action.kind.type === "stage") setAdding(action.kind.stage);
    else if (action.kind.type === "close") setAdding("CLOSE");
    else setTab(action.kind.tab);
  };
  // Sekme içi bölüm kapıları (Tur 112) — görev ayrımı (müdür / kurul başkanı / memur).
  const canRecordMeeting = caps.isChair || caps.isAdmin;
  const canManageParticipants = caps.isMudur || caps.isChair || caps.isAdmin;
  const canIssueWarning = caps.isMudur || caps.isAdmin;
  const canManageEvrak = caps.isMudur || caps.isChair || caps.isMemur || caps.isAdmin;

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-2 text-label-large text-on-surface-variant">
        <Link to="/disiplin" className="hover:text-on-surface">
          ← Disiplin
        </Link>
        <span>/</span>
        <span className="font-mono text-on-surface">{data.case_no}</span>
      </div>

      {/* Üst bilgi kartı */}
      <Card elevation={2} className="p-6">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <p className="text-headline-small text-on-surface">{data.case_no}</p>
              <span
                className={`inline-flex items-center rounded-shape-xl px-2.5 py-0.5 text-label-medium ${STAGE_CHIP[data.current_stage]}`}
              >
                {STAGE_TR[data.current_stage]}
              </span>
              {branch && (
                <span
                  className={`inline-flex items-center rounded-shape-xl px-2.5 py-0.5 text-label-medium ${
                    branch === "B"
                      ? "bg-primary-container text-on-primary-container"
                      : "bg-tertiary-container text-on-tertiary-container"
                  }`}
                  title={
                    branch === "B"
                      ? "Disiplin/onur kuruluna sevk edildi"
                      : "Yazılı uyarı ile yürüyor (kurul yok)"
                  }
                >
                  {BRANCH_TR[branch]}
                </span>
              )}
              {data.closed_at && (
                <span className="inline-flex items-center rounded-shape-xl bg-surface-container-high px-2 py-0.5 text-label-small text-on-surface-variant">
                  Kapanış: {formatDate(data.closed_at)}
                </span>
              )}
              {isLimited && (
                <span
                  className="inline-flex items-center gap-1 rounded-shape-xl bg-surface-container-high px-2 py-0.5 text-label-small text-on-surface-variant"
                  title="Tam erişim yok; özet, olaylar ve ekler gizli."
                >
                  <Icon name="lock" size="sm" />
                  Sınırlı görünüm
                </span>
              )}
            </div>
            <p className="mt-1 text-body-medium text-on-surface-variant">
              Dilekçe: {formatDate(data.petition_date)}
              {data.petitioner_name && ` · ${data.petitioner_name}`}
              {data.petitioner_role && ` (${PETITIONER_TR[data.petitioner_role]})`}
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-1">
            {/* Künye düzeltmesi kapalı dosyada yapılamaz (backend `update_case`
                da reddeder); kapanış öncesi aşamaya geri alınmalıdır. */}
            {canUpdate && !data.closed_at && (
              <Button variant="text" icon="edit" onClick={() => setEditingIdentity(true)}>
                Künye düzenle
              </Button>
            )}
            {isAdmin && earlierStages(data.current_stage).length > 0 && (
              <Button variant="text" icon="undo" onClick={() => setReverting((v) => !v)}>
                Aşamayı geri al
              </Button>
            )}
          </div>
        </div>
        {editingIdentity && (
          <CaseIdentityDialog
            caseObj={data}
            onClose={() => setEditingIdentity(false)}
            onSaved={() => {
              setEditingIdentity(false);
              load(true);
            }}
          />
        )}
        {reverting && (
          <RevertStageForm
            caseId={caseId}
            currentStage={data.current_stage}
            onCancel={() => setReverting(false)}
            onDone={() => {
              setReverting(false);
              load();
            }}
          />
        )}

        {/* Öğrenciler — OYS'de öğrenci-veli listesine bağlantıydı; standalone'da
            hedef sayfa olmadığından bağlantısız çip olarak gösterilir. */}
        <div className="mt-4">
          <p className="text-label-large text-on-surface-variant">İlgili öğrenciler</p>
          <ul className="mt-2 flex flex-wrap gap-2">
            {data.students.map((s) => (
              <li key={s.id}>
                <span className="inline-flex items-center gap-2 rounded-shape-xl bg-surface-container-low px-3 py-1 text-body-medium text-on-surface">
                  <Icon name="person" size="sm" />
                  {s.full_name}
                  {s.class_label && (
                    <span className="text-label-small text-on-surface-variant">
                      · {s.class_label} · #{s.student_number}
                    </span>
                  )}
                </span>
              </li>
            ))}
          </ul>
        </div>
      </Card>

      {/* Aşama rayı — state-machine görselleştirmesi (Tur 108) */}
      {!isLimited && (
        <Card elevation={1} className="p-4">
          <Stepper items={steps} ariaLabel="Disiplin süreci aşamaları" />
        </Card>
      )}

      {/* Sıradaki adım — state-machine eylemleri bağlam başlığıyla (Tur 108) */}
      {!isLimited && canUpdate && (
        <Card elevation={1} className="p-4">
          {adding === null ? (
            <div className="space-y-3">
              <div className="flex items-start gap-2">
                <Icon name="arrow_forward" className="mt-0.5 text-primary" />
                <div>
                  <p className="text-title-small text-on-surface">{nextStep.title}</p>
                  <p className="text-body-small text-on-surface-variant">{nextStep.description}</p>
                  {nextStep.ownerNote && (
                    <p className="mt-1 flex items-center gap-1 text-label-small text-on-surface-variant">
                      <Icon name="info" size="sm" />
                      {nextStep.ownerNote}
                    </p>
                  )}
                </div>
              </div>
              {(nextStep.actions.length > 0 || (isAdmin && !terminal)) && (
                <div className="flex flex-wrap gap-2">
                  {nextStep.actions.map((action) => (
                    <Button
                      key={action.key}
                      variant={action.variant}
                      icon={action.icon}
                      onClick={() => runAction(action)}
                    >
                      {action.label}
                    </Button>
                  ))}
                  {isAdmin && !terminal && (
                    <Button
                      variant="text"
                      icon="admin_panel_settings"
                      onClick={() => setAdding("OVERRIDE")}
                    >
                      Override (aşama atla)
                    </Button>
                  )}
                </div>
              )}
            </div>
          ) : adding === "CLOSE" ? (
            <CloseCaseForm
              caseObj={data}
              isAdmin={isAdmin}
              onCancel={() => setAdding(null)}
              onDone={() => {
                setAdding(null);
                load();
              }}
            />
          ) : (
            <EventForm
              caseObj={data}
              stage={adding === "OVERRIDE" ? "DECIDED" : adding}
              isOverride={adding === "OVERRIDE"}
              onCancel={() => setAdding(null)}
              onAdded={() => {
                setAdding(null);
                load(); // events listesini güncellemek için detayı yeniden çek
              }}
            />
          )}
        </Card>
      )}

      {/* Aşama-bağlamlı çalışma alanı — sekmeler (Tur 108) */}
      {!isLimited && (
        <div className="space-y-4">
          <Tabs
            ariaLabel="Disiplin dosyası bölümleri"
            active={tab}
            onChange={setTab}
            items={[
              { key: "genel", label: "Genel", icon: "summarize" },
              { key: "taraflar", label: "Taraflar", icon: "groups" },
              { key: "kurul", label: "Kurul & Karar", icon: "gavel" },
              { key: "evraklar", label: "Evraklar", icon: "folder" },
            ]}
            idBase="disiplin-dosya"
          />

          <div {...tabPanelProps("disiplin-dosya", tab)}>
            {/* Genel: olay özeti + aşama geçmişi + triaj */}
            {tab === "genel" && (
              <div className="space-y-6">
                {data.summary && (
                  <Card elevation={1} className="p-6">
                    <p className="text-title-medium text-on-surface">Olay özeti</p>
                    <p className="mt-2 whitespace-pre-wrap text-body-medium text-on-surface">
                      {data.summary}
                    </p>
                  </Card>
                )}
                <EventsTimeline events={data.events ?? []} />
                <TriageSection caseObj={data} />
              </div>
            )}

            {/* Taraflar: rollü katılımcılar + müdür uyarıları */}
            {tab === "taraflar" && (
              <div className="space-y-6">
                <ParticipantsSection
                  caseObj={data}
                  canManage={canManageParticipants}
                  onCaseChanged={() => load(true)}
                />
                <WarningsSection caseObj={data} canManage={canIssueWarning} branch={branch} />
              </div>
            )}

            {/* Kurul & Karar: toplantılar + resmî kararlar/EK-1/itiraz + süreler/uzatma/tedbir */}
            {tab === "kurul" && (
              <div className="space-y-6">
                <MeetingsSection caseObj={data} canManage={canRecordMeeting} />
                <DecisionsSection caseObj={data} caps={caps} onCaseChanged={() => load(true)} />
                <PeriodsSection caseObj={data} caps={caps} />
              </div>
            )}

            {/* Evraklar: evrak üretimi + kütük + dosya ekleri */}
            {tab === "evraklar" && (
              <div className="space-y-6">
                <DocumentsSection caseObj={data} canManage={canManageEvrak} />
                {/* Auth yok: OYS'nin indirme rol kapısı (CAN_DOWNLOAD_DISCIPLINE_FILE)
                    evrak yetkisiyle aynı — sabit açık. */}
                <AttachmentsSection
                  caseObj={data}
                  canDownload={canManageEvrak}
                  canManage={canManageEvrak}
                  uploading={uploading}
                  setUploading={setUploading}
                  onChanged={load}
                />
              </div>
            )}
          </div>
        </div>
      )}

      {isLimited && (
        <Card elevation={1} className="p-6">
          <p className="text-body-medium text-on-surface-variant">
            <Icon name="info" size="base" className="mr-1 align-middle" />
            Bu dosyanın olay özeti, aşama detayları ve dosya ekleri bu görünümde gösterilmiyor.
          </p>
        </Card>
      )}
    </div>
  );
}

function stageIcon(stage: CaseStage): string {
  switch (stage) {
    case "GUIDANCE_REFERRED":
      return "psychology";
    case "GUIDANCE_RETURNED":
      return "psychology_alt";
    case "DECIDED":
      return "gavel";
    case "COMMITTEE_DONE":
      return "how_to_vote";
    case "CLOSED":
      return "lock";
    default:
      return "add";
  }
}

// ---------------------------------------------------------------------------
// Olay zaman çizelgesi
// ---------------------------------------------------------------------------

function EventsTimeline({ events }: { events: DisciplineEvent[] }) {
  if (events.length === 0) {
    return (
      <Card elevation={1} className="p-6">
        <p className="text-title-medium text-on-surface">Aşama geçmişi</p>
        <p className="mt-2 text-body-medium text-on-surface-variant">Henüz aşama kaydı yok.</p>
      </Card>
    );
  }
  return (
    <Card elevation={1} className="p-6">
      <p className="text-title-medium text-on-surface">Aşama geçmişi ({events.length})</p>
      <ol className="mt-4 space-y-4">
        {events.map((e) => (
          <li key={e.id} className="relative pl-8">
            <span className="absolute left-0 top-1 flex h-6 w-6 items-center justify-center rounded-full bg-primary text-on-primary">
              <Icon name={stageIcon(e.stage)} size="sm" />
            </span>
            <div className="rounded-shape-md border border-outline-variant bg-surface-container-low p-4">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <p className="text-body-large text-on-surface">{STAGE_TR[e.stage]}</p>
                <p className="text-label-small text-on-surface-variant">
                  {formatDate(e.event_date)} · kayıt: {formatDateTime(e.recorded_at)}
                </p>
              </div>
              {e.is_override && (
                <p className="mt-1 inline-flex items-center gap-1 rounded-shape-xs bg-error-container px-2 py-0.5 text-label-small text-on-error-container">
                  <Icon name="admin_panel_settings" size="xs" />
                  Override · {e.override_reason || "(gerekçe yok)"}
                </p>
              )}
              <EventStageDetails event={e} />
              {e.notes && (
                <p className="mt-2 whitespace-pre-wrap text-body-medium text-on-surface-variant">
                  {e.notes}
                </p>
              )}
            </div>
          </li>
        ))}
      </ol>
    </Card>
  );
}

function EventStageDetails({ event: e }: { event: DisciplineEvent }) {
  // Sapma: rehber FK yok — yalnız ad snapshot'ı (assigned_guidance_name).
  if (e.stage === "GUIDANCE_REFERRED" && e.assigned_guidance_name) {
    return (
      <p className="mt-1 text-body-small text-on-surface-variant">
        Sevk edilen rehber: {e.assigned_guidance_name}
      </p>
    );
  }
  if (e.stage === "GUIDANCE_RETURNED" && e.guidance_outcome) {
    return (
      <p className="mt-1 whitespace-pre-wrap text-body-medium text-on-surface">
        <span className="text-label-small text-on-surface-variant">Rehberlik raporu: </span>
        {e.guidance_outcome}
      </p>
    );
  }
  if (e.stage === "DECIDED" && e.principal_decisions && e.principal_decisions.length > 0) {
    return (
      <div className="mt-1 flex flex-wrap gap-1">
        {e.principal_decisions.map((d) => (
          <span
            key={d}
            className="inline-flex items-center rounded-shape-xl bg-secondary-container px-2 py-0.5 text-label-small text-on-secondary-container"
          >
            {PRINCIPAL_DECISION_TR[d]}
          </span>
        ))}
      </div>
    );
  }
  if (e.stage === "COMMITTEE_DONE") {
    return (
      <div className="mt-1 space-y-1">
        {e.committee_decision_type && (
          <p className="text-body-small text-on-surface-variant">
            Karar tipi: {e.committee_decision_type_name ?? `#${e.committee_decision_type}`}
          </p>
        )}
        {e.committee_decision_text && (
          <p className="whitespace-pre-wrap text-body-medium text-on-surface">
            {e.committee_decision_text}
          </p>
        )}
      </div>
    );
  }
  return null;
}

// ---------------------------------------------------------------------------
// Yeni aşama formu (state'e özgü alanlar)
// ---------------------------------------------------------------------------

function EventForm({
  caseObj,
  stage,
  isOverride,
  onCancel,
  onAdded,
}: {
  caseObj: DisciplineCase;
  stage: CaseStage;
  isOverride: boolean;
  onCancel: () => void;
  onAdded: () => void;
}) {
  const today = todayIso();

  const [eventDate, setEventDate] = useState(today);
  const [notes, setNotes] = useState("");
  const [selectedStage, setSelectedStage] = useState<CaseStage>(stage);

  // GUIDANCE_REFERRED: seçim personel sicilinden yapılır; sınıf sorumluluğu varsa
  // otomatik önerilir. Olayda FK yerine ad snapshot'ı kalır (geçmiş bütünlüğü).
  const [guidanceName, setGuidanceName] = useState("");
  const [guidancePerson, setGuidancePerson] = useState<Personnel | null>(null);
  const [guidanceHint, setGuidanceHint] = useState(
    "Personel listesinden seçin; ad, unvan veya branşla arayabilirsiniz.",
  );

  const [guidanceOutcome, setGuidanceOutcome] = useState("");

  // Tek seçim (Tur 109): müdür ya uyarır ya bir kurula sevk eder — bir arada olmaz.
  const [principalDecision, setPrincipalDecision] = useState<PrincipalDecision | "">("");

  const [committeeTypeId, setCommitteeTypeId] = useState<string>("");
  const [committeeText, setCommitteeText] = useState("");
  const [decisionTypes, setDecisionTypes] = useState<DisciplineDecisionType[]>([]);

  const [overrideReason, setOverrideReason] = useState("");

  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const snackbar = useSnackbar();
  const fieldIdBase = useId();

  // COMMITTEE_DONE için karar tipi listesi
  useEffect(() => {
    if (selectedStage === "COMMITTEE_DONE") {
      disiplinApi
        .listDecisionTypes()
        .then((types) => setDecisionTypes(types.filter((t) => t.is_active)))
        .catch(() => setDecisionTypes([]));
    }
  }, [selectedStage]);

  useEffect(() => {
    if (selectedStage !== "GUIDANCE_REFERRED" || guidanceName) return;
    let cancelled = false;
    okulApi
      .listClassResponsibilities()
      .then((responsibilities) => {
        if (cancelled) return;
        const labels = new Set(
          caseObj.students.map((student) => student.class_label).filter(Boolean),
        );
        const matched = responsibilities.filter(
          (row) => labels.has(row.class_label) && row.guidance_teacher_detail,
        );
        const candidates = Array.from(
          new Map(
            matched
              .map((row) => row.guidance_teacher_detail)
              .filter((person): person is Personnel => person !== null)
              .map((person) => [person.id, person]),
          ).values(),
        );
        if (candidates.length === 1) {
          setGuidancePerson(candidates[0]);
          setGuidanceName(candidates[0].full_name);
          setGuidanceHint(
            `${Array.from(labels).join(", ")} sınıf sorumluluğundan otomatik önerildi; isterseniz değiştirebilirsiniz.`,
          );
        } else if (candidates.length > 1) {
          setGuidanceHint(
            "Dosyadaki sınıfların rehber öğretmenleri farklı; sevki yürütecek personeli seçin.",
          );
        } else {
          setGuidanceHint(
            "Bu sınıf için eşleştirme yok; bütün personel sicilinde ad, unvan veya branşla arayın.",
          );
        }
      })
      .catch(() =>
        setGuidanceHint(
          "Sınıf eşleştirmesi okunamadı; bütün personel sicilinde arama yapabilirsiniz.",
        ),
      );
    return () => {
      cancelled = true;
    };
  }, [caseObj.students, guidanceName, selectedStage]);

  const searchGuidancePersonnel = useCallback(async (query: string) => {
    const page = await okulApi.listPersonnel({ search: query, limit: 50 });
    return page.results;
  }, []);

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const body: DisciplineEventCreateBody = {
        stage: selectedStage,
        event_date: eventDate,
        notes: notes.trim(),
        override: isOverride,
        override_reason: isOverride ? overrideReason.trim() : "",
      };
      if (selectedStage === "GUIDANCE_REFERRED") {
        if (!guidanceName.trim()) throw new Error("Rehber öğretmen adı zorunludur.");
        body.assigned_guidance_name = guidanceName.trim();
      }
      if (selectedStage === "GUIDANCE_RETURNED") {
        if (!guidanceOutcome.trim()) throw new Error("Rehberlik raporu zorunludur.");
        body.guidance_outcome = guidanceOutcome.trim();
      }
      if (selectedStage === "DECIDED") {
        if (!principalDecision) throw new Error("Müdür değerlendirmesi seçilmelidir (tek seçim).");
        body.principal_decisions = [principalDecision];
      }
      if (selectedStage === "COMMITTEE_DONE") {
        if (!committeeTypeId) throw new Error("Kurul karar tipi seçilmelidir.");
        if (!committeeText.trim()) throw new Error("Kurul karar metni zorunludur.");
        body.committee_decision_type_id = Number(committeeTypeId);
        body.committee_decision_text = committeeText.trim();
      }
      await disiplinApi.addEvent(caseObj.id, body);
      snackbar.success("Aşama eklendi.");
      onAdded();
    } catch (err) {
      const msg =
        err instanceof ApiError
          ? err.message
          : err instanceof Error
            ? err.message
            : "Aşama eklenemedi.";
      setError(msg);
      setBusy(false);
    }
  };

  return (
    <form onSubmit={onSubmit} className="space-y-4">
      <p className="text-title-medium text-on-surface">
        {isOverride ? "Override — aşama atla" : `Yeni aşama: ${STAGE_TR[selectedStage]}`}
      </p>

      {isOverride && (
        <>
          <Select
            label="Hedef aşama"
            required
            value={selectedStage}
            onChange={(e) => setSelectedStage(e.target.value as CaseStage)}
            options={Object.entries(STAGE_TR).map(([value, label]) => ({ value, label }))}
          />
          <TextField
            label="Override gerekçesi"
            required
            value={overrideReason}
            onChange={(e) => setOverrideReason(e.target.value)}
            helperText="Gerekçe aşama kaydında saklanır; zaman çizelgesinde 'Override' rozetiyle görünür."
          />
        </>
      )}

      <TextField
        label="Aşama tarihi"
        type="date"
        required
        value={eventDate}
        onChange={(e) => setEventDate(e.target.value)}
      />

      {/* Aşamaya özgü alanlar */}
      {selectedStage === "GUIDANCE_REFERRED" && (
        <Autocomplete<Personnel>
          label="Rehber öğretmen"
          required
          selected={guidancePerson}
          onSelect={(person) => {
            setGuidancePerson(person);
            setGuidanceName(person.full_name);
          }}
          onClear={() => {
            setGuidancePerson(null);
            setGuidanceName("");
          }}
          search={searchGuidancePersonnel}
          getKey={(person) => person.id}
          getLabel={(person) => person.full_name}
          getSublabel={(person) => [person.title, person.branch].filter(Boolean).join(" · ")}
          minChars={0}
          allowFreeText
          freeText={guidancePerson ? "" : guidanceName}
          onFreeText={setGuidanceName}
          placeholder="Personel listesinden seçin veya ad yazın…"
          helperText={guidanceHint}
        />
      )}

      {selectedStage === "GUIDANCE_RETURNED" && (
        <div>
          <label
            htmlFor={`${fieldIdBase}-guidance`}
            className="mb-1 block text-label-large text-on-surface-variant"
          >
            Rehberlik raporu <span className="text-error">*</span>
          </label>
          <textarea
            id={`${fieldIdBase}-guidance`}
            required
            rows={4}
            value={guidanceOutcome}
            onChange={(e) => setGuidanceOutcome(e.target.value)}
            placeholder="Rehberliğin değerlendirme/raporu (müdür değerlendirmesine esas)."
            className="block w-full rounded-shape-xs border border-outline bg-surface px-4 py-3 text-body-medium text-on-surface outline-none focus-visible:ring-2 focus-visible:ring-primary focus:border-primary"
          />
        </div>
      )}

      {selectedStage === "DECIDED" && (
        <div>
          <p className="mb-1 text-label-large text-on-surface-variant">
            Müdür değerlendirmesi / sevk kararı <span className="text-error">*</span> (tek seçim)
          </p>
          <p className="mb-2 text-body-small text-on-surface-variant">
            Müdür ya uyarır (süreç sicile işlenip kapanır) ya da bir kurula sevk eder; ikisi bir
            arada olmaz. Kurula sevkte süreci kurul başkanı yürütür.
          </p>
          <div className="flex flex-col gap-2">
            {(Object.entries(PRINCIPAL_DECISION_TR) as [PrincipalDecision, string][]).map(
              ([code, label]) => (
                <label
                  key={code}
                  className="flex min-h-12 items-center gap-3 rounded-shape-xs px-2 py-1.5 text-body-medium text-on-surface hover:bg-surface-container-low"
                >
                  <input
                    type="radio"
                    name="principal_decision"
                    checked={principalDecision === code}
                    onChange={() => setPrincipalDecision(code)}
                    className="h-5 w-5 accent-primary"
                  />
                  {label}
                </label>
              ),
            )}
          </div>
        </div>
      )}

      {selectedStage === "COMMITTEE_DONE" && (
        <>
          <Select
            label="Kurul karar tipi"
            required
            value={committeeTypeId}
            onChange={(e) => setCommitteeTypeId(e.target.value)}
            options={decisionTypes.map((t) => ({ value: String(t.id), label: t.name }))}
          />
          {decisionTypes.length === 0 && (
            <p className="text-body-small text-error">
              Aktif karar tipi yok. Önce{" "}
              <Link to="/disiplin/karar-tipleri" className="underline">
                karar tipleri
              </Link>{" "}
              sayfasından eklemelisiniz.
            </p>
          )}
          <div>
            <label
              htmlFor={`${fieldIdBase}-committee`}
              className="mb-1 block text-label-large text-on-surface-variant"
            >
              Kurul karar metni <span className="text-error">*</span>
            </label>
            <textarea
              id={`${fieldIdBase}-committee`}
              required
              rows={4}
              value={committeeText}
              onChange={(e) => setCommitteeText(e.target.value)}
              className="block w-full rounded-shape-xs border border-outline bg-surface px-4 py-3 text-body-medium text-on-surface outline-none focus-visible:ring-2 focus-visible:ring-primary focus:border-primary"
            />
          </div>
        </>
      )}

      <div>
        <label
          htmlFor={`${fieldIdBase}-notes`}
          className="mb-1 block text-label-large text-on-surface-variant"
        >
          Açıklama (opsiyonel)
        </label>
        <textarea
          id={`${fieldIdBase}-notes`}
          rows={2}
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
          className="block w-full rounded-shape-xs border border-outline bg-surface px-4 py-3 text-body-medium text-on-surface outline-none focus-visible:ring-2 focus-visible:ring-primary focus:border-primary"
        />
      </div>

      {error && (
        <div className="flex items-start gap-2 rounded-shape-sm bg-error-container px-4 py-3 text-body-medium text-on-error-container">
          <Icon name="error" size="lg" />
          <span>{error}</span>
        </div>
      )}

      <div className="flex justify-end gap-2">
        <Button type="button" variant="text" onClick={onCancel}>
          Vazgeç
        </Button>
        <Button type="submit" icon="check" disabled={busy}>
          {busy ? "Kaydediliyor…" : "Aşamayı ekle"}
        </Button>
      </div>
    </form>
  );
}

// ---------------------------------------------------------------------------
// Ekler bölümü
// ---------------------------------------------------------------------------

function AttachmentsSection({
  caseObj,
  canDownload,
  canManage,
  uploading,
  setUploading,
  onChanged,
}: {
  caseObj: DisciplineCase;
  canDownload: boolean;
  canManage: boolean;
  uploading: boolean;
  setUploading: (b: boolean) => void;
  onChanged: () => void;
}) {
  const attachments = caseObj.attachments ?? [];
  const [showUpload, setShowUpload] = useState(false);
  return (
    <Card elevation={1} className="p-6">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-title-medium text-on-surface">Ekler ({attachments.length})</p>
        {canManage && !showUpload && (
          <Button variant="tonal" icon="upload_file" onClick={() => setShowUpload(true)}>
            Ek yükle
          </Button>
        )}
      </div>

      {showUpload && (
        <div className="mt-3">
          <AttachmentUploadForm
            caseObj={caseObj}
            uploading={uploading}
            setUploading={setUploading}
            onDone={() => {
              setShowUpload(false);
              onChanged();
            }}
            onCancel={() => setShowUpload(false)}
          />
        </div>
      )}

      {attachments.length === 0 ? (
        <p className="mt-3 text-body-medium text-on-surface-variant">Yüklenmiş ek yok.</p>
      ) : (
        <ul className="mt-3 divide-y divide-outline-variant/50">
          {attachments.map((a) => (
            <AttachmentRow
              key={a.id}
              caseId={caseObj.id}
              attachment={a}
              canDownload={canDownload}
              canManage={canManage}
              onChanged={onChanged}
            />
          ))}
        </ul>
      )}
    </Card>
  );
}

function AttachmentRow({
  caseId,
  attachment: a,
  canDownload,
  canManage,
  onChanged,
}: {
  caseId: number;
  attachment: DisciplineAttachment;
  canDownload: boolean;
  canManage: boolean;
  onChanged: () => void;
}) {
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const snackbar = useSnackbar();
  const confirm = useConfirm();
  const onDownload = async () => {
    setBusy(true);
    setErr(null);
    try {
      const blob = await disiplinApi.downloadAttachment(caseId, a.id);
      saveBlob(blob, a.original_filename);
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : "İndirme başarısız.");
    } finally {
      setBusy(false);
    }
  };
  const onDelete = async () => {
    if (
      !(await confirm({
        message: `'${a.original_filename}' silinsin mi? (Yumuşak silme — geri alınabilir)`,
        confirmLabel: "Sil",
      }))
    )
      return;
    setBusy(true);
    setErr(null);
    try {
      await disiplinApi.deleteAttachment(caseId, a.id);
      snackbar.success("Ek silindi.");
      onChanged();
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : "Silme başarısız.");
      setBusy(false);
    }
  };
  return (
    <li className="flex flex-wrap items-center justify-between gap-3 py-3">
      <div className="min-w-0">
        <p className="truncate text-body-medium text-on-surface">{a.original_filename}</p>
        <p className="text-label-small text-on-surface-variant">
          {ATTACHMENT_TYPE_TR[a.file_type]} · {formatSize(a.file_size_bytes)} ·{" "}
          {formatDateTime(a.uploaded_at)}
        </p>
        {err && <p className="text-label-small text-error">{err}</p>}
      </div>
      <div className="flex gap-1">
        {canDownload && (
          <Button variant="text" icon="download" onClick={onDownload} disabled={busy}>
            İndir
          </Button>
        )}
        {canManage && (
          <Button variant="text" icon="delete" onClick={onDelete} disabled={busy}>
            Sil
          </Button>
        )}
      </div>
    </li>
  );
}

function AttachmentUploadForm({
  caseObj,
  uploading,
  setUploading,
  onDone,
  onCancel,
}: {
  caseObj: DisciplineCase;
  uploading: boolean;
  setUploading: (b: boolean) => void;
  onDone: () => void;
  onCancel: () => void;
}) {
  const [file, setFile] = useState<File | null>(null);
  const [fileType, setFileType] = useState<AttachmentType>("OTHER");
  const [eventId, setEventId] = useState<string>("");
  const [error, setError] = useState<string | null>(null);
  const snackbar = useSnackbar();
  const fieldIdBase = useId();

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (!file) return;
    setUploading(true);
    setError(null);
    try {
      const res = await disiplinApi.uploadAttachment(
        caseObj.id,
        file,
        fileType,
        eventId ? Number(eventId) : undefined,
      );
      snackbar.success("Ek yüklendi.");
      // Sapma #5: OYS {attachment, warnings} zarfı yok — düz kayıt + is_duplicate
      // bayrağı döner; mükerrer içerik snackbar ile bildirilir.
      if (res.is_duplicate) {
        snackbar.show("Bilgi: aynı içerikli bir dosya bu dosyaya daha önce yüklenmişti.");
      }
      onDone();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Yükleme başarısız.");
    } finally {
      setUploading(false);
    }
  };

  return (
    <form onSubmit={onSubmit} className="space-y-3 rounded-shape-md bg-surface-container-low p-4">
      <div>
        <label
          htmlFor={fieldIdBase}
          className="mb-1 block text-label-large text-on-surface-variant"
        >
          Dosya <span className="text-error">*</span>
        </label>
        <input
          id={fieldIdBase}
          type="file"
          required
          onChange={(e) => setFile(e.target.files?.[0] ?? null)}
          className="block w-full text-body-medium text-on-surface file:mr-3 file:rounded-shape-xl file:border-0 file:bg-secondary-container file:px-4 file:py-2 file:text-label-large file:text-on-secondary-container hover:file:opacity-90"
        />
      </div>
      <Select
        label="Ek türü"
        required
        value={fileType}
        onChange={(e) => setFileType(e.target.value as AttachmentType)}
        options={Object.entries(ATTACHMENT_TYPE_TR).map(([value, label]) => ({ value, label }))}
      />
      {(caseObj.events ?? []).length > 0 && (
        <Select
          label="İlgili aşama (opsiyonel)"
          placeholder="Hiçbiri"
          value={eventId}
          onChange={(e) => setEventId(e.target.value)}
          options={(caseObj.events ?? []).map((e) => ({
            value: String(e.id),
            label: `${STAGE_TR[e.stage]} — ${formatDate(e.event_date)}`,
          }))}
        />
      )}
      {error && (
        <div className="flex items-start gap-2 rounded-shape-sm bg-error-container px-4 py-2 text-body-small text-on-error-container">
          <Icon name="error" size="sm" />
          <span>{error}</span>
        </div>
      )}
      <div className="flex justify-end gap-2">
        <Button type="button" variant="text" onClick={onCancel}>
          Vazgeç
        </Button>
        <Button type="submit" icon="upload" disabled={!file || uploading}>
          {uploading ? "Yükleniyor…" : "Yükle"}
        </Button>
      </div>
    </form>
  );
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

// ---------------------------------------------------------------------------
// Kurul toplantıları (Tur 70) — katılanlar kurul üyelerinden seçilir
// ---------------------------------------------------------------------------

function MeetingsSection({ caseObj, canManage }: { caseObj: DisciplineCase; canManage: boolean }) {
  const [meetings, setMeetings] = useState<DisciplineMeeting[] | null>(null);
  const [hidden, setHidden] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [recording, setRecording] = useState(false);

  const load = useCallback(() => {
    disiplinApi
      .listMeetings(caseObj.id)
      .then((list) => {
        setMeetings(list);
        setError(null);
      })
      .catch((e: unknown) => {
        // OYS'de tam erişimi olmayan kullanıcı için 403 → bölüm gizlenirdi;
        // authsuz masaüstünde tetiklenmez ama yapısal sadakat için korunur.
        if (e instanceof ApiError && e.status === 403) {
          setHidden(true);
          return;
        }
        setError(e instanceof ApiError ? e.message : "Toplantılar yüklenemedi.");
      });
  }, [caseObj.id]);
  useEffect(load, [load]);

  if (hidden) return null;

  return (
    <Card elevation={1} className="p-6">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-title-medium text-on-surface">
          Kurul toplantıları ({meetings?.length ?? 0})
        </p>
        {canManage && (
          <Button variant="tonal" icon="event" onClick={() => setRecording(true)}>
            Toplantı kaydet
          </Button>
        )}
      </div>

      {error && (
        <div className="mt-3 flex items-start gap-2 rounded-shape-sm bg-error-container px-4 py-2 text-body-small text-on-error-container">
          <Icon name="error" size="sm" />
          <span>{error}</span>
        </div>
      )}

      {meetings === null ? (
        <SkeletonList rows={3} />
      ) : meetings.length === 0 ? (
        <p className="mt-3 text-body-medium text-on-surface-variant">
          Henüz kurul toplantısı kaydedilmedi. Kurul kararı için toplantıyı ve katılan üyeleri
          buradan kaydedin (tutanak verisi buradan üretilir).
        </p>
      ) : (
        <ul className="mt-3 space-y-3">
          {meetings.map((m) => (
            <li
              key={m.id}
              className="rounded-shape-md border border-outline-variant bg-surface-container-low p-4"
            >
              <p className="text-body-large text-on-surface">
                <Icon name="event" size="base" className="mr-1 align-middle text-primary" />
                {formatDate(m.meeting_date)}
              </p>
              <div className="mt-2">
                <p className="text-label-small text-on-surface-variant">
                  Katılanlar ({m.attendee_names.length})
                </p>
                {/* Sapma #8: attendees yalnız üye id listesi — gösterim ad
                    snapshot'ları (attendee_names) üzerinden yapılır. */}
                {m.attendee_names.length === 0 ? (
                  <p className="text-body-small text-on-surface-variant">—</p>
                ) : (
                  <ul className="mt-1 flex flex-wrap gap-2">
                    {m.attendee_names.map((name, i) => (
                      <li
                        key={m.attendees[i] ?? `${m.id}-${i}`}
                        className="inline-flex items-center gap-1 rounded-shape-xl bg-surface-container px-2.5 py-0.5 text-label-small text-on-surface-variant"
                      >
                        <span className="font-medium text-on-surface">{name}</span>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
              {m.notes && (
                <p className="mt-2 whitespace-pre-wrap text-body-medium text-on-surface-variant">
                  {m.notes}
                </p>
              )}
            </li>
          ))}
        </ul>
      )}

      {recording && (
        <RecordMeetingDialog
          onClose={() => setRecording(false)}
          onDone={() => {
            setRecording(false);
            load();
          }}
          caseObj={caseObj}
        />
      )}
    </Card>
  );
}

function RecordMeetingDialog({
  caseObj,
  onClose,
  onDone,
}: {
  caseObj: DisciplineCase;
  onClose: () => void;
  onDone: () => void;
}) {
  const today = todayIso();
  const [committee, setCommittee] = useState<DisciplineCommittee | null>(null);
  const [loadingCommittee, setLoadingCommittee] = useState(true);
  const [meetingDate, setMeetingDate] = useState(today);
  const [selectedIds, setSelectedIds] = useState<number[]>([]);
  const [notes, setNotes] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const snackbar = useSnackbar();
  const fieldIdBase = useId();

  useEffect(() => {
    disiplinApi
      .getCommittee()
      .then((r) => setCommittee(r.committee))
      .catch(() => setCommittee(null))
      .finally(() => setLoadingCommittee(false));
  }, []);

  const toggle = (id: number) =>
    setSelectedIds((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]));

  const submit = async () => {
    setBusy(true);
    setError(null);
    try {
      // Sapma: MeetingCreateBody'de event bağı yok (OYS'deki "ilgili kurul kararı"
      // seçimi kalktı — uç yalnız tarih + katılanlar + not kabul eder).
      await disiplinApi.recordMeeting(caseObj.id, {
        meeting_date: meetingDate,
        attendee_member_ids: selectedIds,
        notes: notes.trim(),
      });
      snackbar.success("Toplantı kaydedildi.");
      onDone();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Toplantı kaydedilemedi.");
      setBusy(false);
    }
  };

  const members = committee?.members ?? [];

  return (
    <Dialog
      open
      onClose={onClose}
      title="Kurul toplantısı kaydet"
      wide
      actions={
        <>
          <Button type="button" variant="text" onClick={onClose}>
            Vazgeç
          </Button>
          <Button
            icon="check"
            onClick={submit}
            disabled={busy || loadingCommittee || committee === null}
          >
            {busy ? "Kaydediliyor…" : "Kaydet"}
          </Button>
        </>
      }
    >
      {loadingCommittee ? (
        <p className="text-body-medium text-on-surface-variant">Kurul yükleniyor…</p>
      ) : committee === null ? (
        <p className="text-body-medium text-on-surface-variant">
          Aktif disiplin kurulu tanımlı değil. Toplantı katılımcıları kurul üyelerinden seçilir;
          önce{" "}
          <Link to="/disiplin/kurul" className="text-primary underline">
            Disiplin Kurulu
          </Link>{" "}
          tanımlanmalıdır.
        </p>
      ) : (
        <div className="space-y-4 text-on-surface">
          <TextField
            label="Toplantı tarihi"
            type="date"
            required
            value={meetingDate}
            onChange={(e) => setMeetingDate(e.target.value)}
          />

          <div>
            <p className="mb-1 text-label-large text-on-surface-variant">
              Katılan üyeler ({selectedIds.length} seçili)
            </p>
            {members.length === 0 ? (
              <p className="text-body-small text-on-surface-variant">
                Kurulun üyesi yok. Önce kurula üye ekleyin.
              </p>
            ) : (
              <ul className="space-y-1">
                {members.map((m) => (
                  <li key={m.id}>
                    <label className="flex min-h-12 items-center gap-3 rounded-shape-xs px-2 py-1.5 text-body-medium text-on-surface hover:bg-surface-container-low">
                      <input
                        type="checkbox"
                        checked={selectedIds.includes(m.id)}
                        onChange={() => toggle(m.id)}
                        className="h-5 w-5 accent-primary"
                      />
                      <span>
                        {m.member_name}{" "}
                        <span className="text-label-small text-on-surface-variant">
                          · {COMMITTEE_MEMBER_TYPE_TR[m.member_type]}
                          {m.is_substitute ? " (yedek)" : ""}
                          {m.title ? ` · ${m.title}` : ""}
                        </span>
                      </span>
                    </label>
                  </li>
                ))}
              </ul>
            )}
          </div>

          <div>
            <label
              htmlFor={fieldIdBase}
              className="mb-1 block text-label-large text-on-surface-variant"
            >
              Notlar (opsiyonel)
            </label>
            <textarea
              id={fieldIdBase}
              rows={3}
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              className="block w-full rounded-shape-xs border border-outline bg-surface px-4 py-3 text-body-medium text-on-surface outline-none focus-visible:ring-2 focus-visible:ring-primary focus:border-primary"
            />
          </div>

          {error && (
            <div className="flex items-start gap-2 rounded-shape-sm bg-error-container px-4 py-2 text-body-small text-on-error-container">
              <Icon name="error" size="sm" />
              <span>{error}</span>
            </div>
          )}
        </div>
      )}
    </Dialog>
  );
}

// ---------------------------------------------------------------------------
// Rollü katılımcılar (Tur 74 Faz A) — suçlanan / mağdur / tanık (md. 193)
// ---------------------------------------------------------------------------

// Dosyadaki öğrenci adlarını id → ad eşlemesi yapar (uyarı/triaj/katılımcı gösterimi).
function studentNameMap(caseObj: DisciplineCase): Record<number, string> {
  const map: Record<number, string> = {};
  for (const s of caseObj.students) map[s.id] = s.full_name;
  return map;
}

const PARTICIPANT_ROLE_CHIP: Record<ParticipantRole, string> = {
  ACCUSED: "bg-error-container text-on-error-container",
  VICTIM: "bg-tertiary-container text-on-tertiary-container",
  WITNESS: "bg-secondary-container text-on-secondary-container",
};

const PARTICIPANT_ROLE_ORDER: ParticipantRole[] = ["ACCUSED", "VICTIM", "WITNESS"];

function ParticipantsSection({
  caseObj,
  canManage,
  onCaseChanged,
}: {
  caseObj: DisciplineCase;
  canManage: boolean;
  /** Dosya detayını tazeler — katılımcı değişimi öğrenci listesini de değiştirir. */
  onCaseChanged: () => void;
}) {
  const [participants, setParticipants] = useState<DisciplineParticipant[] | null>(null);
  const [hidden, setHidden] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [adding, setAdding] = useState(false);

  const load = useCallback(() => {
    disiplinApi
      .listParticipants(caseObj.id)
      .then((list) => {
        setParticipants(list);
        setError(null);
      })
      .catch((e: unknown) => {
        if (e instanceof ApiError && e.status === 403) {
          setHidden(true);
          return;
        }
        setError(e instanceof ApiError ? e.message : "Katılımcılar yüklenemedi.");
      });
  }, [caseObj.id]);
  useEffect(load, [load]);

  // Backend "hakkında işlem yapılan" (ACCUSED) öğrenci katılımcısını dosyanın
  // öğrenci listesiyle (case_students) senkronlar; o liste uyarı/karar/tedbir/
  // evrak seçicilerini besler — yalnız katılımcıları tazelemek bayat bırakırdı.
  const refresh = () => {
    load();
    onCaseChanged();
  };

  if (hidden) return null;

  const grouped = PARTICIPANT_ROLE_ORDER.map((role) => ({
    role,
    items: (participants ?? []).filter((p) => p.role === role),
  })).filter((g) => g.items.length > 0);

  return (
    <Card elevation={1} className="p-6">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-title-medium text-on-surface">
          Katılımcılar ({participants?.length ?? 0})
        </p>
        {canManage && !adding && (
          <Button variant="tonal" icon="group_add" onClick={() => setAdding(true)}>
            Katılımcı ekle
          </Button>
        )}
      </div>
      <p className="mt-1 text-body-small text-on-surface-variant">
        Hakkında işlem yapılan öğrenci, mağdur ve tanıklar (md. 193 ifade/savunma formları buradan
        üretilir). Hakkında işlem yapılan öğrenci eklemesi dosyanın öğrenci listesiyle senkronlanır.
      </p>

      {adding && (
        <div className="mt-4">
          <AddParticipantForm
            caseObj={caseObj}
            onCancel={() => setAdding(false)}
            onAdded={() => {
              setAdding(false);
              refresh();
            }}
          />
        </div>
      )}

      {error && (
        <div className="mt-3 flex items-start gap-2 rounded-shape-sm bg-error-container px-4 py-2 text-body-small text-on-error-container">
          <Icon name="error" size="sm" />
          <span>{error}</span>
        </div>
      )}

      {participants === null ? (
        <SkeletonList rows={3} />
      ) : participants.length === 0 ? (
        <p className="mt-3 text-body-medium text-on-surface-variant">Henüz katılımcı eklenmedi.</p>
      ) : (
        <div className="mt-4 space-y-5">
          {grouped.map((g) => (
            <div key={g.role}>
              <p className="text-label-large text-on-surface-variant">
                {PARTICIPANT_ROLE_TR[g.role]} ({g.items.length})
              </p>
              <ul className="mt-2 divide-y divide-outline-variant/50">
                {g.items.map((p) => (
                  <ParticipantRow
                    key={p.id}
                    caseId={caseObj.id}
                    participant={p}
                    canManage={canManage}
                    onChanged={refresh}
                  />
                ))}
              </ul>
            </div>
          ))}
        </div>
      )}
    </Card>
  );
}

function ParticipantRow({
  caseId,
  participant: p,
  canManage,
  onChanged,
}: {
  caseId: number;
  participant: DisciplineParticipant;
  canManage: boolean;
  onChanged: () => void;
}) {
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const snackbar = useSnackbar();
  const confirm = useConfirm();

  const name = p.name_snapshot || p.external_name || "—";
  const remove = async () => {
    if (
      !(await confirm({
        message: `'${name}' katılımcı listesinden çıkarılsın mı?`,
        confirmLabel: "Çıkar",
      }))
    )
      return;
    setBusy(true);
    setErr(null);
    try {
      await disiplinApi.removeParticipant(caseId, p.id);
      snackbar.success("Katılımcı çıkarıldı.");
      onChanged();
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : "Çıkarılamadı.");
      setBusy(false);
    }
  };

  return (
    <li className="flex flex-wrap items-center justify-between gap-3 py-3">
      <div className="min-w-0">
        <p className="flex flex-wrap items-center gap-2 text-body-medium text-on-surface">
          <span
            className={`inline-flex items-center rounded-shape-xl px-2 py-0.5 text-label-small ${PARTICIPANT_ROLE_CHIP[p.role]}`}
          >
            {PARTICIPANT_ROLE_TR[p.role]}
          </span>
          <span className="font-medium">{name}</span>
          <span className="text-label-small text-on-surface-variant">
            · {PARTICIPANT_PERSON_TYPE_TR[p.person_type]}
            {p.external_title ? ` · ${p.external_title}` : ""}
          </span>
        </p>
        {p.notes && <p className="text-label-small text-on-surface-variant">{p.notes}</p>}
        {err && <p className="text-label-small text-error">{err}</p>}
      </div>
      {canManage && (
        <Button variant="text" icon="person_remove" onClick={remove} disabled={busy}>
          Çıkar
        </Button>
      )}
    </li>
  );
}

interface PersonOption {
  id: number;
  label: string;
  sublabel?: string;
}

function AddParticipantForm({
  caseObj,
  onCancel,
  onAdded,
}: {
  caseObj: DisciplineCase;
  onCancel: () => void;
  onAdded: () => void;
}) {
  const [role, setRole] = useState<ParticipantRole>("VICTIM");
  const [personType, setPersonType] = useState<ParticipantPersonType>("STUDENT");
  const [person, setPerson] = useState<PersonOption | null>(null);
  const [externalName, setExternalName] = useState("");
  const [externalTitle, setExternalTitle] = useState("");
  const [notes, setNotes] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const snackbar = useSnackbar();
  const fieldIdBase = useId();

  // Tipe göre kişi arama (öğrenci → öğrenci lookup, personel → personel lookup).
  // Sapma #4: studentLookupApi düz dizi döner ({count,results} zarfı yok);
  // personel araması personnelLookupApi (OYS userLookupApi'nin karşılığı).
  const searchPerson = (q: string): Promise<PersonOption[]> => {
    if (personType === "STUDENT") {
      return studentLookupApi.search(q).then((rows) =>
        rows.map((s) => ({
          id: s.id,
          label: s.full_name,
          sublabel: `${s.class_label} · #${s.student_number}`,
        })),
      );
    }
    return personnelLookupApi.search(q).then((rows) =>
      rows.map((u) => ({
        id: u.id,
        label: u.full_name,
        sublabel: [u.title, u.branch].filter(Boolean).join(" · "),
      })),
    );
  };

  const submit = async () => {
    setBusy(true);
    setError(null);
    try {
      const body: ParticipantCreateBody = {
        role,
        person_type: personType,
        notes: notes.trim(),
      };
      if (personType === "EXTERNAL") {
        if (!externalName.trim()) throw new Error("Dış kişi için ad zorunludur.");
        body.external_name = externalName.trim();
        body.external_title = externalTitle.trim();
      } else {
        if (!person) throw new Error("Bir kişi seçilmelidir.");
        body.person_id = person.id;
      }
      await disiplinApi.addParticipant(caseObj.id, body);
      snackbar.success("Katılımcı eklendi.");
      onAdded();
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err.message
          : err instanceof Error
            ? err.message
            : "Katılımcı eklenemedi.",
      );
      setBusy(false);
    }
  };

  return (
    <div className="space-y-4 rounded-shape-md bg-surface-container-low p-4">
      <p className="text-title-medium text-on-surface">Yeni katılımcı</p>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <Select
          label="Rol"
          value={role}
          onChange={(e) => setRole(e.target.value as ParticipantRole)}
          options={PARTICIPANT_ROLE_ORDER.map((value) => ({
            value,
            label: PARTICIPANT_ROLE_TR[value],
          }))}
        />
        <Select
          label="Kişi tipi"
          value={personType}
          onChange={(e) => {
            setPersonType(e.target.value as ParticipantPersonType);
            setPerson(null); // tip değişince kişi sıfırla (lookup farklı)
          }}
          options={(
            Object.entries(PARTICIPANT_PERSON_TYPE_TR) as [ParticipantPersonType, string][]
          ).map(([value, label]) => ({ value, label }))}
        />
      </div>

      {personType === "EXTERNAL" ? (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <TextField
            label="Ad soyad"
            required
            value={externalName}
            onChange={(e) => setExternalName(e.target.value)}
            placeholder="Dış kişinin adı"
          />
          <TextField
            label="Ünvan / sıfat (opsiyonel)"
            value={externalTitle}
            onChange={(e) => setExternalTitle(e.target.value)}
            placeholder="Örn. komşu, kolluk görevlisi"
          />
        </div>
      ) : (
        <Autocomplete<PersonOption>
          key={personType}
          label={`${PARTICIPANT_PERSON_TYPE_TR[personType]} seç`}
          required
          selected={person}
          onSelect={setPerson}
          onClear={() => setPerson(null)}
          search={searchPerson}
          getKey={(p) => p.id}
          getLabel={(p) => p.label}
          getSublabel={(p) => p.sublabel ?? ""}
          placeholder={`${PARTICIPANT_PERSON_TYPE_TR[personType]} adı…`}
          helperText="Listeden seçim yapın (yanlış yazımdan ilişkisiz kayıt önlenir)."
        />
      )}

      <div>
        <label
          htmlFor={fieldIdBase}
          className="mb-1 block text-label-large text-on-surface-variant"
        >
          Not (opsiyonel)
        </label>
        <textarea
          id={fieldIdBase}
          rows={2}
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
          className="block w-full rounded-shape-xs border border-outline bg-surface px-4 py-3 text-body-medium text-on-surface outline-none focus-visible:ring-2 focus-visible:ring-primary focus:border-primary"
        />
      </div>

      {error && (
        <div className="flex items-start gap-2 rounded-shape-sm bg-error-container px-4 py-2 text-body-small text-on-error-container">
          <Icon name="error" size="sm" />
          <span>{error}</span>
        </div>
      )}

      <div className="flex justify-end gap-2">
        <Button type="button" variant="text" onClick={onCancel}>
          Vazgeç
        </Button>
        <Button
          icon="check"
          onClick={submit}
          disabled={busy || (personType !== "EXTERNAL" && !person)}
        >
          {busy ? "Ekleniyor…" : "Katılımcıyı ekle"}
        </Button>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Müdür uyarıları (Tur 74 Faz A) — md. 157/7. CEZA DEĞİLDİR; davranış puanı düşmez.
// ---------------------------------------------------------------------------

function WarningsSection({
  caseObj,
  canManage,
  branch,
}: {
  caseObj: DisciplineCase;
  canManage: boolean;
  branch: CaseBranch;
}) {
  // Kurula sevk edilen dosyada (Dal B) müdür uyarısı uygulanmaz: müdür ya uyarır
  // ya sevk eder, ikisi bir arada olmaz (Tur 109).
  const committeeReferred = branch === "B";
  const [warnings, setWarnings] = useState<DisciplineWarning[] | null>(null);
  const [hidden, setHidden] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [adding, setAdding] = useState(false);
  const names = studentNameMap(caseObj);

  const load = useCallback(() => {
    disiplinApi
      .listWarnings(caseObj.id)
      .then((list) => {
        setWarnings(list);
        setError(null);
      })
      .catch((e: unknown) => {
        if (e instanceof ApiError && e.status === 403) {
          setHidden(true);
          return;
        }
        setError(e instanceof ApiError ? e.message : "Uyarılar yüklenemedi.");
      });
  }, [caseObj.id]);
  useEffect(load, [load]);

  if (hidden) return null;

  return (
    <Card elevation={1} className="p-6">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-title-medium text-on-surface">
          Müdür uyarıları ({warnings?.length ?? 0})
        </p>
        {canManage && !adding && !committeeReferred && (
          <Button variant="tonal" icon="campaign" onClick={() => setAdding(true)}>
            Uyarı ekle
          </Button>
        )}
      </div>
      {committeeReferred ? (
        <p className="mt-1 flex items-start gap-1 text-body-small text-on-surface-variant">
          <Icon name="info" size="sm" />
          Bu dosya kurula sevk edildi; müdür uyarısı uygulanmaz (müdür ya uyarır ya sevk eder).
        </p>
      ) : (
        <p className="mt-1 text-body-small text-on-surface-variant">
          Md. 157/7 ilk uyarı — ceza değildir, davranış puanını düşürmez. Tekrarı kurula sevki
          gerektirebilir (aşağıdaki triaj önerisine bakın).
        </p>
      )}

      {adding && (
        <div className="mt-4">
          <AddWarningForm
            caseObj={caseObj}
            onCancel={() => setAdding(false)}
            onAdded={() => {
              setAdding(false);
              load();
            }}
          />
        </div>
      )}

      {error && (
        <div className="mt-3 flex items-start gap-2 rounded-shape-sm bg-error-container px-4 py-2 text-body-small text-on-error-container">
          <Icon name="error" size="sm" />
          <span>{error}</span>
        </div>
      )}

      {warnings === null ? (
        <SkeletonList rows={3} />
      ) : warnings.length === 0 ? (
        <p className="mt-3 text-body-medium text-on-surface-variant">
          Henüz müdür uyarısı kaydedilmedi.
        </p>
      ) : (
        <ul className="mt-3 space-y-3">
          {warnings.map((w) => (
            <li
              key={w.id}
              className="rounded-shape-md border border-outline-variant bg-surface-container-low p-4"
            >
              <div className="flex flex-wrap items-center justify-between gap-2">
                <p className="text-body-large text-on-surface">
                  <Icon name="campaign" size="base" className="mr-1 align-middle text-primary" />
                  {names[w.student] ?? `Öğrenci #${w.student}`}
                </p>
                {/* Sapma #6: issued_by_name yok — yalnız tarih gösterilir. */}
                <p className="text-label-small text-on-surface-variant">
                  {formatDate(w.warning_date)}
                </p>
              </div>
              {w.summary && (
                <p className="mt-2 whitespace-pre-wrap text-body-medium text-on-surface-variant">
                  {w.summary}
                </p>
              )}
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

function AddWarningForm({
  caseObj,
  onCancel,
  onAdded,
}: {
  caseObj: DisciplineCase;
  onCancel: () => void;
  onAdded: () => void;
}) {
  const today = todayIso();
  const students = caseObj.students;
  const [studentId, setStudentId] = useState<string>(
    students.length === 1 ? String(students[0].id) : "",
  );
  const [warningDate, setWarningDate] = useState(today);
  const [summary, setSummary] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const snackbar = useSnackbar();
  const fieldIdBase = useId();

  const submit = async () => {
    setBusy(true);
    setError(null);
    try {
      if (!studentId) throw new Error("Bir öğrenci seçilmelidir.");
      if (!summary.trim()) throw new Error("Uyarı özeti zorunludur.");
      await disiplinApi.addWarning(caseObj.id, {
        student_id: Number(studentId),
        warning_date: warningDate,
        summary: summary.trim(),
      });
      snackbar.success("Uyarı kaydedildi.");
      onAdded();
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err.message
          : err instanceof Error
            ? err.message
            : "Uyarı eklenemedi.",
      );
      setBusy(false);
    }
  };

  return (
    <div className="space-y-4 rounded-shape-md bg-surface-container-low p-4">
      <p className="text-title-medium text-on-surface">Yeni müdür uyarısı</p>
      <Select
        label="Öğrenci"
        required
        placeholder="Seçiniz…"
        value={studentId}
        onChange={(e) => setStudentId(e.target.value)}
        options={students.map((s: CaseStudent) => ({
          value: String(s.id),
          label: s.class_label ? `${s.full_name} · ${s.class_label}` : s.full_name,
        }))}
        helperText="Uyarı dosyadaki bir öğrenciye verilir (md. 157/7)."
      />
      <TextField
        label="Uyarı tarihi"
        type="date"
        required
        value={warningDate}
        onChange={(e) => setWarningDate(e.target.value)}
      />
      <div>
        <label
          htmlFor={fieldIdBase}
          className="mb-1 block text-label-large text-on-surface-variant"
        >
          Uyarı özeti <span className="text-error">*</span>
        </label>
        <textarea
          id={fieldIdBase}
          required
          rows={3}
          value={summary}
          onChange={(e) => setSummary(e.target.value)}
          placeholder="Uyarının konusu / gerekçesi."
          className="block w-full rounded-shape-xs border border-outline bg-surface px-4 py-3 text-body-medium text-on-surface outline-none focus-visible:ring-2 focus-visible:ring-primary focus:border-primary"
        />
      </div>

      {error && (
        <div className="flex items-start gap-2 rounded-shape-sm bg-error-container px-4 py-2 text-body-small text-on-error-container">
          <Icon name="error" size="sm" />
          <span>{error}</span>
        </div>
      )}

      <div className="flex justify-end gap-2">
        <Button type="button" variant="text" onClick={onCancel}>
          Vazgeç
        </Button>
        <Button icon="check" onClick={submit} disabled={busy || !studentId}>
          {busy ? "Kaydediliyor…" : "Uyarıyı kaydet"}
        </Button>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Triaj önerisi (Tur 74 Faz A) — md. 157/7, 166. Sadece öneri; nihai karar müdürün.
// ---------------------------------------------------------------------------

function TriageSection({ caseObj }: { caseObj: DisciplineCase }) {
  const [data, setData] = useState<TriageSuggestion | null>(null);
  const [hidden, setHidden] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const names = studentNameMap(caseObj);

  useEffect(() => {
    disiplinApi
      .triageSuggestion(caseObj.id)
      .then((r) => {
        setData(r);
        setError(null);
      })
      .catch((e: unknown) => {
        if (e instanceof ApiError && e.status === 403) {
          setHidden(true);
          return;
        }
        setError(e instanceof ApiError ? e.message : "Triaj önerisi yüklenemedi.");
      });
  }, [caseObj.id]);

  if (hidden) return null;

  return (
    <Card elevation={1} className="p-6">
      <p className="text-title-medium text-on-surface">Triaj önerisi</p>
      <p className="mt-1 text-body-small text-on-surface-variant">
        Hakkında işlem yapılan öğrencilerin geçmişi (md. 157/7, 166). Yalnızca bir öneridir — nihai
        sevk kararını müdür verir.
      </p>

      {error && (
        <div className="mt-3 flex items-start gap-2 rounded-shape-sm bg-error-container px-4 py-2 text-body-small text-on-error-container">
          <Icon name="error" size="sm" />
          <span>{error}</span>
        </div>
      )}

      {data === null ? (
        !error && <SkeletonList rows={3} />
      ) : data.students.length === 0 ? (
        <p className="mt-3 text-body-medium text-on-surface-variant">
          Suçlanan öğrenci bulunmadığından triaj önerisi yok.
        </p>
      ) : (
        <>
          <div
            className={`mt-3 flex items-start gap-2 rounded-shape-sm px-4 py-3 text-body-medium ${
              data.should_route_to_committee
                ? "bg-error-container text-on-error-container"
                : "bg-secondary-container text-on-secondary-container"
            }`}
          >
            <Icon
              name={data.should_route_to_committee ? "how_to_vote" : "check_circle"}
              size="lg"
            />
            <span>
              {data.should_route_to_committee
                ? "Öneri: en az bir öğrencinin geçmişi disiplin kuruluna sevki gerektirebilir."
                : "Öneri: kurula sevki gerektiren tekrar tespit edilmedi."}
            </span>
          </div>
          <ul className="mt-3 divide-y divide-outline-variant/50">
            {data.students.map((s) => (
              <li
                key={s.student_id}
                className="flex flex-wrap items-center justify-between gap-3 py-3"
              >
                <p className="text-body-medium text-on-surface">
                  {names[s.student_id] ?? `Öğrenci #${s.student_id}`}
                </p>
                <div className="flex flex-wrap items-center gap-2 text-label-small">
                  <span className="inline-flex items-center gap-1 rounded-shape-xl bg-surface-container px-2.5 py-0.5 text-on-surface-variant">
                    <Icon name="campaign" size="xs" />
                    {s.warning_count} uyarı
                  </span>
                  <span className="inline-flex items-center gap-1 rounded-shape-xl bg-surface-container px-2.5 py-0.5 text-on-surface-variant">
                    <Icon name="gavel" size="xs" />
                    {s.penalty_count} ceza
                  </span>
                  {s.should_route_to_committee && (
                    <span className="inline-flex items-center gap-1 rounded-shape-xl bg-error-container px-2.5 py-0.5 text-on-error-container">
                      <Icon name="how_to_vote" size="xs" />
                      Kurula sevk önerilir
                    </span>
                  )}
                </div>
              </li>
            ))}
          </ul>
        </>
      )}
    </Card>
  );
}
