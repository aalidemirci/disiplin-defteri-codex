// Disiplin kurulu sayfası (Tur 70/Faz 4; Tur 212'de sekmeli) — iki sekme:
//   "Kurul Üyeleri": ders yılı başına bir "Okul Öğrenci Ödül ve Disiplin Kurulu"
//   tanımı — başkan müdür yardımcısı (md. 185/188), asıl/yedek üyeler
//   öğretmen/öğrenci/veli (md. 185-186).
//   "Toplantı Tutanakları": karar defteri (md. 184/206) — dosya görüşme tutanağı dahil.
//
// OYS `modules/disiplin/DisiplinKuruluPage.tsx`'ten UYARLANDI (F4-D2). Sapmalar: auth yok
// (rol kapıları/kilit kartları kalktı, hepsi-yetkili koşulsuz render); ders yılları
// `okul` modülünden (okulApi.listSchoolYears DÜZ dizi döner); kişi seçimi
// personnelLookupApi/studentLookupApi (studentLookup düz dizi, `.results` yok); VELİ üye
// FK'sız `member_name` snapshot'ı ile eklenir; addCommitteeMember kurulun TAMAMINI döner
// — üye listesi dönüşle tazelenir (yeniden yükleme yok).

import { useCallback, useEffect, useId, useState } from "react";
import { Link } from "react-router-dom";

import { ApiError } from "../../lib/api";
import Tabs, { tabPanelProps } from "../../ui/Tabs";
import type { TabItem } from "../../ui/Tabs";
import TutanakListesi from "../kurul/TutanakListesi";
import { okulApi } from "../okul/api";
import Autocomplete from "../../ui/Autocomplete";
import Button from "../../ui/Button";
import Card from "../../ui/Card";
import Icon from "../../ui/Icon";
import { SkeletonList } from "../../ui/Skeleton";
import Select from "../../ui/Select";
import { useConfirm } from "../../ui/ConfirmProvider";
import { useSnackbar } from "../../ui/SnackbarProvider";
import TextField from "../../ui/TextField";
import { COMMITTEE_MEMBER_TYPE_TR, disiplinApi, personnelLookupApi, studentLookupApi } from "./api";
import type {
  CommitteeMember,
  CommitteeMemberType,
  DisciplineCommittee,
  PersonnelSearchRow,
} from "./api";

export default function DisiplinKuruluPage() {
  const [committee, setCommittee] = useState<DisciplineCommittee | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  // Authsuz masaüstünde rol kapısı yok — varsayılan sekme daima üyeler.
  const [active, setActive] = useState("uyeler");

  const tabs: TabItem[] = [
    { key: "uyeler", label: "Kurul Üyeleri", icon: "groups" },
    { key: "tutanaklar", label: "Toplantı Tutanakları", icon: "menu_book" },
  ];

  const load = useCallback(() => {
    setLoading(true);
    disiplinApi
      .getCommittee()
      .then((r) => {
        setCommittee(r.committee);
        setError(null);
      })
      .catch((e: unknown) => setError(e instanceof ApiError ? e.message : "Kurul yüklenemedi."))
      .finally(() => setLoading(false));
  }, []);
  useEffect(load, [load]);

  return (
    <div className="space-y-6">
      <Breadcrumb />
      <div className="dd-page-header">
        <div>
          <h1 className="dd-page-title">Disiplin Kurulu</h1>
          <p className="dd-page-description">
            Aktif ders yılı için Okul Öğrenci Ödül ve Disiplin Kurulu. Başkan, müdürün
            görevlendirdiği müdür yardımcısıdır (md. 188); asıl ve yedek üyeler öğretmen, öğrenci ve
            veliden oluşur (md. 185-186).
          </p>
        </div>
      </div>

      <Tabs
        items={tabs}
        active={active}
        onChange={setActive}
        ariaLabel="Disiplin Kurulu bölümleri"
        idBase="disiplin-kurul"
      />

      <div {...tabPanelProps("disiplin-kurul", active)}>
        {active === "uyeler" && (
          <div className="space-y-6">
            {error && (
              <div className="flex items-start gap-2 rounded-shape-sm bg-error-container px-4 py-3 text-body-medium text-on-error-container">
                <Icon name="error" size="lg" />
                <span>{error}</span>
              </div>
            )}

            {loading ? (
              <SkeletonList rows={4} />
            ) : committee === null ? (
              <CommitteeCreateCard onCreated={(c) => setCommittee(c)} />
            ) : (
              <>
                <ChairCard committee={committee} onChanged={(c) => setCommittee(c)} />
                <MembersCard
                  committee={committee}
                  onChanged={load}
                  onCommittee={(c) => setCommittee(c)}
                />
              </>
            )}
          </div>
        )}
        {active === "tutanaklar" && <TutanakListesi councilType="DISCIPLINE" />}
      </div>
    </div>
  );
}

