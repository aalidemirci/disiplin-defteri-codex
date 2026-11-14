// VEKÂLET KAYDI uyarıları (kullanıcı kararı, 14.11.2026 — S7; S5/S6 çizgisi: UYAR, ENGELLEME).
// Metinler sunucuda üretilir (`chair_warnings`): başkan katılmadı ama yedek üye çağrılmamış
// (md. 188 son cümlesi, md. 191/2) ya da dosya görüşme tutanağı dosyanın kurul toplantısı
// kaydıyla başkanlık bakımından çelişiyor (EK-1 ile karar defteri farklı başkan basmasın).
// Liste boşsa hiçbir şey çizilmez.

import Icon from "../../ui/Icon";

export default function VekaletUyarisi({ warnings }: { warnings: string[] | undefined }) {
  if (!warnings || warnings.length === 0) return null;
  return (
    <div className="flex items-start gap-3 rounded-shape-sm bg-tertiary-container p-3">
      <Icon name="warning" className="shrink-0 text-on-tertiary-container" />
      {/* `role="status"`: uyarı yalnız renk ve ikonla değil, ekran okuyucuya da duyurulur. */}
      <div role="status" className="space-y-1 text-body-small text-on-tertiary-container">
        <p>Başkan vekâleti (uyarıdır; kayıt engellenmez):</p>
        <ul className="list-inside list-disc">
          {warnings.map((warning) => (
            <li key={warning}>{warning}</li>
          ))}
        </ul>
      </div>
    </div>
  );
}
