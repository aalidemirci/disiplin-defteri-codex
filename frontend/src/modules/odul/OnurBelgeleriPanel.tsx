import { useCallback, useEffect, useState } from "react";

import { ApiError } from "../../lib/api";
import { todayIso } from "../../lib/format";
import Autocomplete from "../../ui/Autocomplete";
import Button from "../../ui/Button";
import Card from "../../ui/Card";
import Icon from "../../ui/Icon";
import { SkeletonList } from "../../ui/Skeleton";
import Select from "../../ui/Select";
import TextField from "../../ui/TextField";
import { personnelLookupApi, studentLookupApi } from "../disiplin/api";
import { okulApi, type SchoolTerm } from "../okul/api";
import {
  criteriaDisplay,
  HONOR_CRITERION_TR,
  HONOR_PROPOSER_ROLE_TR,
  HONOR_STATUS_TR,
  odulApi,
} from "./api";
import type {
  HonorCertificate,
  HonorCertificateStatus,
  HonorCriterion,
  HonorProposerRole,
} from "./api";

const STATUS_CHIP: Record<HonorCertificateStatus, string> = {
  PROPOSED: "bg-secondary-container text-on-secondary-container",
  HONOR_BOARD_RECOMMENDED: "bg-tertiary-container text-on-tertiary-container",
  AWARDED: "bg-primary-container text-on-primary-container",
  PRINCIPAL_APPROVED: "bg-primary-container text-on-primary-container",
  PRINCIPAL_REJECTED: "bg-error-container text-on-error-container",
  REJECTED: "bg-error-container text-on-error-container",
};

const STATUS_FILTERS = [
  { value: "", label: "Tümü" },
  ...Object.entries(HONOR_STATUS_TR).map(([value, label]) => ({ value, label })),
];

const CRITERION_OPTIONS = (Object.entries(HONOR_CRITERION_TR) as [HonorCriterion, string][]).map(
  ([value, label]) => ({ value, label }),
);

interface LookupOption {
  id: number;
  label: string;
  sublabel?: string;
}

