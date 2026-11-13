// "Geri yükleme hazır" uyarısı — HER ekranda görünür (AppShell).
//
// Yedek hazırlandıktan sonra program yeniden açılana dek kullanıcı çalışmayı
// sürdürebilir; o arada girdiği kayıtlar geri yüklemeyle birlikte kaybolur. Bunu
// yalnız Güvenlik kartında söylemek yetmez: kullanıcı başka bir ekrana geçince
// uyarı gözden kaybolurdu.

import { useEffect, useState } from "react";

import Icon from "../../ui/Icon";
import { yedekApi } from "./yedekApi";

/** Kart yedek hazırladığında / vazgeçildiğinde yayar; bant durumu yeniden okur. */
export const YEDEK_DEGISTI_OLAYI = "dd:yedek-degisti";

export function yedekDegistiYayinla(): void {
  window.dispatchEvent(new Event(YEDEK_DEGISTI_OLAYI));
}

export default function BekleyenGeriYuklemeBandi() {
  const [bekliyor, setBekliyor] = useState(false);

  useEffect(() => {
    let iptal = false;
    const oku = () => {
      yedekApi
        .ozet()
        .then((ozet) => {
          if (!iptal) setBekliyor(ozet.pending_restore);
        })
        .catch(() => undefined); // durum okunamıyorsa bant gösterilmez; kart hatayı gösterir
    };
    oku();
    window.addEventListener(YEDEK_DEGISTI_OLAYI, oku);
    return () => {
      iptal = true;
      window.removeEventListener(YEDEK_DEGISTI_OLAYI, oku);
    };
  }, []);

  if (!bekliyor) return null;

  return (
    <div
      role="alert"
      className="mb-4 flex items-start gap-3 rounded-shape-md bg-error-container px-4 py-3 text-body-medium text-on-error-container"
    >
      <Icon name="settings_backup_restore" size="lg" />
      <span>
        <strong>Yedekten geri yükleme hazır.</strong> Programı şimdi kapatıp yeniden açın. O ana dek
        girdiğiniz kayıtlar geri yüklemeyle birlikte kaybolur. Vazgeçmek için: Ayarlar → Güvenlik →
        Otomatik yedekler ve geri yükleme.
      </span>
    </div>
  );
}
