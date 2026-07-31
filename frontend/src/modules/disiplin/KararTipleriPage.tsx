// OYS `modules/disiplin/KararTipleriPage.tsx`'ten UYARLANDI (F4-D2); sapmalar:
// auth yok — OYS'deki "yalnızca ADMIN" notu kalktı (tek kullanıcılı masaüstünde
// operatör tam yetkili), geri kalanı bire bir.
// Disiplin kurul karar tipleri yönetimi.
// V1'de fixture YOK — operatör gerçek karar tiplerini (kınama, kısa süreli
// uzaklaştırma vb.) buradan ekler. Kod değişikliği gerekmez.

import { useEffect, useId, useState } from "react";
import type { FormEvent } from "react";
import { Link } from "react-router-dom";

import { ApiError } from "../../lib/api";
import Button from "../../ui/Button";
import Card from "../../ui/Card";
import Icon from "../../ui/Icon";
import { SkeletonList } from "../../ui/Skeleton";
import { useSnackbar } from "../../ui/SnackbarProvider";
import TextField from "../../ui/TextField";
import { disiplinApi } from "./api";
import type { DecisionTypeCreateBody, DisciplineDecisionType } from "./api";

export default function KararTipleriPage() {
  const [items, setItems] = useState<DisciplineDecisionType[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [editingId, setEditingId] = useState<number | null>(null);

  const load = () => {
    setLoading(true);
    disiplinApi
      // Yönetim ekranı pasifleri de görmeli: aksi hâlde pasifleştirilen tip
      // listeden düşer ve "Aktif" kutusu işaretlenerek geri açılamaz.
      .listDecisionTypes({ includeInactive: true })
      .then((r) => {
        setItems(r);
        setError(null);
      })
      .catch((e: unknown) =>
        setError(e instanceof ApiError ? e.message : "Karar tipleri yüklenemedi."),
      )
      .finally(() => setLoading(false));
  };
  useEffect(load, []);

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-2 text-label-large text-on-surface-variant">
        <Link to="/disiplin" className="hover:text-on-surface">
          ← Disiplin
        </Link>
        <span>/</span>
        <span className="text-on-surface">Karar tipleri</span>
      </div>

      <div className="dd-page-header">
        <div>
          <h1 className="dd-page-title">Karar tipleri</h1>
          <p className="dd-page-description">
            Dosya detayında "Kurul kararı tamamlandı" aşaması işlenirken seçilen{" "}
            <strong>olay etiketi</strong> listesi (örn. "Disiplin Dosyası Kararı"). Resmî ceza
            kararının kendisi (kınama, uzaklaştırma vb.) burada değil, dosyanın Kararlar bölümünde
            kanunla sabit türlerle kaydedilir. Pasifleştirilen tipler yeni kayıtlarda görünmez ama
            mevcut kayıtlar korunur (silinmez).
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          {!creating && (
            <Button icon="add" onClick={() => setCreating(true)}>
              Yeni tip
            </Button>
          )}
          <Button variant="text" icon="refresh" onClick={load}>
            Yenile
          </Button>
        </div>
      </div>

      {creating && (
        <DecisionTypeForm
          onCancel={() => setCreating(false)}
          onSaved={(t) => {
            setItems((prev) => [...prev, t].sort(byOrder));
            setCreating(false);
          }}
        />
      )}

      {error && (
        <div className="flex items-start gap-2 rounded-shape-sm bg-error-container px-4 py-3 text-body-medium text-on-error-container">
          <Icon name="error" size="lg" />
          <span>{error}</span>
        </div>
      )}

      {loading ? (
        <SkeletonList rows={4} />
      ) : items.length === 0 ? (
        <Card elevation={1} className="p-6">
          <p className="text-body-medium text-on-surface-variant">
            Henüz karar tipi tanımlanmadı. "Yeni tip" ile başlayın.
          </p>
        </Card>
      ) : (
        <Card elevation={1} className="overflow-x-auto p-2">
          <table className="w-full text-body-small">
            <thead className="text-left text-on-surface-variant">
              <tr>
                <th className="px-3 py-2 font-medium">Sıra</th>
                <th className="px-3 py-2 font-medium">Kod</th>
                <th className="px-3 py-2 font-medium">Ad</th>
                <th className="px-3 py-2 font-medium">Açıklama</th>
                <th className="px-3 py-2 font-medium">Durum</th>
                <th className="px-3 py-2 font-medium"></th>
              </tr>
            </thead>
            <tbody>
              {items.map((t) =>
                editingId === t.id ? (
                  <tr
                    key={t.id}
                    className="border-t border-outline-variant/50 bg-surface-container-low"
                  >
                    <td colSpan={6} className="p-3">
                      <DecisionTypeForm
                        initial={t}
                        onCancel={() => setEditingId(null)}
                        onSaved={(updated) => {
                          setItems((prev) =>
                            prev.map((x) => (x.id === updated.id ? updated : x)).sort(byOrder),
                          );
                          setEditingId(null);
                        }}
                      />
                    </td>
                  </tr>
                ) : (
                  <tr
                    key={t.id}
                    className="border-t border-outline-variant/50 transition-colors hover:bg-on-surface/8"
                  >
                    <td className="px-3 py-2 text-on-surface-variant">{t.sort_order}</td>
                    <td className="px-3 py-2 font-mono text-on-surface-variant">{t.code}</td>
                    <td className="px-3 py-2 text-on-surface">{t.name}</td>
                    <td className="px-3 py-2 text-on-surface-variant">{t.description || "—"}</td>
                    <td className="px-3 py-2">
                      {t.is_active ? (
                        <span className="text-primary">Aktif</span>
                      ) : (
                        <span className="text-on-surface-variant">Pasif</span>
                      )}
                    </td>
                    <td className="px-3 py-2 text-right">
                      <Button variant="text" icon="edit" onClick={() => setEditingId(t.id)}>
                        Düzenle
                      </Button>
                    </td>
                  </tr>
                ),
              )}
            </tbody>
          </table>
        </Card>
      )}
    </div>
  );
}

