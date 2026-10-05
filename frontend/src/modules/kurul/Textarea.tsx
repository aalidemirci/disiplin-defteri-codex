// M3 outlined çok-satırlı alan (ui/TextField deseni — token tüketir, ham renk yok).
// ToplantiForm'dan ayrıldı (04.10.2026); toplantı ekranındaki karar gerekçesi de kullanır.

import type { TextareaHTMLAttributes } from "react";

export default function Textarea({
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
