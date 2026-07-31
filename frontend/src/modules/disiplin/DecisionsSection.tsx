// OYS `frontend/src/modules/disiplin/DecisionsSection.tsx`'ten UYARLANDI (F4-D2).
// Sapmalar: auth yok — `caps` prop'u opsiyonel, varsayılan ALL_CAPABILITIES (tüm
// eylemler görünür); CaseStudent `student_id` → `id`; itirazda `filed_by_role_display`
// yerine APPEAL_FILED_BY_ROLE_TR sözlüğü (alan standalone serializer'da yok).
//
// Disiplin resmî kararları + itirazları + EK-1 anlatı alanları (Tur 79, Faz E2).
// Backend: DisciplineCaseViewSet.decisions / decision_approve / decision_notify /
// decision_narrative / decision_appeals / appeal_forward / appeal_resolve
// (Tur 72 Faz 6 + Tur 76 Faz C). md. 163-172.
//
// 403 → bölüm sessizce gizlenir deseni OYS'den korunur (tek kullanıcılı masaüstünde
// pratikte tetiklenmez; savunmacı davranış).

import { useCallback, useEffect, useId, useState } from "react";

import { ApiError } from "../../lib/api";
import { useAutosave } from "../../hooks/useAutosave";
import type { AutosaveStatus } from "../../hooks/useAutosave";
import { SkeletonList } from "../../ui/Skeleton";
import { formatDate, todayIso } from "../../lib/format";
import Button from "../../ui/Button";
import Card from "../../ui/Card";
import Icon from "../../ui/Icon";
import Select from "../../ui/Select";
import { useConfirm } from "../../ui/ConfirmProvider";
import { useSnackbar } from "../../ui/SnackbarProvider";
import TextField from "../../ui/TextField";
import {
  APPEAL_FILED_BY_ROLE_TR,
  APPEAL_RESULT_TR,
  DECISION_APPROVAL_STATUS_TR,
  disiplinApi,
  PENALTY_TYPE_TR,
} from "./api";
import { asMessage, FormError, PanelActions, PanelShell } from "./formHelpers";
import SelectOrOther from "./SelectOrOther";
import Dialog from "../../ui/Dialog";
import { NARRATIVE_TEMPLATES } from "./decisionTemplates";
import type { NarrativeTemplate } from "./decisionTemplates";
import type {
  AppealFiledByRole,
  AppealResult,
  CaseStudent,
  DecisionApprovalStatus,
  DecisionCreateBody,
  DecisionEditBody,
  DecisionNarrative,
  DecisionNarrativeBody,
  DisciplineAppeal,
  DisciplineCase,
  DisciplineDecision,
  PenaltyType,
} from "./api";
import { ALL_CAPABILITIES } from "./workflow";
import type { DisciplineCapabilities } from "./workflow";

// Dosyadaki öğrenci id → ad eşlemesi (karar/itiraz gösterimi).
function studentNames(caseObj: DisciplineCase): Record<number, string> {
  const map: Record<number, string> = {};
  for (const s of caseObj.students) map[s.id] = s.full_name;
  return map;
}

const APPROVAL_STATUS_CHIP: Record<DecisionApprovalStatus, string> = {
  PENDING: "bg-tertiary-container text-on-tertiary-container",
  APPROVED: "bg-secondary-container text-on-secondary-container",
  RETURNED: "bg-tertiary-container text-on-tertiary-container",
  REFERRED: "bg-primary-container text-on-primary-container",
  REJECTED: "bg-error-container text-on-error-container",
};

const APPEAL_RESULT_CHIP: Record<AppealResult, string> = {
  PENDING: "bg-tertiary-container text-on-tertiary-container",
  UPHELD: "bg-secondary-container text-on-secondary-container",
  REDUCED: "bg-primary-container text-on-primary-container",
  OVERTURNED: "bg-error-container text-on-error-container",
};

// Olayla ilgili anlatı (md. 168 takdir + md. 193 ifade/delil).
// `template` verilen alanlarda "Şablon ekle" butonu çıkar (Tur 149, Faz C) — OYS verisiyle
// ön-dolu standart kanaat taslağını alana basar (kurul düzenler).
// Şablon düğmesi (Tur 219): alanın varyantları NARRATIVE_TEMPLATES kayıt
// defterinden türetilir — ayrı template bayrağı kalktı.
const NARRATIVE_FIELDS: { key: keyof DecisionNarrative; label: string }[] = [
  { key: "accused_statement_summary", label: "Hakkında işlem yapılan öğrenci ifade özeti" },
  { key: "witness_statement_summary", label: "Tanık ifade özeti" },
  { key: "other_evidence", label: "Diğer deliller" },
  { key: "mitigating_aggravating", label: "Hafifletici / ağırlaştırıcı sebepler" },
  { key: "committee_opinion", label: "Kurul kanaati" },
  { key: "psychosocial_summary", label: "Psikososyal değerlendirme özeti" },
];

// EK-1 öğrenci-bağlam alanları (Tur 107) — resmî EK-1 "ÖĞRENCİNİN" bloğu.
// "Önceki cezalar" karar anında OYS'den otomatik derlenir; tümü düzenlenebilir.
// `options` verilen alanlar "Seçim + Diğer" (SelectOrOther) ile render edilir (Tur 148,
// Faz B); seçilen değer Türkçe etiket olarak CharField'a yazılır (backend/migration YOK,
// EK-1 belgesi metni aynen basar). Diğerleri serbest metin (sağlık/çevre/yer narrative).
const EK1_CONTEXT_FIELDS: {
  key: keyof DecisionNarrative;
  label: string;
  rows?: number;
  options?: string[];
}[] = [
  { key: "prior_penalties_summary", label: "Şimdiye kadar aldığı cezalar ve genel durumu" },
  {
    key: "boarding_status",
    label: "Paralı/parasız yatılı ya da gündüzlü",
    options: ["Gündüzlü", "Parasız yatılı", "Paralı yatılı"],
  },
  {
    key: "academic_standing",
    label: "Başarı durumu",
    // Tur 181 (Talep 1c) — standart seçilebilir metinler + "Diğer…" (SelectOrOther).
    options: ["Başarılı", "Orta düzeyde başarılı", "Başarısız", "Devamsızlık nedeniyle başarısız"],
  },
  {
    key: "health_status",
    label: "Sağlık durumu",
    options: [
      "Bilinen sağlık sorunu yok",
      "Kronik rahatsızlığı var",
      "Sürekli ilaç kullanıyor",
      "Engel/özel gereksinim durumu var",
    ],
  },
  {
    key: "family_economic_status",
    label: "Ailesinin ekonomik durumu",
    options: ["İyi", "Orta", "Düşük"],
  },
  {
    key: "lives_with_family",
    label: "Ailesi ile birlikte oturup oturmadığı",
    options: ["Ailesiyle birlikte", "Ailesinden ayrı"],
  },
  {
    key: "parents_alive",
    label: "Anne-babasının sağ olup olmadığı",
    options: ["İkisi de sağ", "Anne vefat etti", "Baba vefat etti", "İkisi de vefat etti"],
  },
  {
    key: "parents_biological",
    label: "Anne-babasının öz olup olmadığı",
    options: ["Öz anne-baba", "Üvey anne", "Üvey baba", "Üvey anne-baba"],
  },
  {
    key: "studies_near_family",
    label: "Ailesinin yanında okuyup okumadığı",
    options: ["Ailesinin yanında", "Ailesinden uzakta"],
  },
  { key: "upbringing_environment", label: "Büyüyüp yetiştiği çevre", rows: 2 },
  { key: "family_residence_area", label: "Ailesinin oturduğu yer ve çevresi", rows: 2 },
  { key: "incident_place", label: "Davranışın yapıldığı yer", rows: 1 },
];

// ===========================================================================
// Ana bölüm
// ===========================================================================