export default function OnurBelgeleriPanel() {
  const [items, setItems] = useState<HonorCertificate[]>([]);
  const [terms, setTerms] = useState<SchoolTerm[]>([]);
  const [termId, setTermId] = useState<number | null>(null);
  const [status, setStatus] = useState<HonorCertificateStatus | "">("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [proposing, setProposing] = useState(false);

  useEffect(() => {
    okulApi
      .listSchoolYears()
      .then(async (years) => {
        const active = years.find((year) => year.is_active);
        if (!active) throw new Error("Aktif ders yılı bulunamadı.");
        const rows = await okulApi.listSchoolTerms(active.id);
        setTerms(rows);
        const today = todayIso();
        setTermId(
          rows.find((term) => term.start_date <= today && today <= term.end_date)?.id ??
            rows[0]?.id ??
            null,
        );
      })
      .catch((e: unknown) => setError(e instanceof Error ? e.message : "Dönemler yüklenemedi."));
  }, []);

  const load = useCallback(() => {
    if (termId === null) {
      setItems([]);
      setLoading(false);
      return;
    }
    setLoading(true);
    odulApi
      .listCertificates({ status, schoolTermId: termId })
      .then((rows) => {
        setItems(rows);
        setError(null);
      })
      .catch((e: unknown) =>
        setError(e instanceof ApiError ? e.message : "Onur teklifleri yüklenemedi."),
      )
      .finally(() => setLoading(false));
  }, [status, termId]);

  useEffect(load, [load]);

  return (
    <div className="space-y-5">
      <p className="max-w-3xl text-body-medium text-on-surface-variant">
        Bu alan onur belgesi düzenlemez. Dönemlik teklifleri kaydeder; Onur Kurulunca uygun
        görülenler teklif çizelgesiyle Okul Öğrenci Ödül ve Disiplin Kuruluna gönderilir (md. 161 ve
        183/b).
      </p>

      <div className="flex flex-wrap items-end justify-between gap-3">
        <div className="flex flex-wrap gap-3">
          <div className="w-48">
            <Select
              label="Teklif dönemi"
              value={termId === null ? "" : String(termId)}
              onChange={(event) => setTermId(Number(event.target.value))}
              options={terms.map((term) => ({ value: String(term.id), label: term.name }))}
            />
          </div>
          <div className="w-56">
            <Select
              label="Durum"
              value={status}
              onChange={(event) => setStatus(event.target.value as HonorCertificateStatus | "")}
              options={STATUS_FILTERS}
            />
          </div>
        </div>
        {!proposing && (
          <Button icon="add" onClick={() => setProposing(true)} disabled={termId === null}>
            Yeni teklif
          </Button>
        )}
      </div>

      {terms.length === 0 && !loading && (
        <ErrorBanner message="Onur teklifleri için önce aktif ders yılının iki dönemi tanımlanmalıdır." />
      )}
      {error && <ErrorBanner message={error} />}

      {proposing && termId !== null && (
        <ProposeForm
          schoolTermId={termId}
          onCancel={() => setProposing(false)}
          onCreated={() => {
            setProposing(false);
            load();
          }}
        />
      )}

      {loading ? (
        <SkeletonList rows={5} />
      ) : items.length === 0 ? (
        <Card elevation={1} className="p-6">
          <p className="text-body-medium text-on-surface-variant">
            Seçilen dönem ve durumda onur belgesi teklifi bulunamadı.
          </p>
        </Card>
      ) : (
        <ul className="space-y-2">
          {items.map((proposal) => (
            <ProposalRow key={proposal.id} proposal={proposal} />
          ))}
        </ul>
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

function ProposalRow({ proposal }: { proposal: HonorCertificate }) {
  return (
    <li>
      <Card elevation={1} className="p-4">
        <p className="flex flex-wrap items-center gap-2 text-title-small text-on-surface">
          <span
            className={`inline-flex items-center rounded-shape-xl px-2 py-0.5 text-label-small ${STATUS_CHIP[proposal.status]}`}
          >
            {proposal.status_display || HONOR_STATUS_TR[proposal.status]}
          </span>
          {proposal.student_name}
          {proposal.term_name && (
            <span className="text-label-small text-on-surface-variant">{proposal.term_name}</span>
          )}
        </p>
        <p className="mt-1 text-body-small text-on-surface-variant">
          {criteriaDisplay(proposal.criteria).join(" · ")}
        </p>
        <p className="mt-1 text-label-small text-on-surface-variant">
          Teklif eden: {proposal.proposer_role_display}
          {proposal.proposer_name ? ` (${proposal.proposer_name})` : ""}
        </p>
      </Card>
    </li>
  );
}

function ProposeForm({
  schoolTermId,
  onCancel,
  onCreated,
}: {
  schoolTermId: number;
  onCancel: () => void;
  onCreated: () => void;
}) {
  const [proposerRole, setProposerRole] = useState<HonorProposerRole>("TEACHER");
  const [proposer, setProposer] = useState<LookupOption | null>(null);
  const [student, setStudent] = useState<LookupOption | null>(null);
  const [criteria, setCriteria] = useState<HonorCriterion[]>([]);
  const [justification, setJustification] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const searchStudent = (query: string): Promise<LookupOption[]> =>
    studentLookupApi.search(query).then((rows) =>
      rows.map((row) => ({
        id: row.id,
        label: row.full_name,
        sublabel: `${row.class_label} · #${row.student_number}`,
      })),
    );

  const searchProposer = (query: string): Promise<LookupOption[]> =>
    proposerRole === "STUDENT"
      ? searchStudent(query)
      : personnelLookupApi.search(query).then((rows) =>
          rows.map((row) => ({
            id: row.id,
            label: row.full_name,
            sublabel: [row.title, row.branch].filter(Boolean).join(" · "),
          })),
        );

  const submit = async () => {
    if (!student) return setError("Öğrenci seçilmelidir.");
    if (criteria.length === 0) return setError("En az bir kriter seçilmelidir.");
    setBusy(true);
    setError(null);
    try {
      await odulApi.proposeCertificate({
        student_id: student.id,
        school_term_id: schoolTermId,
        proposer_role: proposerRole,
        proposer_name: proposer?.label.trim() ?? "",
        criteria,
        justification: justification.trim(),
      });
      onCreated();
    } catch (e: unknown) {
      setError(e instanceof ApiError ? e.message : "Teklif kaydedilemedi.");
      setBusy(false);
    }
  };

  return (
    <Card elevation={1} className="space-y-4 p-6">
      <p className="text-title-medium text-on-surface">Yeni onur belgesi teklifi</p>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <Select
          label="Teklif eden"
          value={proposerRole}
          onChange={(event) => {
            setProposerRole(event.target.value as HonorProposerRole);
            setProposer(null);
          }}
          options={(Object.entries(HONOR_PROPOSER_ROLE_TR) as [HonorProposerRole, string][]).map(
            ([value, label]) => ({ value, label }),
          )}
        />
        <Autocomplete<LookupOption>
          label="Teklif eden adı"
          selected={proposer}
          onSelect={setProposer}
          onClear={() => setProposer(null)}
          search={searchProposer}
          getKey={(option) => option.id}
          getLabel={(option) => option.label}
          getSublabel={(option) => option.sublabel ?? ""}
          placeholder="Ad ile ara…"
        />
      </div>
      <Autocomplete<LookupOption>
        label="Teklif edilen öğrenci"
        required
        selected={student}
        onSelect={setStudent}
        onClear={() => setStudent(null)}
        search={searchStudent}
        getKey={(option) => option.id}
        getLabel={(option) => option.label}
        getSublabel={(option) => option.sublabel ?? ""}
        placeholder="Öğrenci adı veya numarası…"
      />
      <fieldset className="space-y-2">
        <legend className="text-label-large text-on-surface">Kriterler (md. 161)</legend>
        {CRITERION_OPTIONS.map((option) => (
          <label
            key={option.value}
            className="flex min-h-11 items-start gap-3 rounded-shape-xs px-2 py-2 text-body-medium text-on-surface hover:bg-surface-container"
          >
            <input
              type="checkbox"
              className="mt-0.5 h-5 w-5 accent-primary"
              checked={criteria.includes(option.value)}
              onChange={(event) =>
                setCriteria((current) =>
                  event.target.checked
                    ? [...current, option.value]
                    : current.filter((value) => value !== option.value),
                )
              }
            />
            <span>{option.label}</span>
          </label>
        ))}
      </fieldset>
      <TextField
        label="Somut gerekçe"
        value={justification}
        onChange={(event) => setJustification(event.target.value)}
      />
      {error && <ErrorBanner message={error} />}
      <div className="flex justify-end gap-2">
        <Button variant="text" onClick={onCancel}>
          Vazgeç
        </Button>
        <Button icon="check" onClick={submit} disabled={busy}>
          {busy ? "Kaydediliyor…" : "Teklifi kaydet"}
        </Button>
      </div>
    </Card>
  );
}
