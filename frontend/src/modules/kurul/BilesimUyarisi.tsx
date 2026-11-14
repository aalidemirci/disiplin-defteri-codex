// Ödül ve Disiplin Kurulu bileşim uyarısı (md. 185/1) — kullanıcı kararı, 14.11.2026 — S5:
// UYAR, ENGELLEME. Kurul; müdür yardımcısı başkan, öğretmenler kurulunca seçilen iki
// öğretmen, onur kurulu ikinci başkanı ve okul-aile birliğinden bir öğrenci velisinden
// oluşur. Uyarı metinleri sunucuda üretilir (`selectors.committee_composition_warnings`)
// ve neyin eksik/fazla olduğunu söyler; burada yalnız kalıcı bir kartta listelenir.
// Liste boşsa hiçbir şey çizilmez (kurul ve toplantı ekranı değişmez).

import Card from "../../ui/Card";
import Icon from "../../ui/Icon";

export default function BilesimUyarisi({ warnings }: { warnings: string[] | undefined }) {
  if (!warnings || warnings.length === 0) return null;
  return (
    <Card elevation={0} className="flex items-start gap-3 bg-tertiary-container p-4">
      <Icon name="warning" className="shrink-0 text-on-tertiary-container" />
      {/* `role="status"`: uyarı yalnız renk ve ikonla değil, ekran okuyucuya da duyurulur. */}
      <div role="status" className="space-y-1 text-body-medium text-on-tertiary-container">
        <p>Kurul bileşimi md. 185/1'e uymuyor (uyarıdır; kayıt ve toplantı engellenmez):</p>
        <ul className="list-inside list-disc">
          {warnings.map((warning) => (
            <li key={warning}>{warning}</li>
          ))}
        </ul>
      </div>
    </Card>
  );
}
