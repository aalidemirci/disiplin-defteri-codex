import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, it, vi } from "vitest";

import { ApiError } from "../../lib/api";
import { ConfirmProvider } from "../../ui/ConfirmProvider";
import { SnackbarProvider } from "../../ui/SnackbarProvider";
import type { YedekOzeti } from "./yedekApi";

const yedek = vi.hoisted(() => ({
  ozet: vi.fn(),
  addanHazirla: vi.fn(),
  dosyadanHazirla: vi.fn(),
  vazgec: vi.fn(),
}));

vi.mock("./yedekApi", () => ({ yedekApi: yedek }));
// Bugün = son yedeğin günü: "bugünün yedeği alınmamış" uyarısı ayrı testte sınanır.
vi.mock("../../lib/format", async (asil) => ({
  ...(await asil<typeof import("../../lib/format")>()),
  todayIso: () => "2026-11-13",
}));

import YedektenGeriYukleme from "./YedektenGeriYukleme";

const OZET: YedekOzeti = {
  backup_dir: "C:\\Veri\\DisiplinDefteri\\backups",
  last_daily_on: "2026-11-13",
  pending_restore: false,
  backups: [
    {
      name: "gunluk-2026-11-13.ddbak",
      kind: "daily",
      taken_on: "2026-11-13",
      size: 10,
      encrypted: true,
    },
    {
      name: "gunluk-2026-11-12.sqlite3",
      kind: "daily",
      taken_on: "2026-11-12",
      size: 10,
      encrypted: false,
    },
  ],
};

function ciz() {
  return render(
    <SnackbarProvider>
      <ConfirmProvider>
        <YedektenGeriYukleme />
      </ConfirmProvider>
    </SnackbarProvider>,
  );
}

async function onayla() {
  const dugmeler = await screen.findAllByRole("button", { name: "Geri yüklemeyi hazırla" });
  await userEvent.click(dugmeler[dugmeler.length - 1]);
}

beforeEach(() => {
  vi.clearAllMocks();
  yedek.ozet.mockResolvedValue(OZET);
});

it("son otomatik yedeğin tarihini ve yedekler klasörünü gösterir", async () => {
  ciz();

  expect(await screen.findByText("13.11.2026")).toBeInTheDocument();
  expect(screen.getByText(OZET.backup_dir)).toBeInTheDocument();
  expect(screen.getByRole("button", { name: /Geri yüklemeyi hazırla/ })).toBeDisabled();
});

it("hiç yedek yokken bunu açıkça söyler", async () => {
  yedek.ozet.mockResolvedValue({ ...OZET, last_daily_on: null, backups: [] });
  ciz();

  expect(await screen.findByText(/Henüz otomatik yedek yok/)).toBeInTheDocument();
  expect(screen.getByLabelText("Bu bilgisayardaki yedekler")).toBeDisabled();
});

it("düz yedeği parola sormadan, onay alarak hazırlar", async () => {
  yedek.addanHazirla.mockResolvedValue({
    ...OZET,
    pending_restore: true,
    message: "",
    warning: "",
  });
  ciz();

  await userEvent.selectOptions(
    await screen.findByLabelText("Bu bilgisayardaki yedekler"),
    "gunluk-2026-11-12.sqlite3",
  );
  expect(screen.queryByLabelText(/uygulama parolası/)).not.toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: /Geri yüklemeyi hazırla/ }));
  expect(yedek.addanHazirla).not.toHaveBeenCalled(); // önce onay
  await onayla();

  await waitFor(() =>
    expect(yedek.addanHazirla).toHaveBeenCalledWith("gunluk-2026-11-12.sqlite3", {
      password: "",
      recovery_key: "",
    }),
  );
  expect(await screen.findByText(/geri yükleme için hazır/)).toBeInTheDocument();
});

it("onay verilmezse hiçbir istek atılmaz", async () => {
  ciz();

  await userEvent.selectOptions(
    await screen.findByLabelText("Bu bilgisayardaki yedekler"),
    "gunluk-2026-11-12.sqlite3",
  );
  await userEvent.click(screen.getByRole("button", { name: /Geri yüklemeyi hazırla/ }));
  await userEvent.click(await screen.findByRole("button", { name: "Vazgeç" }));

  expect(yedek.addanHazirla).not.toHaveBeenCalled();
});

it("şifreli yedekte parolayı ister ve backend hatasını kalıcı gösterir", async () => {
  yedek.addanHazirla.mockRejectedValue(new ApiError(400, "invalid", "Parola hatalı."));
  ciz();

  await userEvent.selectOptions(
    await screen.findByLabelText("Bu bilgisayardaki yedekler"),
    "gunluk-2026-11-13.ddbak",
  );
  await userEvent.type(screen.getByLabelText(/tarihteki uygulama parolası/), "yanlis");
  await userEvent.click(screen.getByRole("button", { name: /Geri yüklemeyi hazırla/ }));
  await onayla();

  expect(await screen.findByText("Parola hatalı.")).toBeInTheDocument();
  expect(yedek.addanHazirla).toHaveBeenCalledWith("gunluk-2026-11-13.ddbak", {
    password: "yanlis",
    recovery_key: "",
  });
  // Seçim ve parola korunur: kullanıcı düzeltip yeniden deneyebilir.
  expect(screen.getByLabelText("Bu bilgisayardaki yedekler")).toHaveValue(
    "gunluk-2026-11-13.ddbak",
  );
});