function byOrder(a: DisciplineDecisionType, b: DisciplineDecisionType): number {
  return a.sort_order - b.sort_order || a.name.localeCompare(b.name, "tr");
}

function DecisionTypeForm({
  initial,
  onSaved,
  onCancel,
}: {
  initial?: DisciplineDecisionType;
  onSaved: (t: DisciplineDecisionType) => void;
  onCancel: () => void;
}) {
  const [code, setCode] = useState(initial?.code ?? "");
  const [name, setName] = useState(initial?.name ?? "");
  const [description, setDescription] = useState(initial?.description ?? "");
  const [isActive, setIsActive] = useState(initial?.is_active ?? true);
  const [sortOrder, setSortOrder] = useState(String(initial?.sort_order ?? 0));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const snackbar = useSnackbar();
  const fieldIdBase = useId();

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const body: DecisionTypeCreateBody = {
        code: code.trim(),
        name: name.trim(),
        description: description.trim(),
        is_active: isActive,
        sort_order: Number(sortOrder) || 0,
      };
      const saved = initial
        ? await disiplinApi.patchDecisionType(initial.id, body)
        : await disiplinApi.createDecisionType(body);
      snackbar.success(initial ? "Karar tipi güncellendi." : "Karar tipi eklendi.");
      onSaved(saved);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Kaydedilemedi.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card elevation={1} className="p-6">
      <p className="text-title-medium text-on-surface">
        {initial ? "Karar tipini düzenle" : "Yeni karar tipi"}
      </p>
      <form onSubmit={onSubmit} className="mt-3 space-y-3">
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <TextField
            label="Kod"
            required
            value={code}
            onChange={(e) => setCode(e.target.value)}
            helperText="Örn. KINAMA, KISA_UZAKLASTIRMA"
            disabled={!!initial}
          />
          <TextField
            label="Sıra"
            type="number"
            min={0}
            value={sortOrder}
            onChange={(e) => setSortOrder(e.target.value)}
          />
        </div>
        <TextField label="Ad" required value={name} onChange={(e) => setName(e.target.value)} />
        <div>
          <label
            htmlFor={fieldIdBase}
            className="mb-1 block text-label-large text-on-surface-variant"
          >
            Açıklama (opsiyonel)
          </label>
          <textarea
            id={fieldIdBase}
            rows={2}
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            className="block min-h-12 w-full rounded-shape-xs border border-outline bg-surface px-4 py-3 text-body-medium text-on-surface outline-none focus-visible:ring-2 focus-visible:ring-primary focus:border-primary"
          />
        </div>
        <label className="flex min-h-12 items-center gap-3 text-body-medium text-on-surface">
          <input
            type="checkbox"
            checked={isActive}
            onChange={(e) => setIsActive(e.target.checked)}
            className="h-5 w-5 accent-primary"
          />
          Aktif (yeni dosyalarda seçilebilir)
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
          <Button type="submit" icon="check" disabled={busy || !code.trim() || !name.trim()}>
            {busy ? "Kaydediliyor…" : "Kaydet"}
          </Button>
        </div>
      </form>
    </Card>
  );
}
