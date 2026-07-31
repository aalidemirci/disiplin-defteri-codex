// OYS frontend/src/modules/disiplin/DocumentsSection.tsx'ten UYARLANDI (F4-D2).
// Sapmalar: CaseStudent.student_id → id; GeneratedDocument'ta generated_by_name yok
// ("üreten" etiketi kalktı); rol/yetki katmanı yok — canManage prop'u korunur, üst
// bileşen ALL_CAPABILITIES gereği daima true geçirir. Gerisi AYNEN.
//
// Disiplin evrak üretimi (WeasyPrint PDF indirme) + evrak kütüğü zaman çizelgesi
// (Tur 81, Faz E4 — disiplin frontend SON alt-turu). Backend: DisciplineCaseViewSet
// .documents (GET zaman çizelgesi, Tur 76 Faz C) / .documents_generate (POST → PDF,
// Tur 77 Faz D motoru).
//
// Tek kart: (1) üretilebilir belgeyi (EK-1 kurul kararı / dizi pusulası / ceza tebliği)
// seç + üret → tarayıcıda PDF indir; her üretim daima kütüğe yazılır (KVKK — dizi
// pusulası bütünlüğü). (2) Üretilen belgelerin denetlenebilir zaman çizelgesi (içerik
// SAKLANMAZ). Tam disiplin erişimi gerektirir; 403 → bölüm gizlenir.

import { useCallback, useEffect, useState } from "react";

import { ApiError } from "../../lib/api";
import { saveBlob } from "../../lib/download";
import { SkeletonList } from "../../ui/Skeleton";
import { formatDate, todayIso } from "../../lib/format";
import Button from "../../ui/Button";
import Card from "../../ui/Card";
import Icon from "../../ui/Icon";
import Select from "../../ui/Select";
import { useConfirm } from "../../ui/ConfirmProvider";
import { useSnackbar } from "../../ui/SnackbarProvider";
import TextField from "../../ui/TextField";
import { categorizeDocuments, disiplinApi, documentDisplayName, PARTICIPANT_ROLE_TR } from "./api";
import { caseBranch, generatableTypesFor } from "./workflow";
import type {
  BoardAuthority,
  BoardOutcome,
  CaseStudent,
  DisciplineCase,
  DisciplineDecision,
  DisciplineParticipant,
  DocumentGenerateBody,
  DocumentLogBody,
  DocumentRecipient,
  DocumentType,
  DocumentVariant,
  GeneratableDocType,
  GeneratedDocument,
  NoticeKind,
} from "./api";
import { ALL_DOCUMENT_TYPES_TR } from "./api";
import { asMessage, FormError, PanelActions } from "./formHelpers";

const EK1_COMPLETENESS_FIELDS: (keyof DisciplineDecision)[] = [
  "accused_statement_summary",
  "witness_statement_summary",
  "other_evidence",
  "mitigating_aggravating",
  "committee_opinion",
  "psychosocial_summary",
  "boarding_status",
  "academic_standing",
  "health_status",
  "family_economic_status",
  "lives_with_family",
  "parents_alive",
  "parents_biological",
  "studies_near_family",
  "upbringing_environment",
  "family_residence_area",
  "incident_place",
  "incident_date",
  "prior_penalties_summary",
  "student_birth_date",
];

function hasMissingEk1Fields(decision: DisciplineDecision): boolean {
  return EK1_COMPLETENESS_FIELDS.some((field) => {
    const value = decision[field];
    return value === null || (typeof value === "string" && value.trim() === "");
  });
}

function studentNames(caseObj: DisciplineCase): Record<number, string> {
  const map: Record<number, string> = {};
  for (const s of caseObj.students) map[s.id] = s.full_name;
  return map;
}

