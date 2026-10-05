// Disiplin Defteri — kök route tanımı (Görev 3; F4-D2'de disiplin, F4-D4'te panel/
// kurulum/kişiler/ayarlar sayfalarına bağlandı).
// Route ağacı OYS `App.tsx` disiplin bloğundan uyarlandı; sapmalar: rol bazlı
// koşullu rotalar yok (authsuz tek kullanıcı), OYS'deki `lazy()` + Suspense bölmesi
// kopyalanmadı — masaüstü paket yerel olduğundan eager import yeterli.
// Rotalar `KurulumKapisi` içine alınır: kurulum tamamlanmadan sihirbaz dışına
// çıkılamaz (gerekçe KurulumKapisi.tsx başında).

import { Navigate, Route, Routes } from "react-router-dom";

import AppShell from "./AppShell";
import KurulumKapisi from "./KurulumKapisi";
import AyarlarPage from "./modules/ayarlar/AyarlarPage";
import BilgiNotlariPage from "./modules/bilgi-notlari/BilgiNotlariPage";
import SinifSorumlulariPage from "./modules/ayarlar/SinifSorumlulariPage";
import DisiplinDetayPage from "./modules/disiplin/DisiplinDetayPage";
import DisiplinPage from "./modules/disiplin/DisiplinPage";
import KararTipleriPage from "./modules/disiplin/KararTipleriPage";
import GuvenlikKapisi from "./modules/guvenlik/GuvenlikKapisi";
import HakkindaPage from "./modules/hakkinda/HakkindaPage";
import ImhaPage from "./modules/imha/ImhaPage";
import KisilerPage from "./modules/kisiler/KisilerPage";
import OdulDisiplinKuruluPage from "./modules/kurul/OdulDisiplinKuruluPage";
import OnurKuruluPage from "./modules/kurul/OnurKuruluPage";
import KurulumPage from "./modules/kurulum/KurulumPage";
import PanelPage from "./modules/panel/PanelPage";
import YilDevriPage from "./modules/yildevri/YilDevriPage";

export default function App() {
  return (
    <AppShell>
      {/* Kilit ekranı kurulum kapısından ÖNCE: parola kuruluysa hiçbir veri
          ekranı (sihirbaz dahil) açılmadan önce açılması gerekir. */}
      <GuvenlikKapisi>
        <KurulumKapisi>
          <Routes>
            <Route path="/" element={<PanelPage />} />
            {/* Kurulum sihirbazı — kapının izin verdiği tek rota (bkz. KurulumKapisi). */}
            <Route path="/kurulum" element={<KurulumPage />} />
            {/* OYS route sırası korunur: statik yollar `:id` parametresinden önce. */}
            <Route path="/disiplin" element={<DisiplinPage />} />
            <Route path="/disiplin/karar-tipleri" element={<KararTipleriPage />} />
            <Route path="/disiplin/:id" element={<DisiplinDetayPage />} />
            {/* Kurullar yönetmeliğin bölümlerini izler (md. 176; 04.10.2026 kurul işleyişi):
                Ödül ve Disiplin Kurulu (Yedinci Bölüm) ve Onur Kurulu (Altıncı Bölüm). */}
            <Route path="/odul-disiplin-kurulu" element={<OdulDisiplinKuruluPage />} />
            <Route path="/onur-kurulu" element={<OnurKuruluPage />} />
            {/* Eski adresler yeni kurul sayfalarına yönlenir. */}
            <Route
              path="/disiplin/kurul"
              element={<Navigate to="/odul-disiplin-kurulu?sekme=uyeler" replace />}
            />
            <Route
              path="/disiplin/onur-teklifleri"
              element={<Navigate to="/odul-disiplin-kurulu?sekme=mudur-onayi" replace />}
            />
            <Route path="/odul" element={<Navigate to="/onur-kurulu" replace />} />
            <Route path="/bilgi-notlari" element={<BilgiNotlariPage />} />
            <Route path="/bilgi-notlari/:notTuru" element={<BilgiNotlariPage />} />
            {/* Öğrenci + personel sicili (OYS'de core modülünün işi; burada yerel). */}
            <Route path="/kisiler" element={<KisilerPage />} />
            {/* Ders yılı, tatil takvimi, okul künyesi. */}
            <Route path="/ayarlar" element={<AyarlarPage />} />
            <Route path="/ayarlar/sinif-sorumlulari" element={<SinifSorumlulariPage />} />
            <Route path="/hakkinda" element={<HakkindaPage />} />
            {/* Yıl devri ve imha menüde YOK: ikisi de yılda bir koşan, geri
              alınamaz işlemler — Ayarlar'daki kartlardan bilinçli olarak açılır. */}
            <Route path="/yil-devri" element={<YilDevriPage />} />
            <Route path="/imha" element={<ImhaPage />} />
          </Routes>
        </KurulumKapisi>
      </GuvenlikKapisi>
    </AppShell>
  );
}
