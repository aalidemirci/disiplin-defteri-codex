import { useCallback, useEffect, useState } from "react";

import { ApiError } from "../../lib/api";
import { formatDate, todayIso } from "../../lib/format";
import Autocomplete from "../../ui/Autocomplete";
import Button from "../../ui/Button";
import Card from "../../ui/Card";
import Icon from "../../ui/Icon";
import Select from "../../ui/Select";
import { SkeletonList } from "../../ui/Skeleton";
import { useConfirm } from "../../ui/ConfirmProvider";
import { useSnackbar } from "../../ui/SnackbarProvider";
import TextField from "../../ui/TextField";
import { studentLookupApi } from "../disiplin/api";
import { okulApi } from "../okul/api";
import { odulApi } from "./api";
import type { HonorCompliance, HonorGeneralAssemblyMember } from "./api";

interface StudentOption {
  id: number;
  label: string;
  sublabel: string;
}

export default function OnurGenelKuruluPanel() {
  const snackbar = useSnackbar();
  const confirm = useConfirm();
  const [members, setMembers] = useState<HonorGeneralAssemblyMember[]>([]);
  const [compliance, setCompliance] = useState<HonorCompliance | null>(null);
  const [student, setStudent] = useState<StudentOption | null>(null);
  const [effectiveFrom, setEffectiveFrom] = useState(todayIso());
  const [replacedMember, setReplacedMember] = useState("");
  const [secondTermStart, setSecondTermStart] = useState("");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const years = await okulApi.listSchoolYears();
      const active = years.find((year) => year.is_active);
      if (!active) throw new Error("Aktif ders yılı bulunamadı.");
      const [memberRows, complianceRow, terms] = await Promise.all([
        odulApi.listGeneralAssemblyMembers(active.id),
        odulApi.getHonorCompliance(active.id),
        okulApi.listSchoolTerms(active.id),
      ]);
      setMembers(memberRows);
      setCompliance(complianceRow);
      setSecondTermStart(terms.find((term) => term.sequence === 2)?.start_date ?? "");
      setEffectiveFrom(active.start_date);
      setError(null);
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err.message
          : err instanceof Error
            ? err.message
            : "Onur Genel Kurulu bilgileri yüklenemedi.",
      );
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const searchStudent = (query: string): Promise<StudentOption[]> =>
    studentLookupApi.search(query).then((rows) =>
      rows.map((row) => ({
        id: row.id,
        label: row.full_name,
        sublabel: `${row.class_label} · #${row.student_number}`,
      })),
    );

  const addMember = async () => {
    if (!student) {
      setError("Temsilci öğrenci seçilmelidir.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await odulApi.addGeneralAssemblyMember({
        student_id: student.id,
        effective_from: effectiveFrom,
        replaced_member_id: replacedMember ? Number(replacedMember) : null,
      });
      snackbar.success(
        replacedMember ? "Temsilci değişikliği kaydedildi." : "Genel kurul temsilcisi eklendi.",
      );
      setStudent(null);
      setReplacedMember("");
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Temsilci kaydedilemedi.");
    } finally {
      setBusy(false);
    }
  };

  const endMember = async (member: HonorGeneralAssemblyMember) => {
    const approved = await confirm({
      title: "Temsilcilik görevini sonlandır",
      message: `${member.member_name} adlı öğrencinin temsilcilik görevi sona erdirilsin mi? Kayıt geçmişte korunur.`,
      confirmLabel: "Görevi sonlandır",
    });
    if (!approved) return;
    setBusy(true);
    try {
      await odulApi.endGeneralAssemblyMember(member.id, {
        effective_until: todayIso(),
        reason: "Görev değişikliği",
      });
      snackbar.success("Temsilcilik görevi sonlandırıldı.");
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Görev sonlandırılamadı.");
    } finally {
      setBusy(false);
    }
  };

  const activeMembers = members.filter((member) => member.is_active);
  const pastMembers = members.filter((member) => !member.is_active);

  return (
    <div className="space-y-6">
      <Card elevation={1} className="p-6">
        <div className="flex items-start gap-3">
          <Icon name="groups" className="text-primary" />
          <div>
            <p className="text-title-medium text-on-surface">Onur Genel Kurulu</p>
            <p className="mt-1 text-body-medium text-on-surface-variant">
              Kurul ders yılı için oluşturulur; her şubenin seçilmiş temsilcisi kaydedilir. Temsilci
              değişiklikleri başlangıç ve bitiş tarihleriyle geçmişi silmeden izlenir.
            </p>
          </div>
        </div>
      </Card>

      {error && (
        <div
          role="alert"
          className="rounded-shape-sm bg-error-container px-4 py-3 text-on-error-container"
        >
          {error}
        </div>
      )}

      {loading ? (
        <SkeletonList rows={5} />
      ) : (
        <>
          <ComplianceCard compliance={compliance} />

          <Card elevation={1} className="space-y-4 p-6">
            <p className="text-title-medium text-on-surface">Şube temsilcisi ekle veya değiştir</p>
            <Autocomplete<StudentOption>
              label="Temsilci öğrenci"
              required
              selected={student}
              onSelect={setStudent}
              onClear={() => setStudent(null)}
              search={searchStudent}
              getKey={(item) => item.id}
              getLabel={(item) => item.label}
              getSublabel={(item) => item.sublabel}
              placeholder="Öğrenci adı veya numarası…"
            />
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              <TextField
                label="Görev başlangıcı"
                type="date"
                required
                value={effectiveFrom}
                onChange={(event) => setEffectiveFrom(event.target.value)}
              />
              <Select
                label="Yerine seçildiği temsilci"
                value={replacedMember}
                onChange={(event) => {
                  setReplacedMember(event.target.value);
                  if (event.target.value && secondTermStart) setEffectiveFrom(secondTermStart);
                }}
                placeholder="Yeni temsilci"
                options={activeMembers.map((member) => ({
                  value: String(member.id),
                  label: `${member.class_level}/${member.class_section} · ${member.member_name}`,
                }))}
                helperText="Aynı şubede değişiklik yapılıyorsa önceki temsilciyi seçin."
              />
            </div>
            <div className="flex justify-end">
              <Button onClick={() => void addMember()} disabled={busy || !effectiveFrom}>
                {busy ? "Kaydediliyor…" : "Temsilciyi kaydet"}
              </Button>
            </div>
          </Card>

          <Card elevation={1} className="p-6">
            <p className="text-title-medium text-on-surface">Aktif şube temsilcileri</p>
            {activeMembers.length === 0 ? (
              <p className="mt-3 text-body-medium text-on-surface-variant">
                Henüz temsilci kaydedilmemiş.
              </p>
            ) : (
              <ul className="mt-3 divide-y divide-outline-variant/50">
                {activeMembers.map((member) => (
                  <li
                    key={member.id}
                    className="flex flex-wrap items-center justify-between gap-3 py-3"
                  >
                    <div>
                      <p className="text-body-medium text-on-surface">{member.member_name}</p>
                      <p className="text-label-small text-on-surface-variant">
                        {member.class_level}/{member.class_section} ·{" "}
                        {formatDate(member.effective_from)}
                      </p>
                    </div>
                    <Button variant="text" onClick={() => void endMember(member)} disabled={busy}>
                      Görevi sonlandır
                    </Button>
                  </li>
                ))}
              </ul>
            )}
          </Card>

          {pastMembers.length > 0 && (
            <Card elevation={1} className="p-6">
              <p className="text-title-medium text-on-surface">Temsilcilik geçmişi</p>
              <ul className="mt-3 divide-y divide-outline-variant/50">
                {pastMembers.map((member) => (
                  <li key={member.id} className="py-3 text-body-medium text-on-surface">
                    {member.class_level}/{member.class_section} · {member.member_name}
                    <span className="ml-2 text-label-small text-on-surface-variant">
                      {formatDate(member.effective_from)} –{" "}
                      {member.effective_until ? formatDate(member.effective_until) : ""}
                      {member.end_reason ? ` · ${member.end_reason}` : ""}
                    </span>
                  </li>
                ))}
              </ul>
            </Card>
          )}
        </>
      )}
    </div>
  );
}