export default function DocumentsSection({
  caseObj,
  canManage,
}: {
  caseObj: DisciplineCase;
  canManage: boolean;
}) {
  const [documents, setDocuments] = useState<GeneratedDocument[] | null>(null);
  const [hidden, setHidden] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [generating, setGenerating] = useState(false);
  const [adding, setAdding] = useState(false);
  const [reordering, setReordering] = useState(false);
  const [indexBusy, setIndexBusy] = useState(false);
  const [deletedDocs, setDeletedDocs] = useState<GeneratedDocument[] | null>(null);
  const [showTrash, setShowTrash] = useState(false);
  const [downloadingDocId, setDownloadingDocId] = useState<number | null>(null);
  const names = studentNames(caseObj);
  const snackbar = useSnackbar();
  const confirm = useConfirm();

  // Dizi pusulası (fihrist kapağı) PDF'ini üret + indir — kütüğe yazmaz.
  const downloadIndexSheet = useCallback(() => {
    setIndexBusy(true);
    disiplinApi
      .getIndexSheet(caseObj.id)
      .then((blob) => {
        saveBlob(blob, `${caseObj.case_no}-dizi-pusulasi.pdf`);
        setError(null);
      })
      .catch((e: unknown) => {
        setError(e instanceof ApiError ? e.message : "Dizi pusulası üretilemedi.");
      })
      .finally(() => setIndexBusy(false));
  }, [caseObj.id, caseObj.case_no]);

  const load = useCallback(() => {
    disiplinApi
      .listDocuments(caseObj.id)
      .then((list) => {
        setDocuments(list);
        setError(null);
      })
      .catch((e: unknown) => {
        if (e instanceof ApiError && e.status === 403) {
          setHidden(true);
          return;
        }
        setError(e instanceof ApiError ? e.message : "Evrak kütüğü yüklenemedi.");
      });
  }, [caseObj.id]);
  useEffect(load, [load]);

  // Bir belgeyi kendi KATEGORİSİ içinde bir basamak yukarı/aşağı taşır (Tur 141);
  // yeni tam sırayı (kategori-gruplu) backend'e yazar. Kategoriler arası taşıma yok.
  const moveInCategory = useCallback(
    (categoryIndex: number, itemIndex: number, dir: -1 | 1) => {
      if (documents === null || reordering) return;
      const grouped = categorizeDocuments(documents);
      const cat = grouped[categoryIndex];
      if (!cat) return;
      const target = itemIndex + dir;
      if (target < 0 || target >= cat.documents.length) return;
      const items = [...cat.documents];
      const a = items[itemIndex];
      const b = items[target];
      if (!a || !b) return;
      items[itemIndex] = b;
      items[target] = a;
      const newFlat = grouped.flatMap((c, i) => (i === categoryIndex ? items : c.documents));
      setReordering(true);
      disiplinApi
        .reorderDocuments(
          caseObj.id,
          newFlat.map((d) => d.id),
        )
        .then((list) => {
          setDocuments(list);
          setError(null);
        })
        .catch((e: unknown) => {
          setError(e instanceof ApiError ? e.message : "Sıralama güncellenemedi.");
        })
        .finally(() => setReordering(false));
    },
    [documents, reordering, caseObj.id],
  );

  // Çöp kutusu (silinmiş belgeler) — geri yükleme için lazy yüklenir (her GET SENSITIVE_READ).
  const loadDeleted = useCallback(() => {
    disiplinApi
      .listDeletedDocuments(caseObj.id)
      .then(setDeletedDocs)
      .catch(() => setDeletedDocs([]));
  }, [caseObj.id]);

  const handleRestore = useCallback(
    async (documentId: number) => {
      try {
        await disiplinApi.restoreDocument(caseObj.id, documentId);
        load();
        if (showTrash) loadDeleted();
        snackbar.success("Belge geri yüklendi.");
      } catch (e) {
        snackbar.error(e instanceof ApiError ? e.message : "Belge geri yüklenemedi.");
      }
    },
    [caseObj.id, load, loadDeleted, showTrash, snackbar],
  );

  const handleDelete = useCallback(
    async (doc: GeneratedDocument) => {
      const ok = await confirm({
        message: `'${documentDisplayName(doc)}' silinsin mi? (Yumuşak silme — geri alınabilir)`,
        confirmLabel: "Sil",
      });
      if (!ok) return;
      try {
        await disiplinApi.deleteDocument(caseObj.id, doc.id);
        load();
        if (showTrash) loadDeleted();
        snackbar.success("Belge silindi.", {
          action: { label: "Geri al", onClick: () => void handleRestore(doc.id) },
        });
      } catch (e) {
        snackbar.error(e instanceof ApiError ? e.message : "Belge silinemedi.");
      }
    },
    [caseObj.id, confirm, handleRestore, load, loadDeleted, showTrash, snackbar],
  );

  const downloadStoredPdf = useCallback(
    async (doc: GeneratedDocument) => {
      setDownloadingDocId(doc.id);
      try {
        const blob = await disiplinApi.downloadStoredDocument(caseObj.id, doc.id);
        saveBlob(
          blob,
          doc.stored_filename || `${caseObj.case_no}-${doc.document_type}-${doc.id}.pdf`,
        );
        snackbar.success("Saklanan PDF kopyası indirildi; yeniden yazdırabilirsiniz.");
      } catch (e) {
        snackbar.error(e instanceof ApiError ? e.message : "Saklanan PDF indirilemedi.");
      } finally {
        setDownloadingDocId(null);
      }
    },
    [caseObj.case_no, caseObj.id, snackbar],
  );

  const toggleTrash = () => {
    const next = !showTrash;
    setShowTrash(next);
    if (next && deletedDocs === null) loadDeleted();
  };

  if (hidden) return null;

  return (
    <Card elevation={1} className="p-6">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-title-medium text-on-surface">Evrak üretimi ve kütüğü</p>
        {canManage && !generating && !adding && (
          <div className="flex flex-wrap gap-2">
            <Button variant="tonal" icon="picture_as_pdf" onClick={() => setGenerating(true)}>
              Belge üret
            </Button>
            <Button variant="outlined" icon="upload_file" onClick={() => setAdding(true)}>
              Belge ekle
            </Button>
            <Button
              variant="text"
              icon="list_alt"
              disabled={indexBusy || (documents?.length ?? 0) === 0}
              onClick={downloadIndexSheet}
            >
              Dizi pusulası üret
            </Button>
          </div>
        )}
      </div>
      <p className="mt-1 text-body-small text-on-surface-variant">
        Resmî disiplin belgesi (PDF) üretilip indirilir ve bir kopyası yeniden yazdırılmak üzere
        veritabanında saklanır. Uygulama parolası etkinse PDF kopyası da şifrelenir ve günlük
        yedeklere dahil olur. Sürece dışarıdan gelen evrak "Belge ekle" ile, bir evrakı destekleyen
        ek belge ise satırdaki "Alt evrak ekle" ile eklenir. Dizi sırası ↑/↓ ile düzenlenebilir;
        ağaç tamamlanınca "Dizi pusulası üret" ile fihrist kapağı alınır.
      </p>

      {generating && (
        <div className="mt-4">
          <GenerateDocumentForm
            caseObj={caseObj}
            onCancel={() => setGenerating(false)}
            onGenerated={() => {
              setGenerating(false);
              load();
            }}
          />
        </div>
      )}

      {adding && (
        <div className="mt-4">
          <AddDocumentForm
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

      {documents === null ? (
        <SkeletonList rows={3} />
      ) : documents.length === 0 ? (
        <p className="mt-3 text-body-medium text-on-surface-variant">Henüz belge yok.</p>
      ) : (
        <div className="mt-4 space-y-5">
          {categorizeDocuments(documents).map((cat, ci) => (
            <div key={cat.label}>
              <p className="mb-2 flex items-center gap-2 text-label-large text-on-surface-variant">
                <span className="flex h-6 min-w-6 items-center justify-center rounded-full bg-secondary-container px-2 text-label-small text-on-secondary-container">
                  {ci + 1}
                </span>
                {cat.label}
              </p>
              <ol className="space-y-2">
                {cat.documents.map((d, ii) => (
                  <DocumentRow
                    key={d.id}
                    caseObj={caseObj}
                    label={`${ci + 1}.${ii + 1}`}
                    document={d}
                    names={names}
                    canManage={canManage}
                    reordering={reordering}
                    isFirst={ii === 0}
                    isLast={ii === cat.documents.length - 1}
                    onMoveUp={() => moveInCategory(ci, ii, -1)}
                    onMoveDown={() => moveInCategory(ci, ii, 1)}
                    onChanged={load}
                    onDelete={handleDelete}
                    onDownload={downloadStoredPdf}
                    downloadingDocId={downloadingDocId}
                  />
                ))}
              </ol>
            </div>
          ))}
        </div>
      )}

      {/* Evrak ağacının en altında silinen evraklar (lazy; geri yükleme/yeniden basım). */}
      {canManage && (
        <div className="mt-5 border-t border-outline-variant pt-4">
          <Button
            variant="text"
            icon={showTrash ? "expand_less" : "delete_outline"}
            onClick={toggleTrash}
            aria-expanded={showTrash}
          >
            Silinen evraklar{deletedDocs ? ` (${deletedDocs.length})` : ""}
          </Button>
          {showTrash &&
            (deletedDocs === null ? (
              <SkeletonList rows={2} />
            ) : deletedDocs.length === 0 ? (
              <p className="mt-2 text-body-small text-on-surface-variant">Çöp kutusu boş.</p>
            ) : (
              <ul className="mt-2 space-y-2">
                {deletedDocs.map((d) => (
                  <li
                    key={d.id}
                    className="flex flex-wrap items-center justify-between gap-2 rounded-shape-md border border-outline-variant bg-surface-container-low px-4 py-2"
                  >
                    <span className="min-w-0 text-body-medium text-on-surface-variant">
                      <Icon
                        name="description"
                        size="sm"
                        className="mr-1 align-middle text-primary"
                      />
                      <span className="text-on-surface">{documentDisplayName(d)}</span>
                      <span className="text-label-small"> · {d.document_type_display}</span>
                    </span>
                    <div className="flex flex-wrap gap-1">
                      {d.has_stored_pdf && (
                        <Button
                          variant="text"
                          icon="download"
                          disabled={downloadingDocId === d.id}
                          onClick={() => void downloadStoredPdf(d)}
                        >
                          Tekrar indir
                        </Button>
                      )}
                      <Button
                        variant="text"
                        icon="restore"
                        onClick={() => void handleRestore(d.id)}
                      >
                        Geri yükle
                      </Button>
                    </div>
                  </li>
                ))}
              </ul>
            ))}
        </div>
      )}
    </Card>
  );
}

function studentLabel(doc: GeneratedDocument, names: Record<number, string>): string | null {
  return doc.student !== null ? (names[doc.student] ?? `Öğrenci #${doc.student}`) : null;
}

// Ana evrak satırı — içerik + sayfa rozeti + (yöneticiyse) ↑/↓ + alt evrak ekle + düzenle.
function DocumentRow({
  caseObj,
  label,
  document: d,
  names,
  canManage,
  reordering,
  isFirst,
  isLast,
  onMoveUp,
  onMoveDown,
  onChanged,
  onDelete,
  onDownload,
  downloadingDocId,
}: {
  caseObj: DisciplineCase;
  label: string;
  document: GeneratedDocument;
  names: Record<number, string>;
  canManage: boolean;
  reordering: boolean;
  isFirst: boolean;
  isLast: boolean;
  onMoveUp: () => void;
  onMoveDown: () => void;
  onChanged: () => void;
  onDelete: (doc: GeneratedDocument) => void;
  onDownload: (doc: GeneratedDocument) => void;
  downloadingDocId: number | null;
}) {
  const [panel, setPanel] = useState<"sub" | "edit" | null>(null);
  const studentName = studentLabel(d, names);
  const subs = d.sub_documents ?? [];

  return (
    <li className="rounded-shape-md border border-outline-variant bg-surface-container-low p-4">
      <div className="flex gap-3">
        <span className="flex h-8 min-w-8 shrink-0 items-center justify-center rounded-full bg-secondary-container px-1.5 text-label-medium text-on-secondary-container">
          {label}
        </span>
        <div className="min-w-0 flex-1">
          <p className="flex flex-wrap items-center gap-2 text-body-large text-on-surface">
            <Icon name="description" size="base" className="text-primary" />
            <span className="font-medium">{documentDisplayName(d)}</span>
            <span className="rounded-full bg-surface-container-high px-2 py-0.5 text-label-small text-on-surface-variant">
              {d.page_count} sayfa
            </span>
            {d.has_stored_pdf && (
              <span className="rounded-full bg-primary-container px-2 py-0.5 text-label-small text-on-primary-container">
                PDF saklandı
              </span>
            )}
          </p>
          <p className="mt-1 text-label-small text-on-surface-variant">
            {d.document_type_display} · {formatDate(d.generated_on)}
            {studentName && ` · öğrenci: ${studentName}`}
          </p>
        </div>
        {canManage && (
          <div className="flex shrink-0 flex-col justify-center">
            <IconButton
              icon="keyboard_arrow_up"
              aria-label="Yukarı taşı"
              disabled={isFirst || reordering}
              onClick={onMoveUp}
            />
            <IconButton
              icon="keyboard_arrow_down"
              aria-label="Aşağı taşı"
              disabled={isLast || reordering}
              onClick={onMoveDown}
            />
          </div>
        )}
      </div>

      {/* Alt/destekleyici evraklar (girintili) */}
      {subs.length > 0 && (
        <ul className="mt-2 space-y-1 border-l-2 border-outline-variant pl-4">
          {subs.map((s, si) => (
            <SubDocumentRow
              key={s.id}
              caseObj={caseObj}
              label={`${label}.${si + 1}`}
              document={s}
              names={names}
              canManage={canManage}
              onChanged={onChanged}
              onDelete={onDelete}
              onDownload={onDownload}
              downloading={downloadingDocId === s.id}
            />
          ))}
        </ul>
      )}

      {canManage && (
        <div className="mt-2 flex flex-wrap gap-1">
          {d.has_stored_pdf && (
            <Button
              variant="text"
              icon="download"
              disabled={downloadingDocId === d.id}
              onClick={() => onDownload(d)}
            >
              Tekrar indir
            </Button>
          )}
          <Button
            variant="text"
            icon="subdirectory_arrow_right"
            onClick={() => setPanel(panel === "sub" ? null : "sub")}
          >
            Alt evrak ekle
          </Button>
          <Button
            variant="text"
            icon="edit"
            onClick={() => setPanel(panel === "edit" ? null : "edit")}
          >
            Düzenle
          </Button>
          {/* "Sil" yalnız alt evrak yokken görünür — alt evraklı ana belge silinemez (backend
              engelliyor); alt evrakları silince bu buton belirir (disabled+title yerine; WCAG). */}
          {subs.length === 0 && (
            <Button variant="text" icon="delete" onClick={() => onDelete(d)}>
              Sil
            </Button>
          )}
        </div>
      )}

      {panel === "sub" && (
        <div className="mt-2">
          <AddDocumentForm
            caseObj={caseObj}
            parentId={d.id}
            parentLabel={documentDisplayName(d)}
            onCancel={() => setPanel(null)}
            onAdded={() => {
              setPanel(null);
              onChanged();
            }}
          />
        </div>
      )}
      {panel === "edit" && (
        <div className="mt-2">
          <EditDocumentForm
            caseObj={caseObj}
            document={d}
            onCancel={() => setPanel(null)}
            onSaved={() => {
              setPanel(null);
              onChanged();
            }}
          />
        </div>
      )}
    </li>
  );
}

// Alt/destekleyici evrak satırı — girintili, sayfa rozeti + (yöneticiyse) düzenle.
function SubDocumentRow({
  caseObj,
  label,
  document: s,
  names,
  canManage,
  onChanged,
  onDelete,
  onDownload,
  downloading,
}: {
  caseObj: DisciplineCase;
  label: string;
  document: GeneratedDocument;
  names: Record<number, string>;
  canManage: boolean;
  onChanged: () => void;
  onDelete: (doc: GeneratedDocument) => void;
  onDownload: (doc: GeneratedDocument) => void;
  downloading: boolean;
}) {
  const [editing, setEditing] = useState(false);
  const studentName = studentLabel(s, names);
  return (
    <li className="text-body-medium text-on-surface-variant">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-label-small text-on-surface-variant">{label}</span>
        <Icon name="subdirectory_arrow_right" size="sm" className="text-primary" />
        <span className="text-on-surface">{documentDisplayName(s)}</span>
        <span className="text-label-small">· {s.document_type_display}</span>
        <span className="rounded-full bg-surface-container-high px-2 py-0.5 text-label-small">
          {s.page_count} sayfa
        </span>
        {studentName && <span className="text-label-small">· {studentName}</span>}
        {canManage && (
          <>
            {s.has_stored_pdf && (
              <IconButton
                icon="download"
                aria-label="Alt evrak PDF kopyasını tekrar indir"
                disabled={downloading}
                onClick={() => onDownload(s)}
              />
            )}
            <IconButton
              icon="edit"
              aria-label="Alt evrakı düzenle"
              disabled={false}
              onClick={() => setEditing((v) => !v)}
            />
            <IconButton
              icon="delete"
              aria-label="Alt evrakı sil"
              disabled={false}
              onClick={() => onDelete(s)}
            />
          </>
        )}
      </div>
      {editing && (
        <div className="mt-2">
          <EditDocumentForm
            caseObj={caseObj}
            document={s}
            onCancel={() => setEditing(false)}
            onSaved={() => {
              setEditing(false);
              onChanged();
            }}
          />
        </div>
      )}
    </li>
  );
}

// İkon butonu — 48px dokunma hedefi + aria-label + focus halkası (M3, §7.5).
function IconButton({
  icon,
  onClick,
  disabled,
  "aria-label": ariaLabel,
}: {
  icon: string;
  onClick: () => void;
  disabled: boolean;
  "aria-label": string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      aria-label={ariaLabel}
      className="flex h-12 w-12 items-center justify-center rounded-full text-on-surface-variant outline-none transition hover:bg-on-surface/8 focus-visible:outline-2 focus-visible:outline-primary disabled:pointer-events-none disabled:opacity-40"
    >
      <Icon name={icon} />
    </button>
  );
}

// Kütük kaydı metadata düzenleme (sayfa/başlık/açıklama; içerik değil; Tur 104).
function EditDocumentForm({
  caseObj,
  document: d,
  onCancel,
  onSaved,
}: {
  caseObj: DisciplineCase;
  document: GeneratedDocument;
  onCancel: () => void;
  onSaved: () => void;
}) {
  const [pageCount, setPageCount] = useState(String(d.page_count));
  const [title, setTitle] = useState(d.title);
  const [notes, setNotes] = useState(d.notes);
  const [sourceLabel, setSourceLabel] = useState(d.source_label);
  const [sourceName, setSourceName] = useState(d.source_name);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const snackbar = useSnackbar();

  const submit = async () => {
    setBusy(true);
    setError(null);
    try {
      await disiplinApi.updateDocument(caseObj.id, d.id, {
        page_count: Number(pageCount) || 1,
        title: title.trim(),
        notes: notes.trim(),
        source_label: sourceLabel.trim(),
        source_name: sourceName.trim(),
      });
      snackbar.success("Belge güncellendi.");
      onSaved();
    } catch (err) {
      setError(asMessage(err, "Belge düzenlenemedi."));
      setBusy(false);
    }
  };

  return (
    <div className="space-y-3 rounded-shape-md bg-surface-container p-3">
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <TextField
          label="Sayfa sayısı"
          type="number"
          min={1}
          max={999}
          value={pageCount}
          onChange={(e) => setPageCount(e.target.value)}
        />
        <TextField label="Başlık" value={title} onChange={(e) => setTitle(e.target.value)} />
      </div>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <TextField
          label="Kimden — sıfat/kaynak"
          value={sourceLabel}
          onChange={(e) => setSourceLabel(e.target.value)}
          helperText="Dizi pusulasında görünür (örn. Hakkında İşlem Yapılan, Tanık, Rehberlik Servisi)."
        />
        <TextField
          label="Kimden — ad"
          value={sourceName}
          onChange={(e) => setSourceName(e.target.value)}
        />
      </div>
      <TextField
        label="Açıklama (opsiyonel)"
        value={notes}
        onChange={(e) => setNotes(e.target.value)}
      />
      <FormError error={error} />
      <PanelActions busy={busy} onCancel={onCancel} onSubmit={submit} submitLabel="Kaydet" />
    </div>
  );
}

// Belge üretim formu — tür seç + (gerekirse) öğrenci/katılımcı/tarih → PDF indir.
function GenerateDocumentForm({
  caseObj,
  onCancel,
  onGenerated,
}: {
  caseObj: DisciplineCase;
  onCancel: () => void;
  onGenerated: () => void;
}) {
  const today = todayIso();
  const students = caseObj.students;
  // Dal A (yalnız yazılı uyarı) dosyasında kurul formları listelenmez (Tur 213, 3c).
  const branch = caseBranch(caseObj.events);
  const availableTypes = generatableTypesFor(branch);
  const [docType, setDocType] = useState<DocumentType>(availableTypes[0].value);
  const [generatedOn, setGeneratedOn] = useState(today);
  const [recipient, setRecipient] = useState<DocumentRecipient>("student");
  const [studentId, setStudentId] = useState<string>(
    students.length === 1 ? String(students[0].id) : "",
  );
  // Dal B formları (Tur 106): katılımcı + GEÇİCİ tarih/saat/yer + variant.
  const [participants, setParticipants] = useState<DisciplineParticipant[] | null>(null);
  const [participantId, setParticipantId] = useState<string>("");
  const [statementDate, setStatementDate] = useState("");
  const [statementTime, setStatementTime] = useState("");
  const [statementPlace, setStatementPlace] = useState("");
  // İfade tutanağı dolu-bas (Tur 144): konu/sorular + ifade gövdesi — GEÇİCİ, no-trace
  // (yalnız PDF'e basılır; backend'e gönderilir ama hiçbir yere kaydedilmez/loglanmaz).
  const [statementSubject, setStatementSubject] = useState("");
  const [statementBody, setStatementBody] = useState("");
  // Form-02 davranış özeti (Tur 213, 3a) — GEÇİCİ; uyarı kaydından prefill edilir.
  const [behaviorSummary, setBehaviorSummary] = useState("");
  const [warningPrefillFor, setWarningPrefillFor] = useState<string | null>(null);
  const [variant, setVariant] = useState<DocumentVariant>("student");
  const [sourceLabel, setSourceLabel] = useState(""); // bilgi alma "kaynak" (Tur 141)
  // Üst kurul kararı tebliği (Tur 220, talep 3) — hepsi GEÇİCİ (yalnız PDF'e basılır).
  const [noticeKind, setNoticeKind] = useState<NoticeKind>("approval");
  const [boardAuthority, setBoardAuthority] = useState<BoardAuthority | "">("");
  const [boardDecisionNo, setBoardDecisionNo] = useState("");
  const [boardDecisionDate, setBoardDecisionDate] = useState("");
  const [boardOutcome, setBoardOutcome] = useState<BoardOutcome | "">("");
  const [resultSummary, setResultSummary] = useState("");
  const [boardPrefillFor, setBoardPrefillFor] = useState<string | null>(null);
  const [ek1Decisions, setEk1Decisions] = useState<DisciplineDecision[] | null>(null);
  const [title, setTitle] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const snackbar = useSnackbar();

  const meta: GeneratableDocType =
    availableTypes.find((t) => t.value === docType) ?? availableTypes[0];

  // Katılımcı gerektiren bir tür seçilince dosya katılımcılarını bir kez çek.
  useEffect(() => {
    if (!meta.participantRequired || participants !== null) return;
    disiplinApi
      .listParticipants(caseObj.id)
      .then(setParticipants)
      .catch(() => setParticipants([]));
  }, [meta.participantRequired, participants, caseObj.id]);

  // Form-02: seçili öğrencinin en yeni uyarı kaydının özeti, alan boşken prefill edilir
  // (kullanıcı yazdıysa ezilmez; öğrenci değişince yeniden denenir).
  useEffect(() => {
    if (!meta.behaviorSummary || !studentId || warningPrefillFor === studentId) return;
    setWarningPrefillFor(studentId);
    disiplinApi
      .listWarnings(caseObj.id)
      .then((warnings) => {
        const latest = warnings.find((w) => String(w.student) === studentId);
        if (latest?.summary) {
          setBehaviorSummary((prev) => (prev.trim() ? prev : latest.summary));
        }
      })
      .catch(() => undefined); // prefill başarısızlığı sessiz — alan elle doldurulabilir
  }, [meta.behaviorSummary, studentId, warningPrefillFor, caseObj.id]);

  // Üst kurul tebliği prefill'i (Tur 220): seçili öğrencinin kararından merci, en son
  // sonuçlanmış itirazından tür/sonuç/özet önerilir (kullanıcı yazdıysa ezilmez).
  useEffect(() => {
    if (!meta.boardDecisionNotice || !studentId || boardPrefillFor === studentId) return;
    setBoardPrefillFor(studentId);
    disiplinApi
      .listDecisions(caseObj.id)
      .then(({ decisions }) => {
        const d = decisions.find((x) => String(x.student) === studentId);
        if (!d) return;
        const resolved = d.appeals
          .filter((a) => a.resulted_on && a.result !== "PENDING")
          .sort((a, b) => (b.resulted_on ?? "").localeCompare(a.resulted_on ?? ""))[0];
        if (resolved) {
          setNoticeKind("appeal_result");
          setBoardAuthority(resolved.appeal_authority as BoardAuthority);
          setBoardOutcome(resolved.result as BoardOutcome);
          if (resolved.result_notes) {
            setResultSummary((prev) => (prev.trim() ? prev : resolved.result_notes));
          }
        } else if (d.approval_authority !== "PRINCIPAL") {
          setBoardAuthority(d.approval_authority as BoardAuthority);
        }
      })
      .catch(() => undefined); // prefill başarısızlığı sessiz — alanlar elle doldurulur
  }, [meta.boardDecisionNotice, studentId, boardPrefillFor, caseObj.id]);

  // EK-1 üretiminden önce seçili öğrencinin anlatı + bağlam alanlarını denetle.
  // Belge üretimini engellemez; boş alanların PDF'e taşınacağını görünür kılar.
  useEffect(() => {
    if (docType !== "COMMITTEE_DECISION" || !studentId) {
      setEk1Decisions(null);
      return;
    }
    let cancelled = false;
    setEk1Decisions(null);
    disiplinApi
      .listDecisions(caseObj.id)
      .then(({ decisions }) => {
        if (!cancelled) setEk1Decisions(decisions);
      })
      .catch(() => {
        if (!cancelled) setEk1Decisions([]);
      });
    return () => {
      cancelled = true;
    };
  }, [docType, studentId, caseObj.id]);

  // Seçili türün rol filtresine uyan katılımcılar (boşsa hepsi).
  const eligibleParticipants = (participants ?? []).filter(
    (p) => !meta.participantRoleFilter || meta.participantRoleFilter.includes(p.role),
  );
  const selectedEk1Decision =
    docType === "COMMITTEE_DECISION" && studentId && ek1Decisions
      ? ek1Decisions.find((d) => String(d.student) === studentId)
      : undefined;

  // Kişi değişiminde o kişiye özgü GEÇİCİ alanlar sıfırlanır: içerik hiçbir yere
  // kaydedilmediği için (no-trace) tek koruma formun kendisidir — aksi hâlde A'nın
  // ifadesi/davranış özeti B'nin resmî tutanağına basılır (md. 194 + KVKK).
  // Dolu alan silindiyse kullanıcı uyarılır; sessiz veri kaybı olmaz.
  const handleParticipantChange = (next: string) => {
    setParticipantId(next);
    if (statementSubject.trim() || statementBody.trim()) {
      snackbar.show("Katılımcı değişti — ifade/savunma metni temizlendi.");
    }
    setStatementSubject("");
    setStatementBody("");
  };

  const handleStudentChange = (next: string) => {
    setStudentId(next);
    if (
      behaviorSummary.trim() ||
      resultSummary.trim() ||
      boardDecisionNo.trim() ||
      boardDecisionDate
    ) {
      snackbar.show("Öğrenci değişti — öğrenciye özgü metin alanları temizlendi.");
    }
    setBehaviorSummary("");
    setWarningPrefillFor(null); // yeni öğrencinin uyarı özeti yeniden önerilsin
    setNoticeKind("approval");
    setBoardAuthority("");
    setBoardDecisionNo("");
    setBoardDecisionDate("");
    setBoardOutcome("");
    setResultSummary("");
    setBoardPrefillFor(null); // yeni öğrencinin kararı/itirazı yeniden önerilsin
  };

  const submit = async () => {
    setBusy(true);
    setError(null);
    try {
      if (meta.studentRequired && !studentId) {
        throw new Error("Bu belge öğrenciye özgüdür; bir öğrenci seçilmelidir.");
      }
      if (meta.participantRequired && !participantId) {
        throw new Error("Bu belge bir katılımcıya (mağdur/suçlanan/tanık) yöneliktir; seçiniz.");
      }
      const body: DocumentGenerateBody = {
        document_type: docType,
        generated_on: generatedOn,
        title: title.trim(),
      };
      if (meta.recipientSelectable) body.recipient = recipient;
      if (meta.studentRequired) body.student_id = Number(studentId);
      if (meta.participantRequired) body.participant_id = Number(participantId);
      if (meta.scheduling) {
        body.statement_date = statementDate || null;
        body.statement_time = statementTime.trim();
        body.statement_place = statementPlace.trim();
      }
      if (meta.freeformStatement) {
        // İçerik no-trace: backend yalnız PDF'e basar, kaydetmez/loglamaz (Tur 142).
        body.statement_subject = statementSubject.trim();
        body.statement_body = statementBody.trim();
      }
      if (meta.behaviorSummary) {
        if (!behaviorSummary.trim()) {
          throw new Error(
            "Davranışın kısa açıklaması zorunludur (Form-02 metnindeki tırnak içine basılır).",
          );
        }
        body.behavior_summary = behaviorSummary.trim();
      }
      if (meta.variantOptions) body.variant = variant;
      if (meta.sourceOptions) body.source_label = sourceLabel;
      if (meta.boardDecisionNotice) {
        // GEÇİCİ alanlar: yalnız PDF'e basılır; merci/sonuç boşsa backend türetir.
        body.notice_kind = noticeKind;
        body.board_authority = boardAuthority;
        body.board_decision_no = boardDecisionNo.trim();
        body.board_decision_date = boardDecisionDate || null;
        body.board_outcome = boardOutcome;
        body.result_summary = resultSummary.trim();
      }
      const blob = await disiplinApi.generateDocument(caseObj.id, body);
      // Üretilen PDF'i tarayıcıda indir (downloadAttachment emsali).
      const suffix = meta.recipientSelectable
        ? `-${recipient}`
        : meta.variantOptions
          ? `-${variant}`
          : "";
      saveBlob(blob, `${caseObj.case_no}-${docType}${suffix}.pdf`);
      snackbar.success("Belge üretildi.");
      onGenerated();
    } catch (err) {
      setError(asMessage(err, "Belge üretilemedi."));
      setBusy(false);
    }
  };

  return (
    <div className="space-y-4 rounded-shape-md bg-surface-container-low p-4">
      <p className="text-title-medium text-on-surface">Belge üret (PDF)</p>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <Select
          label="Belge türü"
          required
          value={docType}
          onChange={(e) => {
            const next = e.target.value as DocumentType;
            setDocType(next);
            setParticipantId(""); // tür değişince rol filtresi değişebilir
            setSourceLabel(""); // kaynak seçimini sıfırla (yalnız bilgi almada görünür)
            setStatementSubject(""); // ifade içeriğini sıfırla (no-trace; tür değişince taşma)
            setStatementBody("");
            setBehaviorSummary(""); // Form-02 özeti türe özgü (Tur 213); prefill yeniden dener
            setWarningPrefillFor(null);
            // Üst kurul tebliği alanlarını sıfırla (Tur 220); prefill yeniden dener.
            setNoticeKind("approval");
            setBoardAuthority("");
            setBoardDecisionNo("");
            setBoardDecisionDate("");
            setBoardOutcome("");
            setResultSummary("");
            setBoardPrefillFor(null);
            const nextMeta = availableTypes.find((t) => t.value === next);
            setVariant(nextMeta?.variantOptions?.[0]?.value ?? "student"); // variant'ı türe göre sıfırla
          }}
          options={availableTypes.map((t) => ({
            value: t.value,
            label: t.label,
          }))}
        />
        <TextField
          label="Üretim tarihi"
          type="date"
          required
          value={generatedOn}
          onChange={(e) => setGeneratedOn(e.target.value)}
        />
      </div>
      <p className="text-body-small text-on-surface-variant">
        <Icon name="info" size="sm" className="mr-1 align-middle" />
        {meta.description}
      </p>

      {branch === "A" && (
        <p className="rounded-shape-sm bg-surface-container px-3 py-2 text-body-small text-on-surface-variant">
          <Icon name="filter_alt" size="sm" className="mr-1 align-middle" />
          Dal A (müdür uyarısı) dosyası — disiplin kurulu formları bu listede gösterilmez.
        </p>
      )}

      {meta.studentRequired && (
        <Select
          label="Öğrenci"
          required
          placeholder="Seçiniz…"
          value={studentId}
          onChange={(e) => handleStudentChange(e.target.value)}
          options={students.map((s: CaseStudent) => ({
            value: String(s.id),
            label: s.class_label ? `${s.full_name} · ${s.class_label}` : s.full_name,
          }))}
        />
      )}

      {docType === "COMMITTEE_DECISION" &&
        studentId &&
        ek1Decisions !== null &&
        (!selectedEk1Decision || hasMissingEk1Fields(selectedEk1Decision)) && (
          <div
            role="status"
            className="flex items-start gap-2 rounded-shape-sm bg-tertiary-container px-4 py-3 text-body-small text-on-tertiary-container"
          >
            <Icon name="warning" size="sm" className="mt-0.5 shrink-0" />
            {!selectedEk1Decision ? (
              <p>
                <span className="text-label-medium">Bu öğrenci için resmî karar bulunamadı.</span>{" "}
                Önce <span className="font-medium">Kurul &amp; Karar → Resmî kararlar</span>{" "}
                bölümünden karar ekleyin.
              </p>
            ) : hasMissingEk1Fields(selectedEk1Decision) ? (
              <p>
                <span className="text-label-medium">EK-1 bilgileri eksik.</span> Öğrenciye ilişkin
                anlatı ve sosyoekonomik bilgiler henüz tamamlanmamış. Boş alanlar üretilen belgede
                boş görünecektir. Bilgileri{" "}
                <span className="font-medium">
                  Kurul &amp; Karar → Resmî kararlar → EK-1 anlatı
                </span>{" "}
                bölümünden doldurabilirsiniz.
              </p>
            ) : null}
          </div>
        )}

      {meta.participantRequired &&
        (participants === null ? (
          <p className="text-body-small text-on-surface-variant">Katılımcılar yükleniyor…</p>
        ) : eligibleParticipants.length === 0 ? (
          <p className="rounded-shape-sm bg-surface-container px-3 py-2 text-body-small text-on-surface-variant">
            Uygun katılımcı yok. Bu belge için önce "Katılımcılar" bölümünden ilgili kişiyi
            (mağdur/suçlanan/tanık) ekleyin.
          </p>
        ) : (
          <Select
            label="İlgili katılımcı"
            required
            placeholder="Seçiniz…"
            value={participantId}
            onChange={(e) => handleParticipantChange(e.target.value)}
            options={eligibleParticipants.map((p) => ({
              value: String(p.id),
              label: `${p.name_snapshot || p.external_name || `Katılımcı #${p.id}`} · ${PARTICIPANT_ROLE_TR[p.role]}`,
            }))}
          />
        ))}

      {meta.variantOptions && (
        <Select
          label={meta.variantLabel ?? "Sürüm"}
          required
          value={variant}
          onChange={(e) => setVariant(e.target.value as DocumentVariant)}
          options={meta.variantOptions}
        />
      )}

      {meta.sourceOptions && (
        <Select
          label="Kaynak (dizi pusulasında 'kimden')"
          placeholder="Seçiniz…"
          value={sourceLabel}
          onChange={(e) => setSourceLabel(e.target.value)}
          options={meta.sourceOptions.map((s) => ({ value: s, label: s }))}
        />
      )}

      {meta.scheduling && (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
          <TextField
            label="Çağrı/toplantı tarihi"
            type="date"
            value={statementDate}
            onChange={(e) => setStatementDate(e.target.value)}
            helperText="Boş bırakılırsa belgede …/…/202… çıkar."
          />
          <TextField
            label="Saat"
            value={statementTime}
            onChange={(e) => setStatementTime(e.target.value)}
            placeholder="Örn. 10:30"
          />
          <TextField
            label="Yer"
            value={statementPlace}
            onChange={(e) => setStatementPlace(e.target.value)}
            placeholder="Müdür Yardımcısı Odası"
          />
        </div>
      )}

      {meta.boardDecisionNotice && (
        <div className="space-y-3">
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <Select
              label="Tebliğ türü"
              required
              value={noticeKind}
              onChange={(e) => {
                setNoticeKind(e.target.value as NoticeKind);
                setBoardOutcome(""); // sonuç ekseni türe bağlı — sıfırla
              }}
              options={[
                { value: "approval", label: "Onay mercii kararı (md. 169/2)" },
                { value: "appeal_result", label: "İtiraz sonucu (md. 169/3-4)" },
              ]}
            />
            <Select
              label="Kararı veren merci"
              value={boardAuthority}
              onChange={(e) => setBoardAuthority(e.target.value as BoardAuthority | "")}
              options={[
                { value: "", label: "Otomatik (karardan / itirazdan)" },
                { value: "DISTRICT_BOARD", label: "İlçe öğrenci disiplin kurulu" },
                { value: "PROVINCIAL_BOARD", label: "İl öğrenci disiplin kurulu" },
                // Üst kurul yalnız itiraz mercii olabilir (md. 205) — S1'de gizlenir.
                ...(noticeKind === "appeal_result"
                  ? [{ value: "UPPER_BOARD", label: "Öğrenci üst disiplin kurulu" }]
                  : []),
              ]}
            />
            <TextField
              label="Merci karar no"
              value={boardDecisionNo}
              onChange={(e) => setBoardDecisionNo(e.target.value)}
              placeholder="örn. 2026/12"
            />
            <TextField
              label="Merci karar tarihi"
              type="date"
              value={boardDecisionDate}
              onChange={(e) => setBoardDecisionDate(e.target.value)}
            />
            <Select
              label="Karar sonucu"
              value={boardOutcome}
              onChange={(e) => setBoardOutcome(e.target.value as BoardOutcome | "")}
              options={[
                { value: "", label: "Otomatik (onay: onaylandı / itiraz: kayıttan)" },
                ...(noticeKind === "approval"
                  ? [
                      { value: "APPROVED", label: "Onaylandı" },
                      { value: "MODIFIED", label: "Değiştirilerek onaylandı" },
                    ]
                  : [
                      { value: "UPHELD", label: "Onandı (itiraz reddedildi)" },
                      { value: "REDUCED", label: "Değiştirildi" },
                      { value: "OVERTURNED", label: "Kaldırıldı" },
                    ]),
              ]}
            />
          </div>
          <div>
            <label
              htmlFor="gen-board-summary"
              className="mb-1 block text-label-large text-on-surface-variant"
            >
              Kurul kararının özeti{" "}
              {boardOutcome === "MODIFIED" || boardOutcome === "REDUCED" ? (
                <span className="text-error">*</span>
              ) : (
                <span className="text-on-surface-variant">(opsiyonel)</span>
              )}
            </label>
            <textarea
              id="gen-board-summary"
              rows={3}
              value={resultSummary}
              onChange={(e) => setResultSummary(e.target.value)}
              className="block w-full rounded-shape-xs border border-outline bg-surface px-4 py-3 text-body-medium text-on-surface outline-none focus-visible:ring-2 focus-visible:ring-primary focus:border-primary"
            />
            <p className="mt-1 text-body-small text-on-surface-variant">
              "Değiştirildi" sonuçlarında zorunlu (değişen ceza belgeye yazılır). İçerik kaydedilmez
              — yalnız üretilen PDF'e basılır.
            </p>
          </div>
        </div>
      )}

      {meta.freeformStatement && (
        <div className="space-y-3">
          <div>
            <label
              htmlFor="gen-stmt-subject"
              className="mb-1 block text-label-large text-on-surface-variant"
            >
              {meta.freeformStatementLabels?.subject ?? "Disiplin konusu / sorular"} (opsiyonel)
            </label>
            <textarea
              id="gen-stmt-subject"
              rows={3}
              value={statementSubject}
              onChange={(e) => setStatementSubject(e.target.value)}
              className="block w-full rounded-shape-xs border border-outline bg-surface px-4 py-3 text-body-medium text-on-surface outline-none focus-visible:ring-2 focus-visible:ring-primary focus:border-primary"
            />
          </div>
          <div>
            <label
              htmlFor="gen-stmt-body"
              className="mb-1 block text-label-large text-on-surface-variant"
            >
              {meta.freeformStatementLabels?.body ?? "İfade metni"} (opsiyonel)
            </label>
            <textarea
              id="gen-stmt-body"
              rows={6}
              value={statementBody}
              onChange={(e) => setStatementBody(e.target.value)}
              className="block w-full rounded-shape-xs border border-outline bg-surface px-4 py-3 text-body-medium text-on-surface outline-none focus-visible:ring-2 focus-visible:ring-primary focus:border-primary"
            />
          </div>
          <p className="text-body-small text-on-surface-variant">
            <Icon name="info" size="sm" className="mr-1 align-middle" />
            Yazılırsa tutanağa basılır; boş bırakılırsa elle yazım için boş kalır. İçerik
            kaydedilmez — yalnız üretilen PDF'e basılır (no-trace).
          </p>
        </div>
      )}

      {meta.behaviorSummary && (
        <div>
          <label
            htmlFor="gen-behavior-summary"
            className="mb-1 block text-label-large text-on-surface-variant"
          >
            Davranışın kısa açıklaması <span className="text-error">*</span>
          </label>
          <textarea
            id="gen-behavior-summary"
            rows={3}
            required
            value={behaviorSummary}
            onChange={(e) => setBehaviorSummary(e.target.value)}
            className="block w-full rounded-shape-xs border border-outline bg-surface px-4 py-3 text-body-medium text-on-surface outline-none focus-visible:ring-2 focus-visible:ring-primary focus:border-primary"
          />
          <p className="mt-1 text-body-small text-on-surface-variant">
            Form metnindeki tırnak içine basılır. Dosyada müdür uyarısı kaydı varsa özeti
            ön-doldurulur; metin kaydedilmez — yalnız üretilen PDF'e basılır (no-trace).
          </p>
        </div>
      )}

      {meta.recipientSelectable && (
        <Select
          label="Tebliğ alıcısı"
          required
          value={recipient}
          onChange={(e) => setRecipient(e.target.value as DocumentRecipient)}
          options={
            meta.recipientOptions ?? [
              { value: "student", label: "Öğrenciye (Form-14/16)" },
              { value: "parent", label: "Veliye (Form-15/17)" },
            ]
          }
        />
      )}

      <TextField
        label="Başlık (opsiyonel)"
        value={title}
        onChange={(e) => setTitle(e.target.value)}
        helperText="Boş bırakılırsa belge türü başlık olur (katılımcı belgelerinde dizi pusulasında 'kimden' görünür)."
      />

      <FormError error={error} />
      <PanelActions busy={busy} onCancel={onCancel} onSubmit={submit} submitLabel="Üret ve indir" />
    </div>
  );
}

// Manuel belge / alt evrak ekleme formu — kütüğe kaydeder (Tur 103-104). parentId
// verilirse ALT/destekleyici evraktır. İçerik saklanmaz; yalnız metadata izlenir.
function AddDocumentForm({
  caseObj,
  parentId,
  parentLabel,
  onCancel,
  onAdded,
}: {
  caseObj: DisciplineCase;
  parentId?: number;
  parentLabel?: string;
  onCancel: () => void;
  onAdded: () => void;
}) {
  const isSub = parentId !== undefined;
  const today = todayIso();
  const students = caseObj.students;
  const [docType, setDocType] = useState<DocumentType>("OTHER");
  const [title, setTitle] = useState("");
  const [generatedOn, setGeneratedOn] = useState(today);
  const [studentId, setStudentId] = useState("");
  const [pageCount, setPageCount] = useState("1");
  const [notes, setNotes] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const snackbar = useSnackbar();

  const submit = async () => {
    setBusy(true);
    setError(null);
    try {
      if (!title.trim()) throw new Error("Belge başlığı zorunludur.");
      const body: DocumentLogBody = {
        document_type: docType,
        title: title.trim(),
        generated_on: generatedOn,
        page_count: Number(pageCount) || 1,
        notes: notes.trim(),
      };
      if (studentId) body.student_id = Number(studentId);
      if (parentId !== undefined) body.parent_document_id = parentId;
      await disiplinApi.addDocument(caseObj.id, body);
      snackbar.success("Belge kütüğe eklendi.");
      onAdded();
    } catch (err) {
      setError(asMessage(err, "Belge eklenemedi."));
      setBusy(false);
    }
  };

  return (
    <div className="space-y-4 rounded-shape-md bg-surface-container-low p-4">
      <p className="text-title-medium text-on-surface">
        {isSub ? "Alt evrak ekle" : "Belge ekle (manuel)"}
      </p>
      <p className="text-body-small text-on-surface-variant">
        <Icon name="info" size="sm" className="mr-1 align-middle" />
        {isSub
          ? `"${parentLabel}" evrakını destekleyen ek belge (örn. delil, ek dilekçe). İçeriği saklanmaz; yalnız ne olduğu kütüğe işlenir.`
          : "Sürece dışarıdan gelen evrakı (örn. taranıp dosyaya konan tutanak) dizi pusulasına ekler. İçerik saklanmaz; yalnız metadata işlenir."}
      </p>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <Select
          label="Belge türü"
          required
          value={docType}
          onChange={(e) => setDocType(e.target.value as DocumentType)}
          options={(Object.entries(ALL_DOCUMENT_TYPES_TR) as [DocumentType, string][]).map(
            ([value, label]) => ({ value, label }),
          )}
        />
        <TextField
          label="Belge tarihi"
          type="date"
          required
          value={generatedOn}
          onChange={(e) => setGeneratedOn(e.target.value)}
        />
      </div>
      <TextField
        label={isSub ? "Açıklama (ne olduğu)" : "Başlık"}
        required
        value={title}
        onChange={(e) => setTitle(e.target.value)}
        helperText={isSub ? "Örn. 'Olay yeri fotoğrafı'." : "Örn. 'Olay tutanağı — 12.05.2026'."}
      />
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <TextField
          label="Sayfa sayısı"
          type="number"
          min={1}
          max={999}
          value={pageCount}
          onChange={(e) => setPageCount(e.target.value)}
        />
        <Select
          label="Öğrenci (opsiyonel)"
          placeholder="Dosya geneli"
          value={studentId}
          onChange={(e) => setStudentId(e.target.value)}
          options={students.map((s: CaseStudent) => ({
            value: String(s.id),
            label: s.class_label ? `${s.full_name} · ${s.class_label}` : s.full_name,
          }))}
        />
      </div>
      <TextField
        label="Açıklama (opsiyonel)"
        value={notes}
        onChange={(e) => setNotes(e.target.value)}
      />
      <FormError error={error} />
      <PanelActions busy={busy} onCancel={onCancel} onSubmit={submit} submitLabel="Kütüğe ekle" />
    </div>
  );
}