export default function DecisionsSection({
  caseObj,
  caps = ALL_CAPABILITIES,
  onCaseChanged,
}: {
  caseObj: DisciplineCase;
  caps?: DisciplineCapabilities;
  onCaseChanged?: () => void;
}) {
  // Kurul kararı girişi başkana aittir (md. 196 — başkan kararı müdüre sunar).
  const canEnterDecision = caps.isChair || caps.isAdmin;
  const [decisions, setDecisions] = useState<DisciplineDecision[] | null>(null);
  const [behaviorPoints, setBehaviorPoints] = useState<Record<number, number>>({});
  const [hidden, setHidden] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [adding, setAdding] = useState(false);
  const [deletedDecisions, setDeletedDecisions] = useState<DisciplineDecision[] | null>(null);
  const [showTrash, setShowTrash] = useState(false);
  const names = studentNames(caseObj);
  const snackbar = useSnackbar();
  const confirm = useConfirm();

  const load = useCallback(() => {
    disiplinApi
      .listDecisions(caseObj.id)
      .then((r) => {
        setDecisions(r.decisions);
        setBehaviorPoints(r.behavior_points ?? {});
        setError(null);
      })
      .catch((e: unknown) => {
        if (e instanceof ApiError && e.status === 403) {
          setHidden(true);
          return;
        }
        setError(e instanceof ApiError ? e.message : "Kararlar yüklenemedi.");
      });
  }, [caseObj.id]);
  useEffect(load, [load]);

  const refresh = useCallback(() => {
    load();
    onCaseChanged?.();
  }, [load, onCaseChanged]);

  // Çöp kutusu (silinmiş kararlar) — geri yükleme için lazy yüklenir.
  const loadDeleted = useCallback(() => {
    disiplinApi
      .listDeletedDecisions(caseObj.id)
      .then(setDeletedDecisions)
      .catch(() => setDeletedDecisions([]));
  }, [caseObj.id]);

  const handleRestore = useCallback(
    async (decisionId: number) => {
      try {
        await disiplinApi.restoreDecision(caseObj.id, decisionId);
        refresh();
        // Koşulsuz: "Geri al" snackbar'ı silme anındaki `showTrash`'i taşır; çöp
        // kutusu ARADA açılmışsa geri alınan kayıt iki listede birden görünürdü.
        loadDeleted();
        snackbar.success("Karar geri yüklendi.");
      } catch (e) {
        snackbar.error(e instanceof ApiError ? e.message : "Karar geri yüklenemedi.");
      }
    },
    [caseObj.id, loadDeleted, refresh, snackbar],
  );

  const handleDelete = useCallback(
    async (decision: DisciplineDecision) => {
      const ok = await confirm({
        message: `${decision.penalty_type_display} kararı silinsin mi? (Yumuşak silme — geri alınabilir)`,
        confirmLabel: "Sil",
      });
      if (!ok) return;
      try {
        await disiplinApi.deleteDecision(caseObj.id, decision.id);
        refresh();
        if (showTrash) loadDeleted();
        snackbar.success("Karar silindi.", {
          action: { label: "Geri al", onClick: () => void handleRestore(decision.id) },
        });
      } catch (e) {
        snackbar.error(e instanceof ApiError ? e.message : "Karar silinemedi.");
      }
    },
    [caseObj.id, confirm, handleRestore, loadDeleted, refresh, showTrash, snackbar],
  );

  const toggleTrash = () => {
    const next = !showTrash;
    setShowTrash(next);
    if (next && deletedDecisions === null) loadDeleted();
  };

  if (hidden) return null;

  const pointEntries = caseObj.students.map((s) => ({
    student: s,
    point: behaviorPoints[s.id],
  }));

  return (
    <Card elevation={1} className="p-6">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-title-medium text-on-surface">
          Resmî kararlar ({decisions?.length ?? 0})
        </p>
        {canEnterDecision && !adding && (
          <Button variant="tonal" icon="gavel" onClick={() => setAdding(true)}>
            Karar ekle
          </Button>
        )}
      </div>
      <p className="mt-1 text-body-small text-on-surface-variant">
        Md. 163 ceza türleri; davranış puanı indirimi (md. 170), onay mercii (md. 163/2) ve itiraz
        son günü (md. 169/3) otomatik hesaplanır.
      </p>

      {/* Davranış puanı özeti (md. 170 — 100 üzerinden, bozulmamış indirimler düşülür) */}
      {pointEntries.some((e) => e.point !== undefined) && (
        <div className="mt-4 flex flex-wrap gap-2">
          {pointEntries.map((e) => (
            <span
              key={e.student.id}
              className="inline-flex items-center gap-1.5 rounded-shape-xl bg-surface-container px-3 py-1 text-label-medium text-on-surface-variant"
              title="Davranış puanı (md. 170) — 100 üzerinden kalan."
            >
              <Icon name="grade" size="sm" className="text-primary" />
              <span className="text-on-surface">{e.student.full_name}</span>
              <span className="font-medium text-on-surface">{e.point ?? 100}</span>
              <span>/ 100</span>
            </span>
          ))}
        </div>
      )}

      {adding && (
        <div className="mt-4">
          <AddDecisionForm
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

      {decisions === null ? (
        <SkeletonList rows={3} />
      ) : decisions.length === 0 ? (
        <p className="mt-3 text-body-medium text-on-surface-variant">
          Henüz resmî karar kaydedilmedi.
        </p>
      ) : (
        <div className="mt-4 space-y-4">
          {decisions.map((d) => (
            <DecisionCard
              key={d.id}
              caseObj={caseObj}
              decision={d}
              studentName={names[d.student] ?? `Öğrenci #${d.student}`}
              caps={caps}
              onChanged={refresh}
              onDelete={handleDelete}
            />
          ))}
        </div>
      )}

      {/* Çöp kutusu — silinmiş kararlar (lazy; geri yükleme için). Tur 153. */}
      {canEnterDecision && (
        <div className="mt-5 border-t border-outline-variant pt-4">
          <Button
            variant="text"
            icon={showTrash ? "expand_less" : "delete_outline"}
            onClick={toggleTrash}
            aria-expanded={showTrash}
          >
            Silinmiş kararlar{deletedDecisions ? ` (${deletedDecisions.length})` : ""}
          </Button>
          {showTrash &&
            (deletedDecisions === null ? (
              <SkeletonList rows={2} />
            ) : deletedDecisions.length === 0 ? (
              <p className="mt-2 text-body-small text-on-surface-variant">Çöp kutusu boş.</p>
            ) : (
              <ul className="mt-2 space-y-2">
                {deletedDecisions.map((d) => (
                  <li
                    key={d.id}
                    className="flex flex-wrap items-center justify-between gap-2 rounded-shape-md border border-outline-variant bg-surface-container-low px-4 py-2"
                  >
                    <span className="min-w-0 text-body-medium text-on-surface-variant">
                      <Icon name="gavel" size="sm" className="mr-1 align-middle text-primary" />
                      <span className="text-on-surface">
                        {names[d.student] ?? `Öğrenci #${d.student}`}
                      </span>
                      <span className="text-label-small"> · {d.penalty_type_display}</span>
                      <span className="text-label-small"> · {formatDate(d.decision_date)}</span>
                    </span>
                    <Button variant="text" icon="restore" onClick={() => void handleRestore(d.id)}>
                      Geri yükle
                    </Button>
                  </li>
                ))}
              </ul>
            ))}
        </div>
      )}
    </Card>
  );
}

// ===========================================================================
// Karar kartı
// ===========================================================================

type CardPanel =
  "approve" | "notify" | "e-school" | "narrative" | "appeal" | "return" | "refer" | "edit" | null;

function DecisionCard({
  caseObj,
  decision: d,
  studentName,
  caps,
  onChanged,
  onDelete,
}: {
  caseObj: DisciplineCase;
  decision: DisciplineDecision;
  studentName: string;
  caps: DisciplineCapabilities;
  onChanged: () => void;
  onDelete: (decision: DisciplineDecision) => void;
}) {
  const [panel, setPanel] = useState<CardPanel>(null);
  const hasNarrative = NARRATIVE_FIELDS.some((f) => (d[f.key] || "").trim().length > 0);
  // Görev ayrımı (Tur 112): onay + itiraz müdüre; EK-1 anlatı + tebliğ kurul başkanına.
  // (Tek kullanıcılı masaüstünde hepsi ALL_CAPABILITIES ile açık.)
  const canApprove = caps.isMudur || caps.isAdmin;
  const canManageAppeal = caps.isMudur || caps.isAdmin;
  const canEditNarrative = caps.isChair || caps.isAdmin;
  const canNotify = caps.isChair || caps.isAdmin;
  // Düzenle/sil yalnız BEKLEMEDEKİ kararda (Tur 152/153) — onaylı/tebliğli/itirazlı kilitli
  // (backend de korur); kararı giren başkan/ADMIN.
  const canEditDelete =
    (caps.isChair || caps.isAdmin) &&
    d.approval_status === "PENDING" &&
    !d.notified_at &&
    (d.appeals?.length ?? 0) === 0;

  return (
    <div className="rounded-shape-md border border-outline-variant bg-surface-container-low p-4">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="flex flex-wrap items-center gap-2 text-body-large text-on-surface">
            <Icon name="gavel" size="base" className="text-primary" />
            <span className="font-medium">{studentName}</span>
            <span className="text-on-surface-variant">· {d.penalty_type_display}</span>
          </p>
          <p className="mt-1 text-label-small text-on-surface-variant">
            {formatDate(d.decision_date)}
            {d.decision_no && ` · Karar no: ${d.decision_no}`}
            {d.penalty_type === "SHORT_TERM_SUSPENSION" &&
              d.suspension_days != null &&
              ` · ${d.suspension_days} gün`}
            {d.enforcement_start_date && ` · uygulama: ${formatDate(d.enforcement_start_date)}`}
            {d.statute_ref && ` · ${d.statute_ref}`}
          </p>
        </div>
        <span
          className={`inline-flex items-center rounded-shape-xl px-2.5 py-0.5 text-label-small ${APPROVAL_STATUS_CHIP[d.approval_status]}`}
        >
          {d.approval_status_display}
        </span>
      </div>

      {/* Künye satırı */}
      <div className="mt-3 flex flex-wrap gap-2 text-label-small text-on-surface-variant">
        <span className="inline-flex items-center gap-1 rounded-shape-xl bg-surface-container px-2.5 py-0.5">
          <Icon name="trending_down" size="xs" />−{d.behavior_point_deduction} puan
        </span>
        <span className="inline-flex items-center gap-1 rounded-shape-xl bg-surface-container px-2.5 py-0.5">
          <Icon name="approval" size="xs" />
          Onay mercii: {d.approval_authority_display}
        </span>
        {d.notified_at ? (
          <span className="inline-flex items-center gap-1 rounded-shape-xl bg-surface-container px-2.5 py-0.5">
            <Icon name="mark_email_read" size="xs" />
            Tebliğ: {formatDate(d.notified_at)}
            {d.appeal_deadline && ` · İtiraz son gün: ${formatDate(d.appeal_deadline)}`}
          </span>
        ) : (
          <span className="inline-flex items-center gap-1 rounded-shape-xl bg-tertiary-container px-2.5 py-0.5 text-on-tertiary-container">
            <Icon name="schedule" size="xs" />
            Henüz tebliğ edilmedi
          </span>
        )}
        {d.e_school_processed_on && (
          <span className="inline-flex items-center gap-1 rounded-shape-xl bg-success-container px-2.5 py-0.5 text-on-success-container">
            <Icon name="cloud_done" size="xs" />
            e-Okul: {formatDate(d.e_school_processed_on)}
          </span>
        )}
      </div>

      {/* e-Okul uyarısı (Tur 218, talep 8): kesinleşmemiş ceza e-Okul'a İŞLENMEZ —
          itirazla bozulan ceza sistemden silinemez; kesinleşme = itiraz süresinin
          dolması / itirazın sonuçlanması (md. 169/3-4, md. 171). */}
      {d.penalty_type !== "NO_PENALTY" &&
        !d.is_final &&
        (d.approval_status === "PENDING" || d.approval_status === "APPROVED") && (
          <div className="mt-2 flex items-start gap-2 rounded-shape-sm bg-error-container px-3 py-2 text-body-small text-on-error-container">
            <Icon name="warning" size="sm" className="mt-0.5" />
            <p>
              <span className="text-label-medium">Cezayı henüz e-Okul'a işlemeyin.</span> Karar
              kesinleşmeden (itiraz süresi dolmadan / itiraz sonuçlanmadan) e-Okul'a işlenen ceza,
              itirazla bozulursa silinemez (md. 169/3-4, md. 171).
            </p>
          </div>
        )}

      {d.penalty_type !== "NO_PENALTY" && d.is_final && !d.e_school_processed_on && (
        <div className="mt-2 flex items-start gap-2 rounded-shape-sm bg-tertiary-container px-3 py-2 text-body-small text-on-tertiary-container">
          <Icon name="cloud_upload" size="sm" className="mt-0.5" />
          <p>
            <span className="text-label-medium">Ceza kesinleşti.</span> Cezayı e-Okul'a işleyin ve
            ardından aşağıdaki işlemle kaydı onaylayın. Bu onay verilmeden dosya normal yolla
            kapatılamaz.
          </p>
        </div>
      )}

      {(d.approval_status === "RETURNED" || d.approval_status === "REFERRED") &&
        d.return_reason && (
          <div className="mt-2 rounded-shape-sm bg-tertiary-container px-3 py-2 text-body-small text-on-tertiary-container">
            <p className="text-label-small">
              {d.approval_status === "REFERRED" ? "İlçeye sevk gerekçesi" : "Kurula iade gerekçesi"}
              {d.returned_at && ` · ${formatDate(d.returned_at)}`} (md. 197)
            </p>
            <p className="mt-0.5 whitespace-pre-wrap">{d.return_reason}</p>
          </div>
        )}

      {d.penalty_detail && (
        <p className="mt-2 whitespace-pre-wrap text-body-medium text-on-surface-variant">
          {d.penalty_detail}
        </p>
      )}
      {d.notes && (
        <p className="mt-1 whitespace-pre-wrap text-body-small text-on-surface-variant">
          {d.notes}
        </p>
      )}

      {/* EK-1 anlatı özeti (varsa) */}
      {hasNarrative && (
        <details className="mt-3 rounded-shape-sm bg-surface-container px-3 py-2">
          <summary className="cursor-pointer text-label-large text-on-surface-variant">
            EK-1 anlatı alanları
          </summary>
          <div className="mt-2 space-y-2">
            {NARRATIVE_FIELDS.filter((f) => (d[f.key] || "").trim()).map((f) => (
              <div key={f.key}>
                <p className="text-label-small text-on-surface-variant">{f.label}</p>
                <p className="whitespace-pre-wrap text-body-small text-on-surface">{d[f.key]}</p>
              </div>
            ))}
          </div>
        </details>
      )}

      {/* Eylem çubuğu */}
      {panel === null &&
        (canApprove || canNotify || canEditNarrative || canManageAppeal || canEditDelete) && (
          <div className="mt-3 flex flex-wrap gap-1">
            {canApprove && d.approval_status !== "REJECTED" && d.approval_status !== "REFERRED" && (
              <Button variant="text" icon="approval" onClick={() => setPanel("approve")}>
                Onay durumu
              </Button>
            )}
            {canApprove &&
              (d.approval_status === "PENDING" || d.approval_status === "RETURNED") && (
                <Button variant="text" icon="undo" onClick={() => setPanel("return")}>
                  Kurula iade
                </Button>
              )}
            {canApprove && d.approval_status === "RETURNED" && (
              <Button variant="text" icon="forward" onClick={() => setPanel("refer")}>
                İlçe kuruluna gönder
              </Button>
            )}
            {canNotify && !d.notified_at && (
              <Button variant="text" icon="mark_email_read" onClick={() => setPanel("notify")}>
                Tebliğ kaydet
              </Button>
            )}
            {canManageAppeal &&
              d.penalty_type !== "NO_PENALTY" &&
              d.is_final &&
              !d.e_school_processed_on && (
                <Button variant="text" icon="cloud_done" onClick={() => setPanel("e-school")}>
                  e-Okul'a işlendi
                </Button>
              )}
            {canEditNarrative && (
              <Button variant="text" icon="edit_note" onClick={() => setPanel("narrative")}>
                EK-1 anlatı
              </Button>
            )}
            {canManageAppeal && d.notified_at && (
              <Button variant="text" icon="balance" onClick={() => setPanel("appeal")}>
                İtiraz ekle
              </Button>
            )}
            {canEditDelete && (
              <Button variant="text" icon="edit" onClick={() => setPanel("edit")}>
                Düzenle
              </Button>
            )}
            {canEditDelete && (
              <Button variant="text" icon="delete" onClick={() => onDelete(d)}>
                Sil
              </Button>
            )}
          </div>
        )}

      {panel === "approve" && (
        <ApprovalForm
          caseId={caseObj.id}
          decision={d}
          onCancel={() => setPanel(null)}
          onDone={() => {
            setPanel(null);
            onChanged();
          }}
        />
      )}
      {panel === "notify" && (
        <NotifyForm
          caseId={caseObj.id}
          decision={d}
          onCancel={() => setPanel(null)}
          onDone={() => {
            setPanel(null);
            onChanged();
          }}
        />
      )}
      {panel === "e-school" && (
        <ESchoolForm
          caseId={caseObj.id}
          decision={d}
          onCancel={() => setPanel(null)}
          onDone={() => {
            setPanel(null);
            onChanged();
          }}
        />
      )}
      {panel === "narrative" && (
        <NarrativeForm
          caseId={caseObj.id}
          caseClosed={caseObj.closed_at !== null}
          decision={d}
          studentName={studentName}
          onCancel={() => setPanel(null)}
          onDone={() => {
            setPanel(null);
            onChanged();
          }}
        />
      )}
      {panel === "appeal" && (
        <AddAppealForm
          caseId={caseObj.id}
          decision={d}
          onCancel={() => setPanel(null)}
          onDone={() => {
            setPanel(null);
            onChanged();
          }}
        />
      )}
      {panel === "edit" && (
        <EditDecisionForm
          caseObj={caseObj}
          decision={d}
          onCancel={() => setPanel(null)}
          onSaved={() => {
            setPanel(null);
            onChanged();
          }}
        />
      )}
      {(panel === "return" || panel === "refer") && (
        <ReviewForm
          caseId={caseObj.id}
          decision={d}
          mode={panel}
          onCancel={() => setPanel(null)}
          onDone={() => {
            setPanel(null);
            onChanged();
          }}
        />
      )}

      {/* İtirazlar */}
      <AppealsList
        caseId={caseObj.id}
        appeals={d.appeals}
        canManage={canManageAppeal}
        onChanged={onChanged}
      />
    </div>
  );
}

// ===========================================================================
// Yeni karar formu
// ===========================================================================

function AddDecisionForm({
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
  const [penaltyType, setPenaltyType] = useState<PenaltyType>("REPRIMAND");
  const [decisionDate, setDecisionDate] = useState(today);
  const [suspensionDays, setSuspensionDays] = useState("1");
  const [enforcementStart, setEnforcementStart] = useState("");
  const [statuteRef, setStatuteRef] = useState("");
  const [decisionNo, setDecisionNo] = useState("");
  const [penaltyDetail, setPenaltyDetail] = useState("");
  const [notes, setNotes] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const snackbar = useSnackbar();
  const fieldIdBase = useId();

  const isSuspension = penaltyType === "SHORT_TERM_SUSPENSION";

  const submit = async () => {
    setBusy(true);
    setError(null);
    try {
      if (!studentId) throw new Error("Bir öğrenci seçilmelidir.");
      const body: DecisionCreateBody = {
        student_id: Number(studentId),
        penalty_type: penaltyType,
        decision_date: decisionDate,
        statute_ref: statuteRef.trim(),
        decision_no: decisionNo.trim(),
        penalty_detail: penaltyDetail.trim(),
        notes: notes.trim(),
      };
      if (isSuspension) {
        body.suspension_days = Number(suspensionDays);
        body.enforcement_start_date = enforcementStart || null;
      }
      await disiplinApi.createDecision(caseObj.id, body);
      snackbar.success("Karar kaydedildi.");
      onAdded();
    } catch (err) {
      setError(asMessage(err, "Karar kaydedilemedi."));
      setBusy(false);
    }
  };

  return (
    <div className="space-y-4 rounded-shape-md bg-surface-container-low p-4">
      <p className="text-title-medium text-on-surface">Yeni resmî karar</p>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
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
        />
        <Select
          label="Ceza türü"
          value={penaltyType}
          onChange={(e) => setPenaltyType(e.target.value as PenaltyType)}
          options={(Object.entries(PENALTY_TYPE_TR) as [PenaltyType, string][]).map(
            ([value, label]) => ({ value, label }),
          )}
          helperText="Md. 163 — kanunla sabit; davranış puanı indirimi otomatik."
        />
      </div>

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <TextField
          label="Karar tarihi"
          type="date"
          required
          value={decisionDate}
          onChange={(e) => setDecisionDate(e.target.value)}
        />
        {isSuspension && (
          <TextField
            label="Uzaklaştırma günü (1-5)"
            type="number"
            min={1}
            max={5}
            required
            value={suspensionDays}
            onChange={(e) => setSuspensionDays(e.target.value)}
            helperText="Md. 163 — kısa süreli uzaklaştırma 1-5 gün."
          />
        )}
      </div>

      {isSuspension && (
        <TextField
          label="Uzaklaştırma uygulama başlangıcı (opsiyonel)"
          type="date"
          value={enforcementStart}
          onChange={(e) => setEnforcementStart(e.target.value)}
          helperText="Girilirse bitiş ve okula başlama tarihleri iş günü (tatil hariç) hesaplanır; ceza günleri tebliğinde (Form-16/17) dolu çıkar. Sonradan da girilebilir."
        />
      )}

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <TextField
          label="Karar no (boşsa otomatik verilir)"
          value={decisionNo}
          onChange={(e) => setDecisionNo(e.target.value)}
        />
        <TextField
          label="Mevzuat dayanağı (opsiyonel)"
          value={statuteRef}
          onChange={(e) => setStatuteRef(e.target.value)}
          placeholder="Örn. md. 164/1-c"
        />
      </div>

      <div>
        <label
          htmlFor={`${fieldIdBase}-detail`}
          className="mb-1 block text-label-large text-on-surface-variant"
        >
          Ceza ayrıntısı / gerekçe (opsiyonel)
        </label>
        <textarea
          id={`${fieldIdBase}-detail`}
          rows={2}
          value={penaltyDetail}
          onChange={(e) => setPenaltyDetail(e.target.value)}
          className="block w-full rounded-shape-xs border border-outline bg-surface px-4 py-3 text-body-medium text-on-surface outline-none focus-visible:ring-2 focus-visible:ring-primary focus:border-primary"
        />
      </div>
      <div>
        <label
          htmlFor={`${fieldIdBase}-notes`}
          className="mb-1 block text-label-large text-on-surface-variant"
        >
          Not (opsiyonel)
        </label>
        <textarea
          id={`${fieldIdBase}-notes`}
          rows={2}
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
          className="block w-full rounded-shape-xs border border-outline bg-surface px-4 py-3 text-body-medium text-on-surface outline-none focus-visible:ring-2 focus-visible:ring-primary focus:border-primary"
        />
      </div>

      <FormError error={error} />
      <div className="flex justify-end gap-2">
        <Button type="button" variant="text" onClick={onCancel}>
          Vazgeç
        </Button>
        <Button icon="check" onClick={submit} disabled={busy || !studentId}>
          {busy ? "Kaydediliyor…" : "Kararı kaydet"}
        </Button>
      </div>
    </div>
  );
}

// Beklemedeki kararı düzenle (çekirdek alanlar; yalnız PENDING — backend korur). Tur 153, Faz 4b.
// Öğrenci/olay/toplantı bağı değişmez; ceza türü değişince davranış puanı + onay mercii backend'de
// yeniden türetilir.
function EditDecisionForm({
  caseObj,
  decision: d,
  onCancel,
  onSaved,
}: {
  caseObj: DisciplineCase;
  decision: DisciplineDecision;
  onCancel: () => void;
  onSaved: () => void;
}) {
  const [penaltyType, setPenaltyType] = useState<PenaltyType>(d.penalty_type);
  const [decisionDate, setDecisionDate] = useState(d.decision_date);
  const [suspensionDays, setSuspensionDays] = useState(String(d.suspension_days ?? 1));
  const [enforcementStart, setEnforcementStart] = useState(d.enforcement_start_date ?? "");
  const [statuteRef, setStatuteRef] = useState(d.statute_ref);
  const [decisionNo, setDecisionNo] = useState(d.decision_no);
  const [penaltyDetail, setPenaltyDetail] = useState(d.penalty_detail);
  const [notes, setNotes] = useState(d.notes);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const snackbar = useSnackbar();
  const fieldIdBase = useId();

  const isSuspension = penaltyType === "SHORT_TERM_SUSPENSION";

  const submit = async () => {
    setBusy(true);
    setError(null);
    try {
      const body: DecisionEditBody = {
        penalty_type: penaltyType,
        decision_date: decisionDate,
        statute_ref: statuteRef.trim(),
        decision_no: decisionNo.trim(),
        penalty_detail: penaltyDetail.trim(),
        notes: notes.trim(),
      };
      if (isSuspension) {
        body.suspension_days = Number(suspensionDays);
        body.enforcement_start_date = enforcementStart || null;
      }
      await disiplinApi.updateDecision(caseObj.id, d.id, body);
      snackbar.success("Karar güncellendi.");
      onSaved();
    } catch (err) {
      setError(asMessage(err, "Karar düzenlenemedi."));
      setBusy(false);
    }
  };

  return (
    <div className="space-y-4 rounded-shape-md bg-surface-container-low p-4">
      <p className="text-title-medium text-on-surface">Kararı düzenle (beklemede)</p>
      <p className="text-body-small text-on-surface-variant">
        Ceza türü değişince davranış puanı indirimi ve onay mercii yeniden hesaplanır. Karar
        onaylanınca/tebliğ edilince düzenlenemez (düzeltme kurula iade / itiraz iledir).
      </p>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <Select
          label="Ceza türü"
          value={penaltyType}
          onChange={(e) => setPenaltyType(e.target.value as PenaltyType)}
          options={(Object.entries(PENALTY_TYPE_TR) as [PenaltyType, string][]).map(
            ([value, label]) => ({ value, label }),
          )}
          helperText="Md. 163 — kanunla sabit; davranış puanı indirimi otomatik."
        />
        <TextField
          label="Karar tarihi"
          type="date"
          required
          value={decisionDate}
          onChange={(e) => setDecisionDate(e.target.value)}
        />
      </div>

      {isSuspension && (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <TextField
            label="Uzaklaştırma günü (1-5)"
            type="number"
            min={1}
            max={5}
            required
            value={suspensionDays}
            onChange={(e) => setSuspensionDays(e.target.value)}
            helperText="Md. 163 — kısa süreli uzaklaştırma 1-5 gün."
          />
          <TextField
            label="Uzaklaştırma uygulama başlangıcı (opsiyonel)"
            type="date"
            value={enforcementStart}
            onChange={(e) => setEnforcementStart(e.target.value)}
            helperText="Girilirse bitiş/okula başlama iş günü (tatil hariç) hesaplanır."
          />
        </div>
      )}

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <TextField
          label="Karar no"
          value={decisionNo}
          onChange={(e) => setDecisionNo(e.target.value)}
        />
        <TextField
          label="Mevzuat dayanağı (opsiyonel)"
          value={statuteRef}
          onChange={(e) => setStatuteRef(e.target.value)}
          placeholder="Örn. md. 164/1-c"
        />
      </div>

      <div>
        <label
          htmlFor={`${fieldIdBase}-detail`}
          className="mb-1 block text-label-large text-on-surface-variant"
        >
          Ceza ayrıntısı / gerekçe (opsiyonel)
        </label>
        <textarea
          id={`${fieldIdBase}-detail`}
          rows={2}
          value={penaltyDetail}
          onChange={(e) => setPenaltyDetail(e.target.value)}
          className="block w-full rounded-shape-xs border border-outline bg-surface px-4 py-3 text-body-medium text-on-surface outline-none focus-visible:ring-2 focus-visible:ring-primary focus:border-primary"
        />
      </div>
      <div>
        <label
          htmlFor={`${fieldIdBase}-notes`}
          className="mb-1 block text-label-large text-on-surface-variant"
        >
          Not (opsiyonel)
        </label>
        <textarea
          id={`${fieldIdBase}-notes`}
          rows={2}
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
          className="block w-full rounded-shape-xs border border-outline bg-surface px-4 py-3 text-body-medium text-on-surface outline-none focus-visible:ring-2 focus-visible:ring-primary focus:border-primary"
        />
      </div>

      <FormError error={error} />
      <div className="flex justify-end gap-2">
        <Button type="button" variant="text" onClick={onCancel}>
          Vazgeç
        </Button>
        <Button icon="check" onClick={submit} disabled={busy}>
          {busy ? "Kaydediliyor…" : "Değişiklikleri kaydet"}
        </Button>
      </div>
    </div>
  );
}

// ===========================================================================
// Onay / tebliğ / anlatı formları
// ===========================================================================

function ApprovalForm({
  caseId,
  decision: d,
  onCancel,
  onDone,
}: {
  caseId: number;
  decision: DisciplineDecision;
  onCancel: () => void;
  onDone: () => void;
}) {
  const today = todayIso();
  // Liste yalnız PENDING/APPROVED içerir; RETURNED/REFERRED/REJECTED bir karşılığı
  // olmadığından state listede GERÇEKTEN bulunan değere ilklenir — aksi halde
  // tarayıcı ilk seçeneği gösterirken state farklı kalır ve dokunulmadan yapılan
  // kayıt backend'de reddedilirdi (md. 197).
  const [status, setStatus] = useState<DecisionApprovalStatus>(
    d.approval_status === "APPROVED" ? "APPROVED" : "PENDING",
  );
  const [approvedOn, setApprovedOn] = useState(d.approved_at ?? today);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const snackbar = useSnackbar();

  const submit = async () => {
    setBusy(true);
    setError(null);
    try {
      await disiplinApi.approveDecision(caseId, d.id, {
        approval_status: status,
        approved_on: status === "PENDING" ? null : approvedOn,
      });
      snackbar.success("Onay durumu güncellendi.");
      onDone();
    } catch (err) {
      setError(asMessage(err, "Onay durumu güncellenemedi."));
      setBusy(false);
    }
  };

  return (
    <PanelShell title="Onay durumu" icon="approval">
      <Select
        label="Onay durumu"
        value={status}
        onChange={(e) => setStatus(e.target.value as DecisionApprovalStatus)}
        options={(Object.entries(DECISION_APPROVAL_STATUS_TR) as [DecisionApprovalStatus, string][])
          .filter(([value]) => value === "PENDING" || value === "APPROVED")
          .map(([value, label]) => ({ value, label }))}
        helperText="Müdür onaylar (kınama/kısa süreli uzaklaştırma) ya da yetki dışı cezada üst mercie gönderir. Müdürün kararı reddetme yetkisi yoktur; uygun bulmazsa gerekçeyle kurula iade eder (md. 197)."
      />
      {status !== "PENDING" && (
        <TextField
          label="Onay tarihi"
          type="date"
          value={approvedOn}
          onChange={(e) => setApprovedOn(e.target.value)}
        />
      )}
      <FormError error={error} />
      <PanelActions busy={busy} onCancel={onCancel} onSubmit={submit} />
    </PanelShell>
  );
}

// md. 197 — kurula iade (RETURN) / ilçe kuruluna gönderme (REFER). Müdür kararı
// reddedemez; uygun bulmazsa gerekçeyle kurula iade eder, kurul ısrar ederse ilçeye sevk.
function ReviewForm({
  caseId,
  decision: d,
  mode,
  onCancel,
  onDone,
}: {
  caseId: number;
  decision: DisciplineDecision;
  mode: "return" | "refer";
  onCancel: () => void;
  onDone: () => void;
}) {
  const today = todayIso();
  const isRefer = mode === "refer";
  const fieldIdBase = useId();
  const [reason, setReason] = useState("");
  const [decidedOn, setDecidedOn] = useState(today);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const snackbar = useSnackbar();

  const submit = async () => {
    setBusy(true);
    setError(null);
    try {
      if (!reason.trim()) throw new Error("Gerekçe zorunludur (md. 197).");
      await disiplinApi.reviewDecision(caseId, d.id, {
        action: isRefer ? "REFER" : "RETURN",
        reason: reason.trim(),
        decided_on: decidedOn,
      });
      snackbar.success("İşlem kaydedildi.");
      onDone();
    } catch (err) {
      setError(asMessage(err, "İşlem kaydedilemedi."));
      setBusy(false);
    }
  };

  return (
    <PanelShell
      title={isRefer ? "İlçe kuruluna gönder (md. 197)" : "Kurula iade (md. 197)"}
      icon={isRefer ? "forward" : "undo"}
    >
      <p className="text-body-small text-on-surface-variant">
        {isRefer
          ? "Kurul kararında ısrar etti. Müdür görüş ve tekliflerini ekleyerek dosyayı en geç 5 iş günü içinde ilçe öğrenci disiplin kuruluna gönderir (md. 197)."
          : "Müdür kararı uygun bulmazsa gerekçesiyle bir defa daha görüşülmek üzere kurula iade eder (md. 197)."}
      </p>
      <div>
        <label
          htmlFor={fieldIdBase}
          className="mb-1 block text-label-large text-on-surface-variant"
        >
          Gerekçe <span className="text-error">*</span>
        </label>
        <textarea
          id={fieldIdBase}
          required
          rows={3}
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          className="block w-full rounded-shape-xs border border-outline bg-surface px-4 py-3 text-body-medium text-on-surface outline-none focus-visible:ring-2 focus-visible:ring-primary focus:border-primary"
        />
      </div>
      <TextField
        label={isRefer ? "Gönderme tarihi" : "İade tarihi"}
        type="date"
        required
        value={decidedOn}
        onChange={(e) => setDecidedOn(e.target.value)}
      />
      <FormError error={error} />
      <PanelActions
        busy={busy}
        onCancel={onCancel}
        onSubmit={submit}
        submitLabel={isRefer ? "İlçeye gönder" : "Kurula iade et"}
      />
    </PanelShell>
  );
}

function NotifyForm({
  caseId,
  decision: d,
  onCancel,
  onDone,
}: {
  caseId: number;
  decision: DisciplineDecision;
  onCancel: () => void;
  onDone: () => void;
}) {
  const today = todayIso();
  const [notifiedOn, setNotifiedOn] = useState(today);
  const [method, setMethod] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const snackbar = useSnackbar();

  const submit = async () => {
    setBusy(true);
    setError(null);
    try {
      await disiplinApi.notifyDecision(caseId, d.id, {
        notified_on: notifiedOn,
        notification_method: method.trim(),
      });
      snackbar.success("Tebliğ kaydedildi.");
      onDone();
    } catch (err) {
      setError(asMessage(err, "Tebliğ kaydedilemedi."));
      setBusy(false);
    }
  };

  return (
    <PanelShell title="Tebliğ kaydet" icon="mark_email_read">
      <p className="text-body-small text-on-surface-variant">
        Tebliğ (md. 169/5) tarihinden itibaren itiraz son günü otomatik hesaplanır (md. 169/3).
      </p>
      <TextField
        label="Tebliğ tarihi"
        type="date"
        required
        value={notifiedOn}
        onChange={(e) => setNotifiedOn(e.target.value)}
      />
      <TextField
        label="Tebliğ yöntemi (opsiyonel)"
        value={method}
        onChange={(e) => setMethod(e.target.value)}
        placeholder="Örn. elden, iadeli taahhütlü"
      />
      <FormError error={error} />
      <PanelActions busy={busy} onCancel={onCancel} onSubmit={submit} />
    </PanelShell>
  );
}

function ESchoolForm({
  caseId,
  decision: d,
  onCancel,
  onDone,
}: {
  caseId: number;
  decision: DisciplineDecision;
  onCancel: () => void;
  onDone: () => void;
}) {
  const [processedOn, setProcessedOn] = useState(todayIso());
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const snackbar = useSnackbar();

  const submit = async () => {
    setBusy(true);
    setError(null);
    try {
      await disiplinApi.confirmESchoolEntry(caseId, d.id, { processed_on: processedOn });
      snackbar.success("Ceza e-Okul'a işlendi olarak kaydedildi.");
      onDone();
    } catch (err) {
      setError(asMessage(err, "e-Okul kaydı onaylanamadı."));
      setBusy(false);
    }
  };

  return (
    <PanelShell title="e-Okul kaydını onayla" icon="cloud_done">
      <div className="rounded-shape-sm bg-tertiary-container px-4 py-3 text-body-small text-on-tertiary-container">
        Bu işlem, <strong>{d.penalty_type_display}</strong> cezasının e-Okul sistemine gerçekten
        işlendiğini beyan eder. Onaydan önce e-Okul kaydını kontrol edin.
      </div>
      <TextField
        label="e-Okul'a işlenme tarihi"
        type="date"
        required
        value={processedOn}
        onChange={(e) => setProcessedOn(e.target.value)}
      />
      <FormError error={error} />
      <PanelActions busy={busy} onCancel={onCancel} onSubmit={submit} />
    </PanelShell>
  );
}

// Oto-kayıt durum göstergesi (Tur 147). aria-live bölgesi HER ZAMAN DOM'da (idle'da
// boş) — ekran okuyucunun durum değişimlerini duyurabilmesi için sabit konteyner
// gerek; sonradan eklenen live region izlenmez (WCAG AA, CLAUDE.md §7.5).
function AutosaveStatusLine({
  status,
  lastSavedAt,
  onRetry,
}: {
  status: AutosaveStatus;
  lastSavedAt: Date | null;
  onRetry: () => void;
}) {
  const view =
    status === "saving"
      ? { icon: "cloud_sync", text: "Kaydediliyor…" }
      : status === "pending"
        ? { icon: "edit", text: "Kaydedilmemiş değişiklik" }
        : {
            icon: "cloud_done",
            text: lastSavedAt
              ? `Kaydedildi ${lastSavedAt.toLocaleTimeString("tr-TR", {
                  hour: "2-digit",
                  minute: "2-digit",
                })}`
              : "Kaydedildi",
          };
  return (
    <div aria-live="polite" aria-atomic="true">
      {status === "idle" ? null : status === "error" ? (
        <div className="flex flex-wrap items-center gap-2 text-label-medium text-error">
          <span className="flex items-center gap-1.5">
            <Icon name="cloud_off" size="sm" />
            Kaydedilemedi
          </span>
          <Button type="button" variant="text" icon="refresh" onClick={onRetry}>
            Tekrar dene
          </Button>
        </div>
      ) : (
        <p className="flex items-center gap-1.5 text-label-medium text-on-surface-variant">
          <Icon name={view.icon} size="sm" />
          {view.text}
        </p>
      )}
    </div>
  );
}

function NarrativeForm({
  caseId,
  caseClosed,
  decision: d,
  studentName,
  onCancel,
  onDone,
}: {
  caseId: number;
  caseClosed: boolean;
  decision: DisciplineDecision;
  studentName: string;
  onCancel: () => void;
  onDone: () => void;
}) {
  const initValues = () =>
    Object.fromEntries(
      [...NARRATIVE_FIELDS, ...EK1_CONTEXT_FIELDS].map((f) => [f.key, d[f.key]]),
    ) as unknown as DecisionNarrative;
  const [values, setValues] = useState<DecisionNarrative>(initValues);
  const [enforcementStart, setEnforcementStart] = useState(d.enforcement_start_date ?? "");
  const [incidentDate, setIncidentDate] = useState(d.incident_date ?? "");
  // Doğum tarihi (Tur 220, talep 1): sicilden prefill; girilirse SİCİLE yazılır.
  const [birthDate, setBirthDate] = useState(d.student_birth_date ?? "");
  const isSuspension = d.penalty_type === "SHORT_TERM_SUSPENSION";
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const snackbar = useSnackbar();
  const confirm = useConfirm();
  // Form-örneğine özgü id tabanı — textarea ↔ label programatik bağı (htmlFor/id; C13).
  // Aynı anda birden çok karar kartı açıksa id'ler çakışmasın diye useId tabanı.
  const fieldIdBase = useId();

  // Sunucu-taraflı oto-kayıt (localStorage YOK — EK-1 hassas veri).
  // Hibrit: alanlar yazıldıkça arka planda kaydedilir; "Anlatıyı kaydet" butonu da kalır.
  // Dosya kapalıyken backend her yazmayı reddeder → oto-kayıt da susturulur.
  const autosave = useAutosave<DecisionNarrativeBody>({
    save: (changed) => disiplinApi.updateDecisionNarrative(caseId, d.id, changed),
    enabled: !caseClosed,
  });

  const submit = async () => {
    setBusy(true);
    setError(null);
    try {
      const body: DecisionNarrativeBody = { ...values, incident_date: incidentDate || null };
      if (isSuspension) body.enforcement_start_date = enforcementStart || null;
      // Doğum tarihi yalnız oto-kayıt debounce'una bağlı değildir: kullanıcı tarihi
      // girip beklemeden kaydederse markSaved() bekleyeni siler ve veri hiç gitmezdi.
      // Değişmişse gövdeye açıkça konur (kaydetme akışı tek doğruluk kaynağı).
      if (birthDate !== (d.student_birth_date ?? "")) body.student_birth_date = birthDate || null;
      await disiplinApi.updateDecisionNarrative(caseId, d.id, body);
      autosave.markSaved();
      snackbar.success("Anlatı kaydedildi.");
      onDone();
    } catch (err) {
      setError(asMessage(err, "Anlatı kaydedilemedi."));
      setBusy(false);
    }
  };

  // Bir anlatı alanını yaz + auto-save'e bildir (Faz A) — textarea ve SelectOrOther ortak.
  const updateField = (key: keyof DecisionNarrative, value: string) => {
    setValues((prev) => ({ ...prev, [key]: value }));
    const patch: Partial<DecisionNarrativeBody> = {};
    (patch as Record<string, string>)[key] = value;
    autosave.notifyChange(patch);
  };

  // Şablon bağlamı — varyant build()'leri kayıtlı veriyle ön-doldurur (Tur 149→219).
  const templateCtx = {
    studentName,
    penaltyLabel: d.penalty_type_display,
    statuteRef: d.statute_ref ?? "",
    incidentDate,
  };

  // Çok-varyantlı alanlarda "Şablon seç" diyaloğunun açık olduğu alan (Tur 219).
  const [templatePickerFor, setTemplatePickerFor] = useState<keyof DecisionNarrative | null>(null);

  // Seçilen şablonu alana basar; alan doluysa üzerine yazmadan önce onay ister
  // (Faz C davranışı korunur). Sonuç updateField ile auto-save'e de düşer.
  const applyTemplate = async (key: keyof DecisionNarrative, tpl: NarrativeTemplate) => {
    const text = tpl.build(templateCtx);
    if (
      values[key]?.trim() &&
      !(await confirm({
        message: "Bu alanda zaten metin var. Şablonla değiştirilsin mi?",
        confirmLabel: "Değiştir",
      }))
    ) {
      return;
    }
    updateField(key, text);
  };

  // Düğme davranışı: tek varyant → doğrudan uygula (eski davranış); çok varyant →
  // önce seçim diyaloğu (Dialog kapanır, doluysa-onay ondan SONRA açılır — odak sırası).
  const onTemplateButton = (key: keyof DecisionNarrative) => {
    const templates = NARRATIVE_TEMPLATES[key] ?? [];
    if (templates.length === 1) {
      void applyTemplate(key, templates[0]);
    } else if (templates.length > 1) {
      setTemplatePickerFor(key);
    }
  };

  const renderField = (f: {
    key: keyof DecisionNarrative;
    label: string;
    rows?: number;
    options?: string[];
  }) => {
    // Sabit seçenekli alanlar "Seçim + Diğer" (Faz B); diğerleri serbest metin.
    if (f.options) {
      return (
        <SelectOrOther
          key={f.key}
          label={f.label}
          value={values[f.key]}
          options={f.options}
          onChange={(value) => updateField(f.key, value)}
        />
      );
    }
    const fieldId = `${fieldIdBase}-${f.key}`;
    return (
      <div key={f.key}>
        <div className="mb-1 flex items-center justify-between gap-2">
          <label htmlFor={fieldId} className="block text-label-large text-on-surface-variant">
            {f.label}
          </label>
          {(NARRATIVE_TEMPLATES[f.key]?.length ?? 0) > 0 && (
            <Button
              type="button"
              variant="text"
              icon="auto_awesome"
              onClick={() => onTemplateButton(f.key)}
            >
              Şablon ekle
            </Button>
          )}
        </div>
        <textarea
          id={fieldId}
          rows={f.rows ?? 3}
          value={values[f.key]}
          onChange={(e) => updateField(f.key, e.target.value)}
          className="block w-full rounded-shape-xs border border-outline bg-surface px-4 py-3 text-body-medium text-on-surface outline-none focus-visible:ring-2 focus-visible:ring-primary focus:border-primary"
        />
      </div>
    );
  };

  return (
    <PanelShell title="EK-1 anlatı + öğrenci bağlamı" icon="edit_note">
      {caseClosed ? (
        <div className="flex items-start gap-2 rounded-shape-sm bg-tertiary-container px-4 py-2 text-body-small text-on-tertiary-container">
          <Icon name="lock" size="sm" />
          <span>
            Dosya kapalı; anlatı düzenlenemez. Alanlar yalnız görüntülenir. Düzeltme gerekiyorsa
            önce dosya yeniden açılmalıdır.
          </span>
        </div>
      ) : (
        <p className="text-body-small text-on-surface-variant">
          Yazdıkça otomatik kaydedilir; EK-1 belgesine işlenir, dosya kapanana kadar düzenlenebilir.
          Boş bırakılan alanlar belgede boş görünür.
        </p>
      )}
      {/* `fieldset disabled` tüm iç alanları (SelectOrOther dahil) tek noktadan
          salt-okunur yapar — alt bileşenlere disabled prop'u eklemeye gerek yok. */}
      <fieldset disabled={caseClosed} className="min-w-0 space-y-3">
        <p className="text-label-large text-on-surface">Olayla ilgili anlatı (md. 168 / 193)</p>
        {NARRATIVE_FIELDS.map(renderField)}
        <p className="mt-2 text-label-large text-on-surface">EK-1 öğrenci bağlamı (md. 168)</p>
        <TextField
          label="Doğum tarihi"
          type="date"
          value={birthDate}
          onChange={(e) => {
            const value = e.target.value;
            setBirthDate(value);
            // Boş bırakılırsa null gider; backend sicile DOKUNMAZ (silme yok).
            autosave.notifyChange({ student_birth_date: value || null });
          }}
          helperText="Öğrenci SİCİLİNE kaydedilir (EK-1 ve diğer tüm belgelerde kullanılır); e-Okul ihracı bu alanı doldurmadığından boş kalmış olabilir."
        />
        {EK1_CONTEXT_FIELDS.map(renderField)}
        <TextField
          label="Davranışın yapıldığı tarih"
          type="date"
          value={incidentDate}
          onChange={(e) => {
            const value = e.target.value;
            setIncidentDate(value);
            autosave.notifyChange({ incident_date: value || null });
          }}
          helperText="EK-1: cezayı gerektiren davranışın yapıldığı tarih."
        />
        {isSuspension && (
          <TextField
            label="Uzaklaştırma uygulama başlangıcı"
            type="date"
            value={enforcementStart}
            onChange={(e) => {
              const value = e.target.value;
              setEnforcementStart(value);
              autosave.notifyChange({ enforcement_start_date: value || null });
            }}
            helperText="Md. 164/2 — girilirse bitiş/okula başlama iş günü (tatil hariç) hesaplanır; ceza günleri tebliğinde (Form-16/17) dolu çıkar."
          />
        )}
      </fieldset>
      <FormError error={error} />
      {caseClosed ? (
        <div className="flex justify-end">
          <Button type="button" variant="text" onClick={onCancel}>
            Kapat
          </Button>
        </div>
      ) : (
        <div className="flex flex-wrap items-center justify-between gap-2">
          <AutosaveStatusLine
            status={autosave.status}
            lastSavedAt={autosave.lastSavedAt}
            onRetry={autosave.retry}
          />
          <div className="ml-auto">
            <PanelActions
              busy={busy}
              onCancel={() => void autosave.flush().then(onCancel)}
              onSubmit={submit}
              submitLabel="Anlatıyı kaydet"
              cancelLabel="Kapat"
            />
          </div>
        </div>
      )}

      {/* Çok-varyantlı şablon seçimi (Tur 219): her satır 48px buton + tek satır önizleme.
          Seçim → diyalog kapanır → doluysa-onay (useConfirm) ondan sonra açılır. */}
      <Dialog
        open={templatePickerFor !== null}
        onClose={() => setTemplatePickerFor(null)}
        title="Şablon seç"
      >
        <div className="space-y-1">
          {(templatePickerFor ? (NARRATIVE_TEMPLATES[templatePickerFor] ?? []) : []).map((tpl) => (
            <button
              key={tpl.id}
              type="button"
              onClick={() => {
                const key = templatePickerFor;
                setTemplatePickerFor(null);
                if (key) void applyTemplate(key, tpl);
              }}
              className="block min-h-12 w-full rounded-shape-sm px-4 py-2.5 text-left outline-none hover:bg-on-surface/8 focus-visible:bg-on-surface/12 focus-visible:ring-2 focus-visible:ring-primary"
            >
              <span className="block text-body-large text-on-surface">{tpl.label}</span>
              <span className="block truncate text-body-small text-on-surface-variant">
                {tpl.build(templateCtx)}
              </span>
            </button>
          ))}
        </div>
      </Dialog>
    </PanelShell>
  );
}

// ===========================================================================
// İtirazlar
// ===========================================================================

function AppealsList({
  caseId,
  appeals,
  canManage,
  onChanged,
}: {
  caseId: number;
  appeals: DisciplineAppeal[];
  canManage: boolean;
  onChanged: () => void;
}) {
  if (appeals.length === 0) return null;
  return (
    <div className="mt-4 border-t border-outline-variant/50 pt-3">
      <p className="text-label-large text-on-surface-variant">İtirazlar ({appeals.length})</p>
      <ul className="mt-2 space-y-2">
        {appeals.map((a) => (
          <AppealRow
            key={a.id}
            caseId={caseId}
            appeal={a}
            canManage={canManage}
            onChanged={onChanged}
          />
        ))}
      </ul>
    </div>
  );
}

function AppealRow({
  caseId,
  appeal: a,
  canManage,
  onChanged,
}: {
  caseId: number;
  appeal: DisciplineAppeal;
  canManage: boolean;
  onChanged: () => void;
}) {
  const [panel, setPanel] = useState<"forward" | "resolve" | null>(null);
  const resolved = a.result !== "PENDING";

  return (
    <li className="rounded-shape-sm bg-surface-container px-3 py-2">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-body-medium text-on-surface">
          <Icon name="balance" size="sm" className="mr-1 align-middle text-primary" />
          {/* Sapma: `filed_by_role_display` alanı standalone serializer'da yok — TR sözlüğü. */}
          {APPEAL_FILED_BY_ROLE_TR[a.filed_by_role]}
          {a.filed_by_name && ` · ${a.filed_by_name}`}
        </p>
        <span
          className={`inline-flex items-center rounded-shape-xl px-2.5 py-0.5 text-label-small ${APPEAL_RESULT_CHIP[a.result]}`}
        >
          {a.result_display}
        </span>
      </div>
      <p className="mt-1 text-label-small text-on-surface-variant">
        Başvuru: {formatDate(a.filed_on)}
        {!a.within_deadline && " · süre dışında"}
        {" · İtiraz mercii: "}
        {a.appeal_authority_display}
        {a.forwarded_on
          ? ` · sevk: ${formatDate(a.forwarded_on)}`
          : a.forward_deadline
            ? ` · sevk son gün: ${formatDate(a.forward_deadline)}`
            : ""}
        {a.resulted_on && ` · sonuç: ${formatDate(a.resulted_on)}`}
      </p>
      {a.result_notes && (
        <p className="mt-1 whitespace-pre-wrap text-body-small text-on-surface-variant">
          {a.result_notes}
        </p>
      )}

      {canManage && panel === null && !resolved && (
        <div className="mt-2 flex flex-wrap gap-1">
          {!a.forwarded_on && (
            <Button variant="text" icon="send" onClick={() => setPanel("forward")}>
              Üst kurula sevk
            </Button>
          )}
          <Button variant="text" icon="task_alt" onClick={() => setPanel("resolve")}>
            Sonucu kaydet
          </Button>
        </div>
      )}

      {panel === "forward" && (
        <ForwardAppealForm
          caseId={caseId}
          appeal={a}
          onCancel={() => setPanel(null)}
          onDone={() => {
            setPanel(null);
            onChanged();
          }}
        />
      )}
      {panel === "resolve" && (
        <ResolveAppealForm
          caseId={caseId}
          appeal={a}
          onCancel={() => setPanel(null)}
          onDone={() => {
            setPanel(null);
            onChanged();
          }}
        />
      )}
    </li>
  );
}

function AddAppealForm({
  caseId,
  decision: d,
  onCancel,
  onDone,
}: {
  caseId: number;
  decision: DisciplineDecision;
  onCancel: () => void;
  onDone: () => void;
}) {
  const today = todayIso();
  const [filedOn, setFiledOn] = useState(today);
  const [role, setRole] = useState<AppealFiledByRole>("PARENT");
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const snackbar = useSnackbar();

  const submit = async () => {
    setBusy(true);
    setError(null);
    try {
      await disiplinApi.fileAppeal(caseId, d.id, {
        filed_on: filedOn,
        filed_by_role: role,
        filed_by_name: name.trim(),
      });
      snackbar.success("İtiraz kaydedildi.");
      onDone();
    } catch (err) {
      setError(asMessage(err, "İtiraz kaydedilemedi."));
      setBusy(false);
    }
  };

  return (
    <PanelShell title="İtiraz ekle" icon="balance">
      <p className="text-body-small text-on-surface-variant">
        İtiraz tebliğden itibaren 5 iş günü içinde yapılır (md. 169/3); süre dışında olsa da
        kaydedilir, sistem işaretler.
      </p>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <TextField
          label="Başvuru tarihi"
          type="date"
          required
          value={filedOn}
          onChange={(e) => setFiledOn(e.target.value)}
        />
        <Select
          label="İtiraz eden"
          value={role}
          onChange={(e) => setRole(e.target.value as AppealFiledByRole)}
          options={(Object.entries(APPEAL_FILED_BY_ROLE_TR) as [AppealFiledByRole, string][]).map(
            ([value, label]) => ({ value, label }),
          )}
        />
      </div>
      <TextField
        label="İtiraz eden ad (opsiyonel)"
        value={name}
        onChange={(e) => setName(e.target.value)}
      />
      <FormError error={error} />
      <PanelActions
        busy={busy}
        onCancel={onCancel}
        onSubmit={submit}
        submitLabel="İtirazı kaydet"
      />
    </PanelShell>
  );
}

function ForwardAppealForm({
  caseId,
  appeal: a,
  onCancel,
  onDone,
}: {
  caseId: number;
  appeal: DisciplineAppeal;
  onCancel: () => void;
  onDone: () => void;
}) {
  const today = todayIso();
  const [forwardedOn, setForwardedOn] = useState(today);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const snackbar = useSnackbar();

  const submit = async () => {
    setBusy(true);
    setError(null);
    try {
      await disiplinApi.forwardAppeal(caseId, a.id, { forwarded_on: forwardedOn });
      snackbar.success("Sevk kaydedildi.");
      onDone();
    } catch (err) {
      setError(asMessage(err, "Sevk kaydedilemedi."));
      setBusy(false);
    }
  };

  return (
    <PanelShell title="Üst kurula sevk" icon="send">
      <p className="text-body-small text-on-surface-variant">
        İtiraz {a.appeal_authority_display} merciine sevk edilir (md. 169/3 — en geç 5 iş günü).
      </p>
      <TextField
        label="Sevk tarihi"
        type="date"
        required
        value={forwardedOn}
        onChange={(e) => setForwardedOn(e.target.value)}
      />
      <FormError error={error} />
      <PanelActions busy={busy} onCancel={onCancel} onSubmit={submit} submitLabel="Sevki kaydet" />
    </PanelShell>
  );
}

function ResolveAppealForm({
  caseId,
  appeal: a,
  onCancel,
  onDone,
}: {
  caseId: number;
  appeal: DisciplineAppeal;
  onCancel: () => void;
  onDone: () => void;
}) {
  const today = todayIso();
  const [result, setResult] = useState<AppealResult>("UPHELD");
  const [resultedOn, setResultedOn] = useState(today);
  const [notes, setNotes] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const snackbar = useSnackbar();
  const fieldIdBase = useId();

  // İnceleniyor (PENDING) bir sonuç değildir; seçilemez.
  const resultOptions = (Object.entries(APPEAL_RESULT_TR) as [AppealResult, string][]).filter(
    ([value]) => value !== "PENDING",
  );

  const submit = async () => {
    setBusy(true);
    setError(null);
    try {
      await disiplinApi.resolveAppeal(caseId, a.id, {
        result,
        resulted_on: resultedOn,
        result_notes: notes.trim(),
      });
      snackbar.success("Sonuç kaydedildi.");
      onDone();
    } catch (err) {
      setError(asMessage(err, "Sonuç kaydedilemedi."));
      setBusy(false);
    }
  };

  return (
    <PanelShell title="İtiraz sonucu" icon="task_alt">
      <p className="text-body-small text-on-surface-variant">
        Sonuç kesindir; yeniden itiraz edilemez (md. 169/4). "Bozuldu" → ceza kaldırılır, davranış
        puanı iade edilir (md. 171).
      </p>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <Select
          label="Sonuç"
          value={result}
          onChange={(e) => setResult(e.target.value as AppealResult)}
          options={resultOptions.map(([value, label]) => ({ value, label }))}
        />
        <TextField
          label="Sonuç tarihi"
          type="date"
          required
          value={resultedOn}
          onChange={(e) => setResultedOn(e.target.value)}
        />
      </div>
      <div>
        <label
          htmlFor={fieldIdBase}
          className="mb-1 block text-label-large text-on-surface-variant"
        >
          Sonuç notu (opsiyonel)
        </label>
        <textarea
          id={fieldIdBase}
          rows={2}
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
          className="block w-full rounded-shape-xs border border-outline bg-surface px-4 py-3 text-body-medium text-on-surface outline-none focus-visible:ring-2 focus-visible:ring-primary focus:border-primary"
        />
      </div>
      <FormError error={error} />
      <PanelActions busy={busy} onCancel={onCancel} onSubmit={submit} submitLabel="Sonucu kaydet" />
    </PanelShell>
  );
}
