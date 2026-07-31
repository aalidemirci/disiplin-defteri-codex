// EK-1 öğrenci-bağlam alanları için "Seçim + Diğer" girişi (Tur 148, Talep 3 Faz B).
//
// Ortak seçenekler tek tıkla; "Diğer…" seçilince serbest metin kutusu açılır. Mevcut
// veya sabit seçeneklerde olmayan değer (eski serbest-metin veri) otomatik "Diğer"de
// gösterilir → veri kaybı yok. Seçilen değer Türkçe etiket olarak doğrudan ilgili
// CharField'a yazılır (backend/migration YOK; EK-1 belgesi metni aynen basar).
//
// ui/Select + ui/TextField (her ikisi M3 outlined, h-14 ≥48px, kendi label/id'si) tüketir.

import { useState } from "react";
import type { ChangeEvent } from "react";

import Select from "../../ui/Select";
import TextField from "../../ui/TextField";

// Sabit seçeneklerle çakışmayan iç "Diğer" değeri (Türkçe etiketlerle çarpışmaz).
const OTHER = "__other__";

export default function SelectOrOther({
  label,
  value,
  options,
  onChange,
  helperText,
}: {
  label: string;
  value: string;
  options: string[];
  onChange: (value: string) => void;
  helperText?: string;
}) {
  // "Diğer" modu: değer dolu ama sabit seçeneklerde değilse (eski serbest metin) ya da
  // kullanıcı "Diğer…"i seçtiyse. Mount değerinden başlatılır — panel açıkken dış
  // değer reset'i yok, bu yüzden tek başlatma yeterli.
  const [otherMode, setOtherMode] = useState(() => value !== "" && !options.includes(value));

  const selectValue = otherMode ? OTHER : options.includes(value) ? value : "";

  const handleSelect = (e: ChangeEvent<HTMLSelectElement>) => {
    const v = e.target.value;
    if (v === OTHER) {
      setOtherMode(true); // değeri koru (eşleşmeyen eski metin "Diğer"e taşınır)
    } else {
      setOtherMode(false);
      onChange(v); // gerçek seçenek veya "" (placeholder → boş)
    }
  };

  return (
    <div className="space-y-2">
      <Select
        label={label}
        placeholder="Seçiniz…"
        value={selectValue}
        onChange={handleSelect}
        options={[
          ...options.map((o) => ({ value: o, label: o })),
          { value: OTHER, label: "Diğer…" },
        ]}
        helperText={otherMode ? undefined : helperText}
      />
      {otherMode && (
        <TextField
          label={`${label} — diğer`}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder="Belirtiniz…"
          helperText={helperText}
        />
      )}
    </div>
  );
}
