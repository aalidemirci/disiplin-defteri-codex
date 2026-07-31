import { useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import { NavLink, useParams } from "react-router-dom";

import Icon from "../../ui/Icon";

type NoteKey = "disiplin-kurulu" | "onur-kurulu";

interface Section {
  id: string;
  title: string;
  content: ReactNode;
}

interface Note {
  key: NoteKey;
  eyebrow: string;
  title: string;
  description: string;
  icon: string;
  accent: string;
  sections: Section[];
  checklist: string[];
}

function Ref({ children }: { children: ReactNode }) {
  return (
    <span className="whitespace-nowrap rounded-shape-xs bg-secondary-container px-1.5 py-0.5 text-label-small font-semibold text-on-secondary-container">
      {children}
    </span>
  );
}

function Callout({
  icon,
  title,
  children,
  tone = "primary",
}: {
  icon: string;
  title: string;
  children: ReactNode;
  tone?: "primary" | "tertiary";
}) {
  const colors =
    tone === "tertiary"
      ? "bg-tertiary-container text-on-tertiary-container"
      : "bg-primary-container text-on-primary-container";
  return (
    <div className={`rounded-shape-md p-4 ${colors}`}>
      <div className="flex items-center gap-2 text-title-small font-semibold">
        <Icon name={icon} size="lg" filled />
        {title}
      </div>
      <div className="mt-2 text-body-medium leading-6">{children}</div>
    </div>
  );
}

const DISCIPLINE_SECTIONS: Section[] = [
  {
    id: "amac",
    title: "Amaç ve kapsam",
    content: (
      <>
        <p>
          Bu not, Okul Öğrenci Ödül ve Disiplin Kurulunun öğretim yılı başında mevzuata uygun
          biçimde oluşturulması, ilk toplantının yürütülmesi ve önleyici disiplin çalışmalarının
          planlanması için hazırlanmıştır.
        </p>
        <Callout icon="calendar_month" title="Yıl başındaki iki temel yükümlülük">
          Üyeler her ders yılının ilk ayı içinde belirlenir. Kurul dönem başlarında toplanarak
          okulun disiplin açısından genel durumunu değerlendirir. <Ref>Md. 185, 189/f</Ref>
        </Callout>
      </>
    ),
  },
  {
    id: "dayanak",
    title: "Yasal dayanak",
    content: (
      <ul>
        <li>
          MEB Ortaöğretim Kurumları Yönetmeliği; öğrenci davranışları, ödül ve disiplin hükümleri
          ile kurullara ilişkin <Ref>Md. 157–206</Ref>.
        </li>
        <li>MEB Önleyici Disiplin Uygulamaları Öğretmen Rehber Kitabı.</li>
        <li>1739 sayılı Millî Eğitim Temel Kanunu, özellikle kök değerler ve genel amaçlar.</li>
        <li>Öğrenci verilerinin işlenmesinde 6698 sayılı Kişisel Verilerin Korunması Kanunu.</li>
      </ul>
    ),
  },
  {
    id: "olusum",
    title: "Kurulun oluşumu",
    content: (
      <>
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
          {[
            ["Başkan", "Müdürün görevlendirdiği müdür yardımcısı", "shield_person"],
            ["2 öğretmen", "Öğretmenler kurulunca gizli oyla seçilir", "school"],
            ["1 öğrenci", "Onur Kurulu ikinci başkanı", "person"],
            ["1 veli", "Okul-Aile Birliği temsilcisi", "family_restroom"],
            ["Yedekler", "Gerektiğinde asıl üyenin yerine çağrılır", "group_add"],
          ].map(([title, text, icon]) => (
            <div key={title} className="rounded-shape-md bg-surface-container-low p-3">
              <Icon name={icon} className="text-primary" />
              <p className="mt-2 text-title-small font-semibold text-on-surface">{title}</p>
              <p className="mt-1 text-body-small text-on-surface-variant">{text}</p>
            </div>
          ))}
        </div>
        <p>
          Öğretmen üyeler ilk ay içinde seçilir. Eşitlikte seçim yenilenir; sonuç yine eşitse
          kıdemli öğretmen seçilmiş sayılır. Kurulun görevi yeni kurul oluşana kadar sürer.{" "}
          <Ref>Md. 185–188</Ref>
        </p>
        <Callout icon="gavel" title="Tarafsızlık kuralı" tone="tertiary">
          İncelenen davranıştan şikâyetçi olan veya zarar gören üye görüşmeye katılamaz; yerine
          yedek üye çağrılır. <Ref>Md. 191/2</Ref>
        </Callout>
      </>
    ),
  },
  {
    id: "gorevler",
    title: "Kurulun görevleri",
    content: (
      <ul>
        <li>Okulda düzen ve disiplinin sağlanmasına ilişkin kararlar almak.</li>
        <li>Disipline aykırı davranışların nedenlerini ve önleme yollarını incelemek.</li>
        <li>Örnek davranış ve başarı gösteren öğrencilerin ödüllendirilmesine karar vermek.</li>
        <li>Dönem başında genel durumu değerlendirip kişisel olmayan tedbirler önermek.</li>
        <li>Müdürün havale ettiği olayları inceleyip karara bağlamak.</li>
        <li>Dönem ve yıl sonunda olay, tedbir ve sonuç raporunu yönetime sunmak.</li>
      </ul>
    ),
  },
  {
    id: "onleyici",
    title: "Önleyici disiplin yaklaşımı",
    content: (
      <>
        <div className="grid gap-3 sm:grid-cols-3">
          {[
            ["01", "Önleyici", "Beklenen davranışı ve okul kurallarını önceden öğret."],
            ["02", "Destekleyici", "Erken işaretlerde rehberlik ve iş birliğiyle destekle."],
            ["03", "İyileştirici", "Olay sonrasında gelişim ve sosyal sorumluluk planla."],
          ].map(([number, title, text]) => (
            <div key={number} className="rounded-shape-md border border-outline-variant p-4">
              <span className="text-label-small font-bold text-primary">{number}</span>
              <p className="mt-1 text-title-medium font-semibold text-on-surface">{title}</p>
              <p className="mt-1 text-body-medium text-on-surface-variant">{text}</p>
            </div>
          ))}
        </div>
        <p>
          Çalışmalar; adalet, dostluk, dürüstlük, öz denetim, sabır, saygı, sevgi, sorumluluk,
          vatanseverlik ve yardımseverlik kök değerleriyle ilişkilendirilmelidir. Okula özgü
          destekleyici kurallar kurul önerisi, öğretmenler kurulu kararı ve müdür onayıyla yürürlüğe
          girer. <Ref>Md. 157/5, 168/4</Ref>
        </p>
      </>
    ),
  },
  {
    id: "surec",
    title: "Disiplin süreci ve süreler",
    content: (
      <>
        <ol>
          <li>Olay ve ilk bilgiler kayıt altına alınır; varsa rehberlik servisine iletilir.</li>
          <li>Dosya müdür tarafından kurula havale edilir.</li>
          <li>Öğrenci ve ilgililerin ifadeleri alınır; deliller toplanır.</li>
          <li>Kurul dosyayı gelişinden itibaren 10 iş günü içinde görüşür.</li>
          <li>Zorunlu hâlde ara karar ve müdür onayıyla süre bir defaya mahsus 10 iş günü uzar.</li>
          <li>Gerekçeli karar karar defterine yazılır, imzalanır ve onaya sunulur.</li>
        </ol>
        <Callout icon="child_care" title="Kararda öğrencinin üstün yararı">
          Öğrencinin çocuk olduğu, gizlilik, rehber öğretmen ve veli görüşleri, kişisel ve
          psikolojik durumu ile önceki davranışları birlikte değerlendirilir.{" "}
          <Ref>Md. 168, 192–197</Ref>
        </Callout>
      </>
    ),
  },
  {
    id: "cezalar",
    title: "Cezalar ve davranış puanı",
    content: (
      <>
        <div className="overflow-x-auto rounded-shape-md border border-outline-variant">
          <table className="min-w-table w-full text-left text-body-medium">
            <thead className="bg-surface-container text-label-large text-on-surface-variant">
              <tr>
                <th className="px-4 py-3">Ceza</th>
                <th className="px-4 py-3">Davranış puanı</th>
                <th className="px-4 py-3">Onay mercii</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-outline-variant">
              {[
                ["Kınama", "10 puan indirim", "Okul müdürü"],
                ["1–5 gün uzaklaştırma", "20 puan indirim", "Okul müdürü"],
                ["Okul değiştirme", "40 puan indirim", "İlçe öğrenci disiplin kurulu"],
                ["Örgün eğitim dışına çıkarma", "80 puan indirim", "İl öğrenci disiplin kurulu"],
              ].map((row) => (
                <tr key={row[0]}>
                  {row.map((cell) => (
                    <td key={cell} className="px-4 py-3 text-on-surface">
                      {cell}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p>
          Her ders yılı başında davranış puanı 100’dür. Olumlu değişim gösteren öğrencinin cezası
          öğretmenler kurulunca kaldırılabilir ve puanı iade edilebilir. İlk kez kınama gerektiren
          davranışta yönetmelikteki yazılı uyarı usulü ayrıca değerlendirilir.{" "}
          <Ref>Md. 157/7, 163, 170–171</Ref>
        </p>
      </>
    ),
  },
  {
    id: "gundem",
    title: "Önerilen sene başı gündemi",
    content: (
      <ol>
        <li>Açılış, yoklama ve salt çoğunluğun tespiti.</li>
        <li>Üyelerin tanıtılması, görev ve sorumlulukların paylaşılması.</li>
        <li>Geçen yılın disiplin durumu ve sonuç raporunun değerlendirilmesi.</li>
        <li>Okulun genel durumu, risk alanları ve önleyici tedbirlerin görüşülmesi.</li>
        <li>Kök değerler ve sosyal-duygusal beceri çalışmalarının planlanması.</li>
        <li>Destekleyici okul ve sınıf kurallarının gözden geçirilmesi.</li>
        <li>Okul–Öğrenci–Veli Sözleşmesi sürecinin değerlendirilmesi.</li>
        <li>Belge, karar defteri, toplantı ve yazışma usullerinin hatırlatılması.</li>
        <li>Dilek, öneriler ve kapanış.</li>
      </ol>
    ),
  },
  {
    id: "takvim",
    title: "Yıl başı çalışma takvimi",
    content: (
      <div className="space-y-3">
        {[
          ["Ders yılı öncesi", "Gündem, geçen yıl raporu, karar defteri ve formları hazırlayın."],
          ["İlk hafta", "Kurul seçimlerini öğretmenler kurulu gündemine alın; kuralları duyurun."],
          ["İlk ay", "Öğretmen, öğrenci ve veli üyeleri ile yedekleri belirleyip tebliğ edin."],
          ["İlk ay sonu", "Genel durum ve önleyici tedbirler gündemiyle kurul toplantısını yapın."],
          ["Toplantı sonrası", "Gerekçeli kararları yazıp imzalayın ve müdüre sunun."],
          [
            "Dönem boyunca",
            "Önleyici çalışmaları izleyin; dönem/yıl sonu sonuç raporunu hazırlayın.",
          ],
        ].map(([time, task]) => (
          <div
            key={time}
            className="grid gap-1 rounded-shape-md bg-surface-container-low p-3 sm:grid-cols-pane-sm"
          >
            <p className="text-label-large font-semibold text-primary">{time}</p>
            <p className="text-body-medium text-on-surface">{task}</p>
          </div>
        ))}
      </div>
    ),
  },
];

const HONOR_SECTIONS: Section[] = [
  {
    id: "amac",
    title: "Amaç ve temel ayrım",
    content: (
      <>
        <p>
          Onur Kurulu; öğrencilerin okul düzeni, olumlu davranış, sosyal sorumluluk ve onur belgesi
          süreçlerine katılımını sağlayan öğrenci ağırlıklı kuruldur. Okul Öğrenci Ödül ve Disiplin
          Kurulundan ayrı oluşturulur.
        </p>
        <Callout icon="account_tree" title="İki ayrı kurul, birbirini tamamlayan süreç">
          Onur Kurulu öğrenci için uygun görüş ve öneri oluşturur; onur belgesiyle ödüllendirme
          kararını Okul Öğrenci Ödül ve Disiplin Kurulu verir. <Ref>Md. 161, 180–185</Ref>
        </Callout>
      </>
    ),
  },
  {
    id: "genel-kurul",
    title: "Onur genel kurulu",
    content: (
      <ul>
        <li>Her şubeden bir öğrenci, sınıf rehber öğretmeninin gözetiminde seçilir.</li>
        <li>Dönemde en az bir kez toplanır ve Onur Kurulu üyelerini seçer.</li>
        <li>Okuldaki disiplinsizliklerin nedenlerini inceler, önleyici öneriler geliştirir.</li>
        <li>Şubelerden gelen öğrenci görüşlerinin kurula taşınmasını sağlar.</li>
      </ul>
    ),
  },
  {
    id: "olusum",
    title: "Onur Kurulunun oluşumu",
    content: (
      <>
        <div className="grid gap-3 sm:grid-cols-3">
          {[
            ["Başkan", "Ödül-disiplin kurulu dışından, öğretmenler kurulunca seçilen öğretmen"],
            ["Öğrenci üyeler", "Her sınıf seviyesinden onur genel kurulunca seçilen bir öğrenci"],
            ["İkinci başkan", "Son sınıf düzeyindeki öğrenci üye; ayrıca yedeği belirlenir"],
          ].map(([title, text]) => (
            <div key={title} className="rounded-shape-md bg-surface-container-low p-4">
              <p className="text-title-small font-semibold text-on-surface">{title}</p>
              <p className="mt-1 text-body-medium text-on-surface-variant">{text}</p>
            </div>
          ))}
        </div>
        <p>
          Üyelerin disiplin cezası almamış, örnek davranışlı, çalışkan, dürüst ve güvenilir olması
          gerekir. Bu nitelikleri kaybeden veya ceza alan öğrencinin üyeliği sona erer.{" "}
          <Ref>Md. 180–182</Ref>
        </p>
      </>
    ),
  },
  {
    id: "gorevler",
    title: "Görevler ve çalışma usulü",
    content: (
      <ul>
        <li>Ayda en az bir kez toplanmak.</li>
        <li>Okul düzeni ve disiplin konularını görüşerek müdüre öneri sunmak.</li>
        <li>Onur belgesi önerilecek öğrenciler hakkında uygun görüş oluşturmak.</li>
        <li>Öğrencilerin boş zamanlarını değerlendirecek programlara katkı vermek.</li>
        <li>Nöbet işleri ve sınıf başkanlığına ilişkin esasların hazırlanmasına katılmak.</li>
        <li>Kararları Onur Kurulu karar defterine yazmak ve imzalamak.</li>
      </ul>
    ),
  },
  {
    id: "onur-belgesi",
    title: "Onur belgesi ölçütleri",
    content: (
      <>
        <p>
          Puan şartına bağlı olmadan; Türkçeyi örnek kullanma, etkinliklerde liderlik ve üstün
          başarı, çevreyi ve okul araçlarını koruma, görgü ve insan ilişkilerinde örneklik, trafik
          ve bilişim kurallarına uyma, düzenli devam, sosyal sorumluluk ile sağlık ve güvenlik
          çalışmalarında öne çıkma gibi davranışlar değerlendirilir.
        </p>
        <Callout icon="verified" title="Uygunluk koşulu" tone="tertiary">
          Aday öğrencinin davranış puanı indirilmemiş olmalıdır. Öğretmenler kurulu yıl başında
          okulun özelliklerine uygun ek davranış ölçütleri belirleyebilir. <Ref>Md. 161</Ref>
        </Callout>
      </>
    ),
  },
  {
    id: "akis",
    title: "Tekliften karara süreç",
    content: (
      <div className="grid gap-3 md:grid-cols-4">
        {[
          ["1", "Teklif", "Öğrenci, öğretmen veya okul yönetimi adayı teklif eder."],
          ["2", "Ön inceleme", "Koşullar ve örnek davranışı destekleyen bilgiler kontrol edilir."],
          ["3", "Uygun görüş", "Onur Kurulu görüşür, gerekçeli kararını deftere yazar."],
          ["4", "Nihai karar", "Ödül ve Disiplin Kurulu kabul veya ret kararı verir."],
        ].map(([number, title, text]) => (
          <div key={number} className="relative rounded-shape-md border border-outline-variant p-4">
            <span className="flex h-7 w-7 items-center justify-center rounded-full bg-primary text-label-medium font-bold text-on-primary">
              {number}
            </span>
            <p className="mt-3 text-title-small font-semibold text-on-surface">{title}</p>
            <p className="mt-1 text-body-small text-on-surface-variant">{text}</p>
          </div>
        ))}
      </div>
    ),
  },
  {
    id: "onur-listesi",
    title: "Onur listesi ve duyuru",
    content: (
      <>
        <p>
          Bir öğretim yılı içinde iki veya daha fazla onur belgesi alan öğrenci okulun onur
          listesinde yer alır. Onur listesi ders kesiminde okunur ve fotoğraflı olarak takip eden
          ders yılı boyunca herkesin görebileceği bir yerde sergilenir. Kişisel verilerin
          görünürlüğü okulun KVKK uygulamalarıyla birlikte değerlendirilmelidir.{" "}
          <Ref>Md. 161–162</Ref>
        </p>
      </>
    ),
  },
  {
    id: "gundem",
    title: "Önerilen ilk toplantı gündemi",
    content: (
      <ol>
        <li>Açılış, yoklama; başkan, ikinci başkan ve üyelerin tanıtılması.</li>
        <li>Onur Kurulunun görevleri, toplantı düzeni ve karar defterinin açıklanması.</li>
        <li>Geçen yılın öğrenci davranışları ve kurul çalışmalarının değerlendirilmesi.</li>
        <li>Okul düzenini güçlendirecek öğrenci katılımlı çalışmaların belirlenmesi.</li>
        <li>Onur belgesi ölçütleri ve tekliflerin değerlendirme yönteminin açıklanması.</li>
        <li>Öğretmenler kurulunca belirlenen ek onur davranışlarının duyurulması.</li>
        <li>Aylık toplantı takvimi, görev paylaşımı ve iletişim düzeninin kararlaştırılması.</li>
        <li>Dilek, öneriler ve kapanış.</li>
      </ol>
    ),
  },
];

const NOTES: Record<NoteKey, Note> = {
  "disiplin-kurulu": {
    key: "disiplin-kurulu",
    eyebrow: "Sene başı hazırlık rehberi",
    title: "Okul Öğrenci Ödül ve Disiplin Kurulu",
    description:
      "Kurulun oluşturulması, önleyici disiplin planı, yasal süreler ve ilk toplantı için uygulama notu.",
    icon: "balance",
    accent: "bg-primary-container text-on-primary-container",
    sections: DISCIPLINE_SECTIONS,
    checklist: [
      "Toplantı tarihi, yeri ve gündem taslağı hazırlandı.",
      "Geçen öğretim yılının disiplin sonuç raporu temin edildi.",
      "2 asıl ve 3 yedek öğretmen üye gizli oyla seçildi.",
      "Onur Kurulu başkanı ile öğrenci ikinci başkan belirlendi.",
      "Okul-Aile Birliği veli üyesi ve yedeği belirlendi.",
      "Kurul başkanı görevlendirildi; üyelere yazılı tebliğ yapıldı.",
      "Karar defteri ve kurul kararı örnekleri hazırlandı.",
      "Davranış puanlarının 100 olarak başladığı teyit edildi.",
      "Üyelere yazılı toplantı çağrısı yapıldı.",
      "Önleyici disiplin ve destekleyici okul kuralları görüşüldü.",
      "Kararlar gerekçeli yazıldı, imzalandı ve müdüre sunuldu.",
    ],
  },
  "onur-kurulu": {
    key: "onur-kurulu",
    eyebrow: "Sene başı hazırlık rehberi",
    title: "Onur Kurulu",
    description:
      "Onur genel kurulu seçimlerinden onur belgesi uygun görüşüne kadar kurulun yapısı ve çalışma düzeni.",
    icon: "workspace_premium",
    accent: "bg-tertiary-container text-on-tertiary-container",
    sections: HONOR_SECTIONS,
    checklist: [
      "Her şubeden onur genel kurulu temsilcisi seçildi.",
      "Her sınıf seviyesinden Onur Kurulu öğrenci üyesi seçildi.",
      "Son sınıf düzeyinden ikinci başkan ve yedeği belirlendi.",
      "Kurul başkanı ve yedek öğretmen, öğretmenler kurulunca seçildi.",
      "Üyelerin gerekli nitelikleri taşıdığı kontrol edildi.",
      "Karar defteri ve aylık toplantı takvimi hazırlandı.",
      "Ek onur davranışları belirlenmişse kurula bildirildi.",
      "Onur belgesi teklif ve değerlendirme yöntemi üyelere açıklandı.",
      "İlk toplantı yapıldı; görev paylaşımı karar defterine işlendi.",
      "Ödül ve Disiplin Kuruluyla bilgi akışı planlandı.",
    ],
  },
};

function Checklist({ note }: { note: Note }) {
  const storageKey = `bilgi-notu-kontrol-${note.key}`;
  const [checked, setChecked] = useState<Record<number, boolean>>({});

  useEffect(() => {
    try {
      const saved = window.localStorage.getItem(storageKey);
      setChecked(saved ? (JSON.parse(saved) as Record<number, boolean>) : {});
    } catch {
      setChecked({});
    }
  }, [storageKey]);

  const completed = Object.values(checked).filter(Boolean).length;
  const toggle = (index: number) => {
    setChecked((current) => {
      const next = { ...current, [index]: !current[index] };
      window.localStorage.setItem(storageKey, JSON.stringify(next));
      return next;
    });
  };

  return (
    <section id={`${note.key}-kontrol`} className="scroll-mt-24">
      <div className="overflow-hidden rounded-shape-lg border border-outline-variant bg-surface-container-lowest shadow-elevation-1">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-outline-variant bg-surface-container-low px-5 py-4">
          <div>
            <p className="text-title-large font-semibold text-on-surface">
              Hazırlık kontrol listesi
            </p>
            <p className="mt-1 text-body-small text-on-surface-variant">
              İşaretlemeler yalnızca bu cihazda saklanır.
            </p>
          </div>
          <span className="rounded-full bg-primary-container px-3 py-1 text-label-large font-semibold text-on-primary-container">
            {completed} / {note.checklist.length}
          </span>
        </div>
        <ul className="divide-y divide-outline-variant/70">
          {note.checklist.map((item, index) => (
            <li key={item}>
              <label className="flex min-h-14 cursor-pointer items-start gap-3 px-5 py-3 transition hover:bg-surface-container-low">
                <input
                  type="checkbox"
                  checked={Boolean(checked[index])}
                  onChange={() => toggle(index)}
                  className="mt-0.5 h-5 w-5 shrink-0 accent-primary"
                />
                <span
                  className={`text-body-medium ${
                    checked[index] ? "text-on-surface-variant line-through" : "text-on-surface"
                  }`}
                >
                  {item}
                </span>
              </label>
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}

export default function BilgiNotlariPage() {
  const { notTuru } = useParams();
  const noteKey: NoteKey = notTuru === "onur-kurulu" ? "onur-kurulu" : "disiplin-kurulu";
  const note = NOTES[noteKey];
  const toc = useMemo(
    () => [
      ...note.sections.map((section) => ({
        id: `${note.key}-${section.id}`,
        title: section.title,
      })),
      { id: `${note.key}-kontrol`, title: "Hazırlık kontrol listesi" },
    ],
    [note],
  );

  return (
    <div className="space-y-5">
      <header>
        <p className="text-label-large font-semibold uppercase tracking-wider text-primary">
          Başvuru kitaplığı
        </p>
        <h1 className="mt-1 text-headline-medium font-semibold tracking-tight text-on-surface">
          Kurul bilgi notları
        </h1>
        <p className="mt-2 max-w-3xl text-body-large text-on-surface-variant">
          Öğretim yılı başındaki kurul işlemlerini hazırlamak ve toplantı sırasında hızlıca
          başvurmak için düzenlenmiş uygulama rehberleri.
        </p>
      </header>

      <nav aria-label="Bilgi notu seçimi" className="grid gap-3 md:grid-cols-2">
        {Object.values(NOTES).map((item) => (
          <NavLink
            key={item.key}
            to={`/bilgi-notlari/${item.key}`}
            className={({ isActive }) =>
              `group rounded-shape-lg border p-4 transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary ${
                isActive || (!notTuru && item.key === "disiplin-kurulu")
                  ? "border-primary bg-primary-container/40 shadow-elevation-1"
                  : "border-outline-variant bg-surface-container-lowest hover:border-primary/60 hover:shadow-elevation-1"
              }`
            }
          >
            <div className="flex items-start gap-3">
              <span
                className={`flex h-11 w-11 shrink-0 items-center justify-center rounded-shape-md ${item.accent}`}
              >
                <Icon name={item.icon} size="xl" filled />
              </span>
              <span className="min-w-0">
                <span className="block text-title-medium font-semibold text-on-surface">
                  {item.title}
                </span>
                <span className="mt-1 block text-body-small text-on-surface-variant">
                  {item.key === "disiplin-kurulu"
                    ? "Kuruluş, görevler, süreç ve sene başı planı"
                    : "Seçimler, görevler ve onur belgesi süreci"}
                </span>
              </span>
              <Icon
                name="arrow_forward"
                className="ml-auto text-on-surface-variant transition group-hover:translate-x-1 group-hover:text-primary"
              />
            </div>
          </NavLink>
        ))}
      </nav>

      <div className={`overflow-hidden rounded-shape-lg p-5 sm:p-7 ${note.accent}`}>
        <div className="flex flex-col gap-5 sm:flex-row sm:items-center">
          <span className="flex h-16 w-16 shrink-0 items-center justify-center rounded-shape-lg bg-surface-container-lowest/80 shadow-elevation-1">
            <Icon name={note.icon} size="4xl" filled />
          </span>
          <div>
            <p className="text-label-large font-semibold uppercase tracking-wider opacity-80">
              {note.eyebrow}
            </p>
            <h2 className="mt-1 text-headline-small font-semibold">{note.title}</h2>
            <p className="mt-2 max-w-4xl text-body-large opacity-90">{note.description}</p>
          </div>
        </div>
      </div>

      <div className="grid items-start gap-5 xl:grid-cols-pane-sm">
        <aside className="rounded-shape-lg border border-outline-variant bg-surface-container-lowest p-3 xl:sticky xl:top-20">
          <p className="px-3 pb-2 pt-1 text-label-small font-semibold uppercase tracking-wider text-on-surface-variant">
            Bu notta
          </p>
          <nav aria-label={`${note.title} içindekiler`}>
            <ol className="space-y-0.5">
              {toc.map((item, index) => (
                <li key={item.id}>
                  <a
                    href={`#${item.id}`}
                    className="flex min-h-10 items-center gap-3 rounded-shape-sm px-3 py-2 text-body-medium text-on-surface-variant transition hover:bg-primary/8 hover:text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
                  >
                    <span className="w-5 text-label-small font-bold text-primary">
                      {String(index + 1).padStart(2, "0")}
                    </span>
                    {item.title}
                  </a>
                </li>
              ))}
            </ol>
          </nav>
        </aside>

        <article className="min-w-0 space-y-4">
          {note.sections.map((section, index) => (
            <section
              key={section.id}
              id={`${note.key}-${section.id}`}
              className="scroll-mt-24 rounded-shape-lg border border-outline-variant bg-surface-container-lowest p-5 shadow-elevation-1 sm:p-6"
            >
              <div className="mb-4 flex items-start gap-3">
                <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-shape-sm bg-primary text-label-medium font-bold text-on-primary">
                  {String(index + 1).padStart(2, "0")}
                </span>
                <h3 className="pt-0.5 text-title-large font-semibold text-on-surface">
                  {section.title}
                </h3>
              </div>
              <div className="space-y-4 text-body-large leading-7 text-on-surface-variant [&_li]:ml-5 [&_li]:mt-2 [&_ol]:list-decimal [&_ul]:list-disc [&_strong]:font-semibold [&_strong]:text-on-surface">
                {section.content}
              </div>
            </section>
          ))}

          <Checklist note={note} />

          <footer className="rounded-shape-md border border-outline-variant bg-surface-container-low p-4 text-body-small leading-5 text-on-surface-variant">
            <p className="flex items-start gap-2">
              <Icon name="info" size="lg" className="shrink-0 text-primary" />
              <span>
                Bu içerik bilgilendirme ve planlama amaçlıdır; bağlayıcı hüküm değildir. Uygulamada
                yürürlükteki güncel mevzuat ve okulunuzun resmî çalışma takvimi esas alınmalıdır.
              </span>
            </p>
          </footer>
        </article>
      </div>
    </div>
  );
}