function Breadcrumb() {
  return (
    <div className="flex items-center gap-2 text-label-large text-on-surface-variant">
      <Link to="/disiplin" className="hover:text-on-surface">
        ← Disiplin
      </Link>
      <span>/</span>
      <span className="text-on-surface">Disiplin Kurulu</span>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Kurul oluşturma (kurul henüz yoksa)
// ---------------------------------------------------------------------------

function CommitteeCreateCard({ onCreated }: { onCreated: (c: DisciplineCommittee) => void }) {
  const [chair, setChair] = useState<PersonnelSearchRow | null>(null);
  const [notes, setNotes] = useState("");
  const fieldIdBase = useId();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const snackbar = useSnackbar();

  const onSubmit = async () => {
    if (!chair) {
      setError("Başkan (müdür yardımcısı) seçilmelidir.");
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
      const created = await disiplinApi.createCommittee({
        school_year_id: active.id,
        chair_id: chair.id,
        notes: notes.trim(),
      });
      snackbar.success("Disiplin kurulu oluşturuldu.");
      onCreated(created);
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err.message
          : err instanceof Error
            ? err.message
            : "Kurul oluşturulamadı.",
      );
      setBusy(false);
    }
  };

  return (
    <Card elevation={1} className="p-6">
      <p className="text-title-medium text-on-surface">Kurul oluştur</p>
      <p className="mt-1 text-body-medium text-on-surface-variant">
        Aktif ders yılı için yeni bir disiplin kurulu tanımlanır. Önce başkanı seçin; üyeler
        oluşturulduktan sonra eklenir.
      </p>
      <div className="mt-4 space-y-4">
        <Autocomplete<PersonnelSearchRow>
          label="Kurul başkanı (müdür yardımcısı)"
          required
          selected={chair}
          onSelect={setChair}
          onClear={() => setChair(null)}
          search={(q) => personnelLookupApi.search(q)}
          getKey={(u) => u.id}
          getLabel={(u) => u.full_name}
          getSublabel={(u) => `${u.title || "—"} · ${u.branch || "—"}`}
          placeholder="Müdür yardımcısı adı…"
          helperText="Md. 188: başkan, müdürün görevlendirdiği müdür yardımcısıdır."
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
            className="block w-full rounded-shape-xs border border-outline bg-surface px-4 py-3 text-body-medium text-on-surface outline-none focus-visible:ring-2 focus-visible:ring-primary focus:border-primary"
          />
        </div>
        {error && (
          <div className="flex items-start gap-2 rounded-shape-sm bg-error-container px-4 py-2 text-body-small text-on-error-container">
            <Icon name="error" size="sm" />
            <span>{error}</span>
          </div>
        )}
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
// Başkan kartı + değiştirme
// ---------------------------------------------------------------------------

function ChairCard({
  committee,
  onChanged,
}: {
  committee: DisciplineCommittee;
  onChanged: (c: DisciplineCommittee) => void;
}) {
  const [editing, setEditing] = useState(false);
  const [chair, setChair] = useState<PersonnelSearchRow | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const snackbar = useSnackbar();

  const save = async () => {
    if (!chair) return;
    setBusy(true);
    setError(null);
    try {
      const updated = await disiplinApi.setCommitteeChair({ chair_id: chair.id });
      snackbar.success("Kurul başkanı güncellendi.");
      onChanged(updated);
      setEditing(false);
      setChair(null);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Başkan güncellenemedi.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card elevation={1} className="p-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <p className="text-label-large text-on-surface-variant">Kurul başkanı</p>
          <p className="mt-1 flex items-center gap-2 text-title-medium text-on-surface">
            <Icon name="shield_person" className="text-primary" />
            {committee.chair_name || "—"}
          </p>
        </div>
        {!editing && (
          <Button variant="text" icon="edit" onClick={() => setEditing(true)}>
            Başkanı değiştir
          </Button>
        )}
      </div>

      {editing && (
        <div className="mt-4 space-y-3 rounded-shape-md bg-surface-container-low p-4">
          <Autocomplete<PersonnelSearchRow>
            label="Yeni başkan (müdür yardımcısı)"
            required
            selected={chair}
            onSelect={setChair}
            onClear={() => setChair(null)}
            search={(q) => personnelLookupApi.search(q)}
            getKey={(u) => u.id}
            getLabel={(u) => u.full_name}
            getSublabel={(u) => `${u.title || "—"} · ${u.branch || "—"}`}
            placeholder="Müdür yardımcısı adı…"
          />
          {error && (
            <div className="flex items-start gap-2 rounded-shape-sm bg-error-container px-4 py-2 text-body-small text-on-error-container">
              <Icon name="error" size="sm" />
              <span>{error}</span>
            </div>
          )}
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
    </Card>
  );
}

// ---------------------------------------------------------------------------
// Üyeler kartı (asıl/yedek) + ekleme/çıkarma
// ---------------------------------------------------------------------------

const MEMBER_TYPE_CHIP: Record<CommitteeMemberType, string> = {
  TEACHER: "bg-primary-container text-on-primary-container",
  STUDENT: "bg-tertiary-container text-on-tertiary-container",
  PARENT: "bg-secondary-container text-on-secondary-container",
};

function MembersCard({
  committee,
  onChanged,
  onCommittee,
}: {
  committee: DisciplineCommittee;
  onChanged: () => void;
  onCommittee: (c: DisciplineCommittee) => void;
}) {
  const [adding, setAdding] = useState(false);
  const principals = committee.members
    .filter((m) => !m.is_substitute)
    .sort((a, b) => a.order - b.order);
  const substitutes = committee.members
    .filter((m) => m.is_substitute)
    .sort((a, b) => a.order - b.order);

  return (
    <Card elevation={1} className="p-6">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-title-medium text-on-surface">Üyeler ({committee.members.length})</p>
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
            onAdded={(c) => {
              setAdding(false);
              // Üye ekleme güncel kurulun tamamını döner — state dönüşle tazelenir.
              onCommittee(c);
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
  members: CommitteeMember[];
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

function MemberRow({ member: m, onRemoved }: { member: CommitteeMember; onRemoved: () => void }) {
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const snackbar = useSnackbar();
  const confirm = useConfirm();

  const remove = async () => {
    if (
      !(await confirm({
        message: `'${m.member_name}' kuruldan çıkarılsın mı?`,
        confirmLabel: "Çıkar",
      }))
    )
      return;
    setBusy(true);
    setErr(null);
    try {
      await disiplinApi.removeCommitteeMember(m.id);
      snackbar.success("Üye kuruldan çıkarıldı.");
      onRemoved();
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : "Çıkarılamadı.");
      setBusy(false);
    }
  };

  return (
    <li className="flex flex-wrap items-center justify-between gap-3 py-3">
      <div className="min-w-0">
        <p className="flex items-center gap-2 text-body-medium text-on-surface">
          <span
            className={`inline-flex items-center rounded-shape-xl px-2 py-0.5 text-label-small ${MEMBER_TYPE_CHIP[m.member_type]}`}
          >
            {COMMITTEE_MEMBER_TYPE_TR[m.member_type]}
          </span>
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
// Üye ekleme formu — tipe göre kişi seçici; VELİ için FK yok, ad snapshot'ı
// ---------------------------------------------------------------------------

interface PersonOption {
  id: number;
  label: string;
  sublabel?: string;
}

function AddMemberForm({
  onCancel,
  onAdded,
}: {
  onCancel: () => void;
  onAdded: (c: DisciplineCommittee) => void;
}) {
  const [memberType, setMemberType] = useState<CommitteeMemberType>("TEACHER");
  const [person, setPerson] = useState<PersonOption | null>(null);
  // VELİ üye: veli sicili tutulmaz — ad-soyad snapshot'ı (member_name) yeterli.
  const [parentName, setParentName] = useState("");
  const [isSubstitute, setIsSubstitute] = useState(false);
  const [order, setOrder] = useState("0");
  const [title, setTitle] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const snackbar = useSnackbar();

  // Tipe göre arama fonksiyonu (her biri PersonOption[] döndürür). VELİ'de seçici yok.
  const searchPerson = (q: string): Promise<PersonOption[]> => {
    if (memberType === "TEACHER") {
      return personnelLookupApi.search(q).then((rows) =>
        rows.map((u) => ({
          id: u.id,
          label: u.full_name,
          sublabel: `${u.title || "—"} · ${u.branch || "—"}`,
        })),
      );
    }
    // STUDENT — lookup düz dizi döner (`.results` yok).
    return studentLookupApi.search(q).then((rows) =>
      rows.map((s) => ({
        id: s.id,
        label: s.full_name,
        sublabel: `${s.class_label} · #${s.student_number}`,
      })),
    );
  };

  const submit = async () => {
    const trimmedParentName = parentName.trim();
    if (memberType === "PARENT" && !trimmedParentName) {
      setError("Veli adı soyadı yazılmalıdır.");
      return;
    }
    if (memberType !== "PARENT" && !person) {
      setError("Bir kişi seçilmelidir.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      // Dönen değer güncel kurulun TAMAMI — üst bileşen state'i bununla tazeler.
      const updated = await disiplinApi.addCommitteeMember({
        member_type: memberType,
        ...(memberType === "PARENT"
          ? { member_name: trimmedParentName }
          : { person_id: person?.id ?? null }),
        is_substitute: isSubstitute,
        order: Number(order) || 0,
        title: title.trim(),
      });
      snackbar.success("Üye eklendi.");
      onAdded(updated);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Üye eklenemedi.");
      setBusy(false);
    }
  };

  return (
    <div className="space-y-4 rounded-shape-md bg-surface-container-low p-4">
      <p className="text-title-medium text-on-surface">Yeni üye</p>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <Select
          label="Üye tipi"
          value={memberType}
          onChange={(e) => {
            setMemberType(e.target.value as CommitteeMemberType);
            setPerson(null); // tip değişince kişi sıfırla (lookup farklı)
            setParentName("");
          }}
          options={(
            Object.entries(COMMITTEE_MEMBER_TYPE_TR) as [CommitteeMemberType, string][]
          ).map(([value, label]) => ({ value, label }))}
        />
        <TextField
          label="Sıra"
          type="number"
          min={0}
          value={order}
          onChange={(e) => setOrder(e.target.value)}
          helperText="Aynı tip içinde gösterim sırası."
        />
      </div>

      {memberType === "PARENT" ? (
        // VELİ: FK yok — ad snapshot'ı serbest metin girilir (veli sicili tutulmaz).
        <TextField
          label="Veli adı soyadı"
          required
          value={parentName}
          onChange={(e) => setParentName(e.target.value)}
          placeholder="Veli adı soyadı…"
          helperText="Veli sicili tutulmaz; ad-soyad kayda olduğu gibi yazılır."
        />
      ) : (
        // Tipe göre kişi seçici — key tip değişince Autocomplete'i sıfırlar
        <Autocomplete<PersonOption>
          key={memberType}
          label={`${COMMITTEE_MEMBER_TYPE_TR[memberType]} seç`}
          required
          selected={person}
          onSelect={setPerson}
          onClear={() => setPerson(null)}
          search={searchPerson}
          getKey={(p) => p.id}
          getLabel={(p) => p.label}
          getSublabel={(p) => p.sublabel ?? ""}
          placeholder={`${COMMITTEE_MEMBER_TYPE_TR[memberType]} adı…`}
          helperText="Listeden seçim yapın (yanlış yazımdan ilişkisiz kayıt önlenir)."
        />
      )}

      <TextField
        label="Ünvan / görev (opsiyonel)"
        value={title}
        onChange={(e) => setTitle(e.target.value)}
        helperText="Örn. Zümre başkanı, okul aile birliği temsilcisi."
      />

      <label className="flex min-h-12 items-center gap-3 text-body-medium text-on-surface">
        <input
          type="checkbox"
          checked={isSubstitute}
          onChange={(e) => setIsSubstitute(e.target.checked)}
          className="h-5 w-5 accent-primary"
        />
        Yedek üye
      </label>

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
          disabled={busy || (memberType === "PARENT" ? !parentName.trim() : !person)}
        >
          {busy ? "Ekleniyor…" : "Üyeyi ekle"}
        </Button>
      </div>
    </div>
  );
}
