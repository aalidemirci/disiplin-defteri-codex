// Okul Öğrenci Ödül ve Disiplin Kurulu (md. 185-191) — kurul işleyişine göre sayfa
// (04.10.2026, Aşama 1). Kurul toplanır (md. 190-191) → gündemdeki işleri karara bağlar
// (md. 189) → karar defterine yazar ve okul müdürüne sunar (md. 196) → müdür onaylar.
// Sekmeler: Gündem (Onur Kurulundan gelen öneriler) · Toplantılar (karar defteri) ·
// Müdür Onayı · Kurul Üyeleri. Disiplin dosyalarının kurul görüşmesi şimdilik dosya
// içinde kalır (Aşama 2'de bu kurulun gündemine taşınacak).

import Card from "../../ui/Card";
import Icon from "../../ui/Icon";
import Tabs, { tabPanelProps } from "../../ui/Tabs";
import type { TabItem } from "../../ui/Tabs";
import GundemPanel from "./GundemPanel";
import MudurOnayiPanel from "./MudurOnayiPanel";
import OdkUyeleriPanel from "./OdkUyeleriPanel";
import TutanakListesi from "./TutanakListesi";
import useSekme from "./useSekme";

const TABS: TabItem[] = [
  { key: "gundem", label: "Gündem", icon: "pending_actions" },
  { key: "toplantilar", label: "Toplantılar", icon: "menu_book" },
  { key: "mudur-onayi", label: "Müdür Onayı", icon: "verified" },
  { key: "uyeler", label: "Kurul Üyeleri", icon: "groups" },
];

export default function OdulDisiplinKuruluPage() {
  const [active, setActive] = useSekme(TABS.map((tab) => tab.key));

  return (
    <div className="space-y-6">
      <div className="dd-page-header">
        <div>
          <h1 className="dd-page-title">Ödül ve Disiplin Kurulu</h1>
          <p className="dd-page-description">
            Okul Öğrenci Ödül ve Disiplin Kurulu (md. 185-191): üyelerin salt çoğunluğuyla toplanır,
            oy çoğunluğuyla karar alır (md. 191); onur belgesi verilmesine karar verir (md. 161/1,
            189/ç), kararlarını karar defterine yazıp okul müdürüne sunar (md. 196).
          </p>
        </div>
      </div>

      <Card elevation={1} className="flex items-start gap-3 bg-surface-container-low p-4">
        <Icon name="info" className="shrink-0 text-primary" />
        <p className="text-body-small text-on-surface-variant">
          Disiplin dosyalarının kurul görüşmesi ve kararı şimdilik <strong>dosya içinden</strong>{" "}
          (Disiplin Dosyaları → dosya → Kurul &amp; Karar) yürür. Teşekkür, takdir ve üstün başarı
          belgeleri (md. 160) e-Okul&apos;da üretilir; burada yalnız onur belgesi kararları vardır.
        </p>
      </Card>

      <Tabs
        items={TABS}
        active={active}
        onChange={setActive}
        ariaLabel="Ödül ve Disiplin Kurulu bölümleri"
        idBase="odk"
      />

      <div {...tabPanelProps("odk", active)}>
        {active === "gundem" && <GundemPanel councilType="DISCIPLINE" meetingsTab="toplantilar" />}
        {active === "toplantilar" && <TutanakListesi councilType="DISCIPLINE" />}
        {active === "mudur-onayi" && <MudurOnayiPanel />}
        {active === "uyeler" && <OdkUyeleriPanel />}
      </div>
    </div>
  );
}
