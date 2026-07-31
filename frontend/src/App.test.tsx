// Kabuk + yönlendirme testi (Görev 3 → F4-D4'te yeni rotalara uyarlandı).
// Pinlenen davranışlar: (1) kurulum kapısı — `setup_completed=false` iken her rota
// sihirbaza düşer, `true` iken panel açılır; (2) kabuk gezinme çubuğunun beş ana
// bölümü; (3) kaldırılan "Kurullar"/"Karar Tipleri" sekmelerinin geri gelmemesi;
// (4) M3 token bütünlüğü — kaynakta kullanılan şekil/opaklık sınıflarının Tailwind
// çıktısında gerçekten üretildiği (F4-D5 bulgu 14/15).
// Auth yok: rol/oturum senaryosu YOKTUR (tek kullanıcılı masaüstü).

import { readdirSync, readFileSync } from "node:fs";
import path from "node:path";

import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import postcss from "postcss";
import { MemoryRouter } from "react-router-dom";
import tailwindcss from "tailwindcss";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ConfirmProvider } from "./ui/ConfirmProvider";
import { SnackbarProvider } from "./ui/SnackbarProvider";
import type { SetupStatus } from "./modules/okul/api";

const okulApiMock = vi.hoisted(() => ({
  getSetupStatus: vi.fn(),
  getSchoolConfig: vi.fn(),
  updateSchoolConfig: vi.fn(),
  completeSetup: vi.fn(),
  getGradeLevels: vi.fn(),
  listSchoolYears: vi.fn(),
  createSchoolYear: vi.fn(),
  activateSchoolYear: vi.fn(),
  listHolidays: vi.fn(),
  createHoliday: vi.fn(),
  deleteHoliday: vi.fn(),
  seedHolidays: vi.fn(),
  listStudents: vi.fn(),
  createStudent: vi.fn(),
  updateStudent: vi.fn(),
  deleteStudent: vi.fn(),
  listPersonnel: vi.fn(),
  createPersonnel: vi.fn(),
  updatePersonnel: vi.fn(),
  deletePersonnel: vi.fn(),
}));

const deadlinesApiMock = vi.hoisted(() => ({ list: vi.fn() }));

// Yalnız istemci nesneleri taklit edilir; etiket sabitleri (SEVERITY_ORDER,
// STAGE_TR …) gerçek kalsın diye `importOriginal` ile yayılır.
vi.mock("./modules/okul/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("./modules/okul/api")>();
  return { ...actual, okulApi: okulApiMock };
});

vi.mock("./modules/disiplin/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("./modules/disiplin/api")>();
  return {
    ...actual,
    disiplinApi: { ...actual.disiplinApi, listCases: vi.fn().mockResolvedValue([]) },
    deadlinesApi: deadlinesApiMock,
  };
});

import App from "./App";

const KURULU: SetupStatus = {
  setup_completed: true,
  school_name: "Örnek Anadolu Lisesi",
  has_active_school_year: true,
  student_count: 482,
  personnel_count: 37,
  holiday_count: 14,
};

const KURULMAMIS: SetupStatus = {
  ...KURULU,
  setup_completed: false,
  school_name: "",
  has_active_school_year: false,
  student_count: 0,
  personnel_count: 0,
  holiday_count: 0,
};

/** main.tsx ile aynı sağlayıcı zinciri — sayfalar snackbar/confirm bekliyor. */
function ekranaBas(yol = "/") {
  return render(
    <MemoryRouter initialEntries={[yol]}>
      <SnackbarProvider>
        <ConfirmProvider>
          <App />
        </ConfirmProvider>
      </SnackbarProvider>
    </MemoryRouter>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  okulApiMock.getSetupStatus.mockResolvedValue(KURULU);
  okulApiMock.getSchoolConfig.mockResolvedValue({
    school_name: "",
    province: "",
    district: "",
    principal_name: "",
    setup_completed: false,
  });
  okulApiMock.listSchoolYears.mockResolvedValue([]);
  okulApiMock.listHolidays.mockResolvedValue([]);
  okulApiMock.getGradeLevels.mockResolvedValue({
    levels: [
      { value: 9, label: "9" },
      { value: 10, label: "10" },
    ],
    prep_enabled: false,
  });
  const bosSayfa = { count: 0, next: null, previous: null, results: [] };
  okulApiMock.listStudents.mockResolvedValue(bosSayfa);
  okulApiMock.listPersonnel.mockResolvedValue(bosSayfa);
  okulApiMock.getSetupStatus.mockResolvedValue(KURULU);
  deadlinesApiMock.list.mockResolvedValue([]);
});