function ComplianceCard({ compliance }: { compliance: HonorCompliance | null }) {
  if (!compliance?.configured) {
    return (
      <Card elevation={1} className="flex items-start gap-3 p-5">
        <Icon name="warning" className="text-error" />
        <p className="text-body-medium text-on-surface">
          Aktif ders yılının iki dönem takvimi tanımlı değil. Toplantı uygunluğu izlenemez.
        </p>
      </Card>
    );
  }
  return (
    <Card elevation={1} className="p-6">
      <p className="text-title-medium text-on-surface">Toplantı uygunluğu</p>
      <div className="mt-4 grid grid-cols-1 gap-4 lg:grid-cols-2">
        {compliance.terms.map((term) => (
          <div key={term.term_id} className="rounded-shape-sm border border-outline-variant p-4">
            <p className="font-medium text-on-surface">{term.name}</p>
            <p className={term.assembly_complete ? "text-primary" : "text-error"}>
              Genel kurul: {term.assembly_complete ? "toplantı kaydı var" : "toplantı kaydı eksik"}
            </p>
            <div className="mt-2 flex flex-wrap gap-2">
              {term.months.map((month) => (
                <span
                  key={`${month.year}-${month.month}`}
                  className={`rounded-shape-xl px-2 py-1 text-label-small ${
                    month.complete
                      ? "bg-primary-container text-on-primary-container"
                      : "bg-error-container text-on-error-container"
                  }`}
                >
                  {month.label}
                </span>
              ))}
            </div>
          </div>
        ))}
      </div>
    </Card>
  );
}
