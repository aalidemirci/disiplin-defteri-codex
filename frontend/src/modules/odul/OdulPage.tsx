// Onur Kurulu modülü (ADR-0011) — md. 159-184. Tek rota (/odul) altında sekmeli sayfa:
// Teklifler (teklif + form PDF) / Kurul Kararı (uygun görüş + belge kararı + tutanaklar) /
// Toplantılar (karar defteri md. 184) / Kurul Üyeleri.
//
// OYS `modules/odul/OdulPage.tsx`'ten UYARLANDI (F4-D3); sapmalar: auth yok → "Kurul Üyeleri"
// sekmesinin müdür rol kapısı kalktı (sekme daima görünür), sekme görünürlüğü koşulsuz.

import { useState } from "react";

import Card from "../../ui/Card";
import Icon from "../../ui/Icon";
import Tabs, { tabPanelProps } from "../../ui/Tabs";
import type { TabItem } from "../../ui/Tabs";
import TutanakListesi from "../kurul/TutanakListesi";
import KurulKarariPanel from "./KurulKarariPanel";
import OnurBelgeleriPanel from "./OnurBelgeleriPanel";
import OnurGenelKuruluPanel from "./OnurGenelKuruluPanel";
import OnurKuruluPanel from "./OnurKuruluPanel";

export default function OdulPage() {
  const tabs: TabItem[] = [
    { key: "teklifler", label: "Teklifler", icon: "how_to_reg" },
    { key: "karar", label: "Kurul Kararı", icon: "ballot" },
    { key: "toplantilar", label: "Toplantılar", icon: "menu_book" },
    { key: "genel-kurul", label: "Genel Kurul", icon: "groups_3" },
    { key: "kurul", label: "Kurul Üyeleri", icon: "groups" },
  ];

  const [active, setActive] = useState("teklifler");

  return (
    <div className="space-y-6">
      <div className="dd-page-header">
        <div>
          <h1 className="dd-page-title">Onur Kurulu</h1>
          <p className="dd-page-description">
            Onur belgesi süreci (md. 159-184): öğretmen/yönetim teklifi → onur kurulu uygun görüşü →
            ödül-disiplin kurulu kararı. Akademik belgeler (teşekkür/takdir/üstün başarı) e-Okul'da
            üretilir, burada yer almaz.
          </p>
        </div>
      </div>

      <Card elevation={1} className="flex items-start gap-3 bg-surface-container-low p-4">
        <Icon name="info" className="shrink-0 text-primary" />
        <p className="text-body-small text-on-surface-variant">
          {/* Onur listesi kuralı md. 161/1'in SON cümlesidir; md. 161/2 öğretmenler kurulunun
              belirlediği ek onur davranışlarıdır. Asma kuralı md. 162/3. */}
          <strong>Onur listesi e-Okul'da otomatik üretilir</strong> (md. 161/1 — bir öğretim yılı
          içinde iki ve daha fazla onur belgesi alan öğrenci) ve ders kesiminde fotoğraflı olarak
          asılır (md. 162/3). Bu program ayrı bir onur listesi tutmaz.
        </p>
      </Card>

      <Tabs
        items={tabs}
        active={active}
        onChange={setActive}
        ariaLabel="Onur Kurulu bölümleri"
        idBase="odul"
      />

      <div {...tabPanelProps("odul", active)}>
        {active === "teklifler" && <OnurBelgeleriPanel />}
        {active === "karar" && <KurulKarariPanel />}
        {active === "toplantilar" && <TutanakListesi councilType="HONOR" />}
        {active === "genel-kurul" && <OnurGenelKuruluPanel />}
        {active === "kurul" && <OnurKuruluPanel />}
      </div>
    </div>
  );
}
