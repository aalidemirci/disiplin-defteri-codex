// Onur Kurulu (md. 178-184, Onur Genel Kurulu dahil) — kurul işleyişine göre sayfa
// (04.10.2026, Aşama 1; eski `odul/OdulPage`). Öğrenci, öğretmen veya okul yönetimi onur
// belgesi teklif eder (md. 161/1) → Onur Kurulu ayda en az bir toplanıp teklifi görüşür
// ve Ödül ve Disiplin Kuruluna önerir (md. 183/b) → kararlar karar defterine yazılır
// (md. 184). Belge verme kararı bu kurulun DEĞİL, Ödül ve Disiplin Kurulunundur.
// Sekmeler: Teklifler · Gündem · Toplantılar (karar defteri) · Genel Kurul · Kurul Üyeleri.

import Card from "../../ui/Card";
import Icon from "../../ui/Icon";
import Tabs, { tabPanelProps } from "../../ui/Tabs";
import type { TabItem } from "../../ui/Tabs";
import OnurBelgeleriPanel from "../odul/OnurBelgeleriPanel";
import OnurGenelKuruluPanel from "../odul/OnurGenelKuruluPanel";
import OnurKuruluPanel from "../odul/OnurKuruluPanel";
import GundemPanel from "./GundemPanel";
import TutanakListesi from "./TutanakListesi";
import useSekme from "./useSekme";

const TABS: TabItem[] = [
  { key: "teklifler", label: "Teklifler", icon: "how_to_reg" },
  { key: "gundem", label: "Gündem", icon: "pending_actions" },
  { key: "toplantilar", label: "Toplantılar", icon: "menu_book" },
  { key: "genel-kurul", label: "Genel Kurul", icon: "groups_3" },
  { key: "uyeler", label: "Kurul Üyeleri", icon: "groups" },
];

export default function OnurKuruluPage() {
  const [active, setActive] = useSekme(TABS.map((tab) => tab.key));

  return (
    <div className="space-y-6">
      <div className="dd-page-header">
        <div>
          <h1 className="dd-page-title">Onur Kurulu</h1>
          <p className="dd-page-description">
            Onur belgesi süreci (md. 161, 178-184): öğrenci/öğretmen/yönetim teklifi → Onur Kurulu
            toplantısında uygun görüş → Ödül ve Disiplin Kuruluna öneri. Belge verme kararı Ödül ve
            Disiplin Kurulunundur.
          </p>
        </div>
      </div>

      <Card elevation={1} className="flex items-start gap-3 bg-surface-container-low p-4">
        <Icon name="info" className="shrink-0 text-primary" />
        <p className="text-body-small text-on-surface-variant">
          {/* Onur listesi kuralı md. 161/1'in SON cümlesidir; md. 161/2 öğretmenler kurulunun
              belirlediği ek onur davranışlarıdır. Asma kuralı md. 162/3. */}
          <strong>Onur listesi e-Okul&apos;da otomatik üretilir</strong> (md. 161/1 — bir öğretim
          yılı içinde iki ve daha fazla onur belgesi alan öğrenci) ve ders kesiminde fotoğraflı
          olarak asılır (md. 162/3). Bu program ayrı bir onur listesi tutmaz.
        </p>
      </Card>

      <Tabs
        items={TABS}
        active={active}
        onChange={setActive}
        ariaLabel="Onur Kurulu bölümleri"
        idBase="onur"
      />

      <div {...tabPanelProps("onur", active)}>
        {active === "teklifler" && <OnurBelgeleriPanel />}
        {active === "gundem" && <GundemPanel councilType="HONOR" meetingsTab="toplantilar" />}
        {active === "toplantilar" && <TutanakListesi councilType="HONOR" />}
        {active === "genel-kurul" && <OnurGenelKuruluPanel />}
        {active === "uyeler" && <OnurKuruluPanel />}
      </div>
    </div>
  );
}
