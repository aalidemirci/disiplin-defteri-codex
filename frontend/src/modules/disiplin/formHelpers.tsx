// Disiplin detay bölümlerinde paylaşılan küçük form yardımcıları (Tur 80).
// DecisionsSection + PeriodsSection genişleyen panel (onay/tebliğ/uzatma/tedbir)
// formlarında aynı kabuk/eylem/hata bloğunu kullanır — M3 token'lı, tekrar yok.

import type { ReactNode } from "react";

import { ApiError } from "../../lib/api";
import Button from "../../ui/Button";
import Icon from "../../ui/Icon";

// Genişleyen panel kabuğu (başlık + ikon + içerik), surface-container üstünde.
export function PanelShell({
  title,
  icon,
  children,
}: {
  title: string;
  icon: string;
  children: ReactNode;
}) {
  return (
    <div className="mt-3 space-y-3 rounded-shape-sm bg-surface-container px-4 py-3">
      <p className="flex items-center gap-2 text-title-small text-on-surface">
        <Icon name={icon} size="base" className="text-primary" />
        {title}
      </p>
      {children}
    </div>
  );
}

// Panel alt eylem çubuğu — Vazgeç/Kapat + Kaydet (busy'de devre dışı).
// `cancelLabel` oto-kayıtlı formlarda "Kapat" olur (Vazgeç artık veriyi geri almaz).
export function PanelActions({
  busy,
  onCancel,
  onSubmit,
  submitLabel = "Kaydet",
  cancelLabel = "Vazgeç",
}: {
  busy: boolean;
  onCancel: () => void;
  onSubmit: () => void;
  submitLabel?: string;
  cancelLabel?: string;
}) {
  return (
    <div className="flex justify-end gap-2">
      <Button type="button" variant="text" onClick={onCancel}>
        {cancelLabel}
      </Button>
      <Button type="button" icon="check" onClick={onSubmit} disabled={busy}>
        {busy ? "Kaydediliyor…" : submitLabel}
      </Button>
    </div>
  );
}

// Standart hata kutusu (error-container) — null'da render yok.
export function FormError({ error }: { error: string | null }) {
  if (!error) return null;
  return (
    <div className="flex items-start gap-2 rounded-shape-sm bg-error-container px-4 py-2 text-body-small text-on-error-container">
      <Icon name="error" size="sm" />
      <span>{error}</span>
    </div>
  );
}

// ApiError / Error mesajını çöz, aksi halde fallback.
export function asMessage(err: unknown, fallback: string): string {
  if (err instanceof ApiError) return err.message;
  if (err instanceof Error) return err.message;
  return fallback;
}