describe("App — kurulum kapısı", () => {
  it("kurulum tamamlanmadıysa kök rotadan sihirbaza yönlendirir", async () => {
    okulApiMock.getSetupStatus.mockResolvedValue(KURULMAMIS);
    ekranaBas("/");
    expect(await screen.findByRole("heading", { name: "Kurulum sihirbazı" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Panel" })).not.toBeInTheDocument();
  });

  it("kurulum tamamlanmadıysa iç rotalardan da sihirbaza yönlendirir", async () => {
    okulApiMock.getSetupStatus.mockResolvedValue(KURULMAMIS);
    ekranaBas("/kisiler");
    expect(await screen.findByRole("heading", { name: "Kurulum sihirbazı" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Kişiler" })).not.toBeInTheDocument();
  });

  it("kurulum tamamlandıysa kök rotada panel açılır", async () => {
    ekranaBas("/");
    expect(await screen.findByRole("heading", { name: "Panel" })).toBeInTheDocument();
  });

  it("kurulum tamamlandıktan sonra sihirbaz elle açılabilir kalır", async () => {
    ekranaBas("/kurulum");
    expect(await screen.findByRole("heading", { name: "Kurulum sihirbazı" })).toBeInTheDocument();
  });

  it("durum okunamazsa kapı açılır (fail-open) — program kilitlenmez", async () => {
    okulApiMock.getSetupStatus.mockRejectedValue(new Error("ağ yok"));
    ekranaBas("/");
    expect(await screen.findByRole("heading", { name: "Panel" })).toBeInTheDocument();
  });
});

describe("App — kabuk gezinmesi", () => {
  it("ana bölüm bağlantılarını gösterir", async () => {
    ekranaBas("/");
    await screen.findByRole("heading", { name: "Panel" });
    for (const ad of ["Panel", "Disiplin", "Onur / Ödül", "Bilgi Notları", "Kişiler", "Ayarlar"]) {
      expect(screen.getByRole("link", { name: ad })).toBeInTheDocument();
    }
    expect(screen.getByRole("link", { name: "Hakkında ve Lisans" })).toHaveAttribute(
      "href",
      "/hakkinda",
    );
  });

  it("Bilgi Notları bağlantısı kurul rehberlerini açar", async () => {
    const user = userEvent.setup();
    ekranaBas("/");
    await user.click(await screen.findByRole("link", { name: "Bilgi Notları" }));
    expect(await screen.findByRole("heading", { name: "Kurul bilgi notları" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Disiplin Kurulu/ })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Onur Kurulu/ })).toBeInTheDocument();
  });

  it("Hakkında ve Lisans bağlantısı geliştirici ve kullanım koşullarını gösterir", async () => {
    const user = userEvent.setup();
    ekranaBas("/");
    await user.click(await screen.findByRole("link", { name: "Hakkında ve Lisans" }));
    expect(await screen.findByRole("heading", { name: "Hakkında ve Lisans" })).toBeInTheDocument();
    expect(screen.getByText("Ahmet Ali DEMİRCİ")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "aalidemirci@gmail.com" })).toHaveAttribute(
      "href",
      "mailto:aalidemirci@gmail.com",
    );
    expect(screen.getByText(/PolyForm Noncommercial License 1.0.0/)).toBeInTheDocument();
  });

  it("kaldırılan alt sayfa sekmelerini menüde göstermez", async () => {
    ekranaBas("/");
    await screen.findByRole("heading", { name: "Panel" });
    expect(screen.queryByRole("link", { name: "Kurullar" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Karar Tipleri" })).not.toBeInTheDocument();
  });

  it("Disiplin bağlantısına tıklayınca dosya listesi sayfası açılır", async () => {
    const user = userEvent.setup();
    ekranaBas("/");
    await user.click(await screen.findByRole("link", { name: "Disiplin" }));
    expect(await screen.findByRole("heading", { name: "Disiplin" })).toBeInTheDocument();
  });

  it("Kişiler bağlantısına tıklayınca sicil sayfası açılır", async () => {
    const user = userEvent.setup();
    ekranaBas("/");
    await user.click(await screen.findByRole("link", { name: "Kişiler" }));
    expect(await screen.findByRole("heading", { name: "Kişiler" })).toBeInTheDocument();
  });
});

// --- M3 token bütünlüğü ------------------------------------------------------
// Tailwind JIT, ölçekte KARŞILIĞI OLMAYAN bir token için sessizce hiç kural
// üretmez: `rounded-shape-full` ya da `bg-on-surface/8` yazılınca derleme
// patlamaz, sınıf yok sayılır ve kusur ancak gözle fark edilir (F4-D5 bulgu
// 14: köşeli gezinme sekmeleri, bulgu 15: hover geri bildirimi hiç oluşmaması).
// Bu test gerçek Tailwind çıktısını üretip kaynakta kullanılan her şekil ve
// opaklık token'ının CSS'te GERÇEKTEN yer aldığını doğrular.

// Vitest'in çalışma dizini proje kökü (`frontend/`) — `import.meta.url` burada
// dosya URL'i değil (vite-node sanal yolu), o yüzden cwd tabanlı çözülür.
const KOK = process.cwd();
const SRC_DIR = path.join(KOK, "src");

/** `src/` altındaki tüm ürün kaynağı (test dosyaları hariç). */
function kaynakDosyalari(dizin: string): string[] {
  const cikti: string[] = [];
  for (const girdi of readdirSync(dizin, { withFileTypes: true })) {
    const yol = path.join(dizin, girdi.name);
    if (girdi.isDirectory()) cikti.push(...kaynakDosyalari(yol));
    else if (/\.tsx?$/.test(girdi.name) && !/\.test\.tsx?$/.test(girdi.name)) cikti.push(yol);
  }
  return cikti;
}

// Şekil ölçeği: `rounded-shape-*`. Opaklık modifiyesi: yalnız SAYISAL olanlar —
// `bg-scrim/[0.32]` gibi keyfi değerler ölçeğe bakmadan üretildiği için kapsam dışı.
const SEKIL_DESENI = /\brounded-shape-[a-z0-9]+/g;
const OPAKLIK_DESENI =
  /\b(?:bg|text|border|ring|outline|fill|stroke|divide|from|via|to)-[a-z][a-z0-9-]*\/\d+\b/g;

/** Sınıf adının CSS'te üretilmiş bir seçici olarak var olup olmadığı.
 *
 * CSS çıktısında `/` kaçışlıdır (`.bg-primary\/8`). Sınıf bir varyantın ardından
 * da gelebilir (`hover:`, `placeholder:` → `.hover\:bg-primary\/8`), o yüzden
 * önünde `.` ya da kaçışlı `:` aranır.
 */
function uretildiMi(css: string, sinif: string): boolean {
  const desen = sinif
    .replace(/\//g, "\\/") // CSS kaçışı
    .replace(/[.\\/]/g, "\\$&"); // regex kaçışı
  return new RegExp(`(?:\\.|\\\\:)${desen}(?![\\w-])`).test(css);
}

describe("M3 token bütünlüğü", () => {
  it("kaynakta kullanılan şekil ve opaklık token'ları Tailwind çıktısında üretilir", async () => {
    const kullanilan = new Map<string, string>(); // sınıf → ilk görüldüğü dosya
    for (const dosya of kaynakDosyalari(SRC_DIR)) {
      const metin = readFileSync(dosya, "utf8");
      for (const desen of [SEKIL_DESENI, OPAKLIK_DESENI]) {
        for (const eslesme of metin.matchAll(desen)) {
          if (!kullanilan.has(eslesme[0]))
            kullanilan.set(eslesme[0], path.relative(SRC_DIR, dosya));
        }
      }
    }
    expect(kullanilan.size).toBeGreaterThan(0); // tarama gerçekten bir şey buldu

    const { css } = await postcss([
      tailwindcss({ config: path.join(KOK, "tailwind.config.js") }),
    ]).process("@tailwind utilities;", { from: undefined });

    const tanimsiz = [...kullanilan].filter(([sinif]) => !uretildiMi(css, sinif));
    expect(tanimsiz.map(([sinif, dosya]) => `${sinif} (${dosya})`)).toEqual([]);
  }, 60_000);
});
