// Kurul sayfalarında etkin sekme `?sekme=` ile adres çubuğunda tutulur: derin bağlantı
// (Panel kartı, yıl devri, Gündem → açılan toplantı) ve geri tuşu sekmeyi korur.

import { useSearchParams } from "react-router-dom";

export default function useSekme(keys: readonly string[]): [string, (key: string) => void] {
  const [params, setParams] = useSearchParams();
  const raw = params.get("sekme") ?? "";
  const active = keys.includes(raw) ? raw : keys[0];
  // Sekme değişince sekmeye özgü parametreler (açık toplantı) düşer.
  const setActive = (key: string) => setParams({ sekme: key });
  return [active, setActive];
}