it("dışarıdan seçilen dosyayı yükler", async () => {
  yedek.dosyadanHazirla.mockResolvedValue({
    ...OZET,
    pending_restore: true,
    message: "",
    warning: "Bu yedekteki alanlar şifreli.",
  });
  ciz();
  const dosya = new File(["x"], "usb-yedek.sqlite3");

  await userEvent.upload(await screen.findByLabelText(/başka bir yerdeki yedek dosyası/), dosya);
  await userEvent.click(screen.getByRole("button", { name: /Geri yüklemeyi hazırla/ }));
  await onayla();

  await waitFor(() =>
    expect(yedek.dosyadanHazirla).toHaveBeenCalledWith(dosya, { password: "", recovery_key: "" }),
  );
  expect(await screen.findByText("Bu yedekteki alanlar şifreli.")).toBeInTheDocument();
});

it("hazırlanmış geri yüklemeden vazgeçilebilir", async () => {
  yedek.ozet.mockResolvedValue({ ...OZET, pending_restore: true });
  yedek.vazgec.mockResolvedValue(OZET);
  ciz();

  await userEvent.click(await screen.findByRole("button", { name: "Vazgeç" }));

  await waitFor(() => expect(yedek.vazgec).toHaveBeenCalled());
  await waitFor(() =>
    expect(screen.queryByText(/geri yükleme için hazır/)).not.toBeInTheDocument(),
  );
});

it("yedek bilgisi okunamazsa hatayı gösterir", async () => {
  yedek.ozet.mockRejectedValue(new ApiError(500, "500", "Sunucu hatası."));
  ciz();

  expect(await screen.findByText("Sunucu hatası.")).toBeInTheDocument();
});

it("bugünün yedeği yoksa bunu söyler", async () => {
  yedek.ozet.mockResolvedValue({ ...OZET, last_daily_on: "2026-11-10" });
  ciz();

  expect(await screen.findByText("10.11.2026")).toBeInTheDocument();
  expect(screen.getByText(/Bugünün yedeği alınmamış/)).toBeInTheDocument();
});

it("bugünün yedeği varsa uyarı göstermez", async () => {
  ciz();

  expect(await screen.findByText("13.11.2026")).toBeInTheDocument();
  expect(screen.queryByText(/Bugünün yedeği alınmamış/)).not.toBeInTheDocument();
});

it("adı değiştirilmiş (uzantısı tanınmayan) dosyada da parola alanlarını gösterir", async () => {
  ciz();
  // Dosya seçicide "Tüm dosyalar" ile seçilmiş gibi: `accept` yalnız bir süzgeç önerisidir.
  const kullanici = userEvent.setup({ applyAccept: false });

  await kullanici.upload(
    await screen.findByLabelText(/başka bir yerdeki yedek dosyası/),
    new File(["x"], "okul-yedegi.bak"),
  );

  expect(screen.getByLabelText(/tarihteki uygulama parolası/)).toBeInTheDocument();
});

it("seçilen dosya kaldırılıp listeye dönülebilir", async () => {
  ciz();
  const liste = await screen.findByLabelText("Bu bilgisayardaki yedekler");

  await userEvent.upload(
    screen.getByLabelText(/başka bir yerdeki yedek dosyası/),
    new File(["x"], "usb.sqlite3"),
  );
  expect(liste).toBeDisabled();
  await userEvent.click(screen.getByRole("button", { name: /Dosyayı kaldır/ }));

  expect(liste).toBeEnabled();
  expect(screen.getByRole("button", { name: /Geri yüklemeyi hazırla/ })).toBeDisabled();
});

it("seçilen yedek artık yoksa listeyi yeniden okur ve bayat seçimi düşürür", async () => {
  // Windows saha denemesi (14.11.2026): parola kurulunca düz yedekler `.ddbak` olur;
  // kart eski adı gösterip "yedek bulunamadı" hatasında takılı kalıyordu.
  yedek.addanHazirla.mockRejectedValue(
    new ApiError(400, "validation_error", "Seçilen yedek yedekler klasöründe bulunamadı."),
  );
  ciz();
  const liste = await screen.findByLabelText("Bu bilgisayardaki yedekler");
  await userEvent.selectOptions(liste, "gunluk-2026-11-12.sqlite3");
  yedek.ozet.mockResolvedValue({
    ...OZET,
    backups: [{ ...OZET.backups[0], name: "gunluk-2026-11-12.ddbak", encrypted: true }],
  });

  await userEvent.click(screen.getByRole("button", { name: /Geri yüklemeyi hazırla/ }));
  await onayla();

  expect(await screen.findByText(/yedekler klasöründe bulunamadı/)).toBeInTheDocument();
  await waitFor(() => expect(liste).toHaveValue(""));
  expect(screen.getByRole("option", { name: /gunluk-2026-11-12\.ddbak/ })).toBeInTheDocument();
});
