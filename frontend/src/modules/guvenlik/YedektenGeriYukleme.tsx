// Otomatik yedeklerin durumu + yedekten geri yükleme.
//
// Geri yükleme iki adımdır (backend `services/restore_backup.py`): burada yedek
// doğrulanıp HAZIRLANIR; veritabanı ancak program yeniden açıldığında değişir.
// Bu yüzden işlem program yeniden başlatılana dek "Vazgeç" ile geri alınabilir ve
// eski veri silinmez (yedekler klasöründe `geri-yukleme-oncesi-…` olarak saklanır).
//
// Kart iki yerde durur: Ayarlar → Güvenlik ve kurulum sihirbazı (boş kurulumda /
// yeni bilgisayarda yedekten dönmek için). Uç kilit kapısından muaftır.

import { useCallback, useEffect, useId, useRef, useState } from "react";
import type { FormEvent } from "react";

import { ApiError } from "../../lib/api";
import { formatDate, todayIso } from "../../lib/format";
import Button from "../../ui/Button";
import Card from "../../ui/Card";
import { useConfirm } from "../../ui/ConfirmProvider";
import Icon from "../../ui/Icon";
import Select from "../../ui/Select";
import { useSnackbar } from "../../ui/SnackbarProvider";
import TextField from "../../ui/TextField";
import { yedekDegistiYayinla } from "./BekleyenGeriYuklemeBandi";
import { yedekApi } from "./yedekApi";
import type { YedekBilgisi, YedekOzeti } from "./yedekApi";

const TUR_ADI: Record<YedekBilgisi["kind"], string> = {
  daily: "günlük yedek",
  pre_migrate: "güncelleme öncesi yedek",
  transition: "parola işlemi öncesi yedek",
};

const ONAY_METNI =
  "Seçilen yedek, programı kapatıp yeniden açtığınızda şu anki kayıtların yerine konur. " +
  "Yedeğin alındığı tarihten sonra girilen HER kayıt (dosya, karar, evrak) programdan kalkar; " +
  "hazırlıktan sonra, programı yeniden açana dek girecekleriniz de buna dahildir. Şu anki " +
  "veri 14 gün boyunca yedekler klasöründe 'geri-yukleme-oncesi-…' adıyla saklanır. " +
  "Devam edilsin mi?";

function hataMesaji(err: unknown, yedek: string): string {
  return err instanceof ApiError ? err.message : yedek;
}

function yedekEtiketi(y: YedekBilgisi): string {
  // Dosya adı da yazılır: aynı günün birden çok yedeği (ör. parola işlemi öncesi) ayırt edilsin.
  const tarih = y.taken_on ? `${formatDate(y.taken_on)} — ` : "";
  return `${tarih}${TUR_ADI[y.kind]}${y.encrypted ? " (şifreli)" : ""} · ${y.name}`;
}

export default function YedektenGeriYukleme() {
  const snackbar = useSnackbar();
  const confirm = useConfirm();
  const dosyaAlaniId = useId();
  const dosyaAlani = useRef<HTMLInputElement>(null);

  const [ozet, setOzet] = useState<YedekOzeti | null>(null);
  const [yuklemeHatasi, setYuklemeHatasi] = useState<string | null>(null);
  const [secilenAd, setSecilenAd] = useState("");
  const [dosya, setDosya] = useState<File | null>(null);
  const [parola, setParola] = useState("");
  const [kurtarma, setKurtarma] = useState("");
  const [calisiyor, setCalisiyor] = useState(false);
  const [hata, setHata] = useState<string | null>(null);
  const [uyari, setUyari] = useState("");

  const tazele = useCallback(async () => {
    try {
      setOzet(await yedekApi.ozet());
      setYuklemeHatasi(null);
    } catch (err) {
      setYuklemeHatasi(hataMesaji(err, "Yedek bilgisi okunamadı."));
    }
  }, []);

  useEffect(() => {
    void tazele();
  }, [tazele]);

  const secilenYedek = ozet?.backups.find((y) => y.name === secilenAd) ?? null;
  // Dışarıdan seçilen dosyanın adı değiştirilmiş olabilir: yalnız ".sqlite3" uzantısı
  // "düz yedek" sayılır, gerisinde parola alanları gösterilir (boş bırakılabilir).
  const sifreli = dosya
    ? !dosya.name.toLowerCase().endsWith(".sqlite3")
    : !!secilenYedek?.encrypted;
  const secimVar = dosya !== null || secilenYedek !== null;

  function formuTemizle() {
    setSecilenAd("");
    setDosya(null);
    setParola("");
    setKurtarma("");
    if (dosyaAlani.current) dosyaAlani.current.value = "";
  }

  async function hazirla(e: FormEvent) {
    e.preventDefault();
    if (!secimVar || calisiyor) return;
    setHata(null);
    if (!(await confirm({ message: ONAY_METNI, confirmLabel: "Geri yüklemeyi hazırla" }))) return;
    setCalisiyor(true);
    try {
      const sirlar = { password: parola, recovery_key: kurtarma.trim() };
      const sonuc = dosya
        ? await yedekApi.dosyadanHazirla(dosya, sirlar)
        : await yedekApi.addanHazirla(secilenAd, sirlar);
      setOzet(sonuc);
      setUyari(sonuc.warning);
      formuTemizle();
      yedekDegistiYayinla();
      snackbar.success("Yedek hazırlandı. Programı kapatıp yeniden açın.");
    } catch (err) {
      setHata(hataMesaji(err, "Yedek hazırlanamadı."));
      // Liste bayatlamış olabilir (yedek klasörü program açıkken değişti: rotasyon,
      // parola işlemi, elle silme). Yeniden okunur; listede artık olmayan seçim düşer.
      if (!dosya) {
        const guncel = await yedekApi.ozet().catch(() => null);
        if (guncel) {
          setOzet(guncel);
          if (!guncel.backups.some((y) => y.name === secilenAd)) setSecilenAd("");
        }
      }
    } finally {
      setCalisiyor(false);
    }
  }

  async function vazgec() {
    setCalisiyor(true);
    try {
      setOzet(await yedekApi.vazgec());
      setUyari("");
      yedekDegistiYayinla();
      snackbar.success("Geri yüklemeden vazgeçildi; kayıtlarınız olduğu gibi kalır.");
    } catch (err) {
      snackbar.error(hataMesaji(err, "Geri yükleme iptal edilemedi."));
    } finally {
      setCalisiyor(false);
    }
  }

  return (
    <Card className="p-6">
      <div className="flex items-start gap-3">
        <Icon name="settings_backup_restore" className="mt-0.5 text-primary" />
        <div className="min-w-0 flex-1">
          <h2 className="text-title-large text-on-surface">Otomatik yedekler ve geri yükleme</h2>
          <p className="mt-2 text-body-medium text-on-surface-variant">
            Program her açılışta o günün yedeğini alır ve son 14 günü saklar. Uygulama parolası
            kuruluysa yedekler şifrelidir (<span className="font-mono">.ddbak</span>); kurulu
            değilse veritabanının kendisi gibi düz dosyadır (
            <span className="font-mono">.sqlite3</span>).
          </p>

          {yuklemeHatasi && (
            <p
              role="alert"
              className="mt-3 rounded-shape-md bg-error-container p-3 text-body-small text-on-error-container"
            >
              {yuklemeHatasi}
            </p>
          )}

          {ozet && (
            <>
              {ozet.last_daily_on ? (
                <>
                  <p className="mt-3 text-body-medium text-on-surface">
                    <span className="text-label-large">Son otomatik yedek: </span>
                    {formatDate(ozet.last_daily_on)}
                  </p>
                  {ozet.last_daily_on !== todayIso() && (
                    <p className="mt-2 rounded-shape-md bg-tertiary-container p-3 text-body-small text-on-tertiary-container">
                      Bugünün yedeği alınmamış. Program her açılışta o günün yedeğini alır; bu uyarı
                      yarın da görünürse yedekleme çalışmıyor demektir (disk dolu olabilir ya da
                      parola kuruluysa kilit henüz hiç açılmamıştır).
                    </p>
                  )}
                </>
              ) : (
                <p className="mt-3 rounded-shape-md bg-tertiary-container p-3 text-body-small text-on-tertiary-container">
                  Henüz otomatik yedek yok. İlk yedek, kayıt girildikten sonraki açılışta alınır.
                  Birkaç gün sonra burada hâlâ tarih görünmüyorsa yedekleme çalışmıyor demektir.
                </p>
              )}
              <p className="mt-1 break-all text-body-small text-on-surface-variant">
                Yedekler klasörü: <span className="font-mono">{ozet.backup_dir}</span> — yedekler
                aynı bilgisayardadır; disk arızasına karşı bu klasörü düzenli olarak USB belleğe
                kopyalayın.
              </p>

              {ozet.pending_restore && (
                <div
                  role="status"
                  className="mt-4 flex flex-wrap items-center gap-3 rounded-shape-md bg-secondary-container p-3 text-body-medium text-on-secondary-container"
                >
                  <span className="min-w-0 flex-1">
                    Bir yedek geri yükleme için hazır. Programı kapatıp yeniden açtığınızda
                    uygulanır.
                  </span>
                  <Button variant="outlined" icon="undo" onClick={vazgec} disabled={calisiyor}>
                    Vazgeç
                  </Button>
                </div>
              )}

              {uyari && (
                <p
                  role="alert"
                  className="mt-3 rounded-shape-md bg-tertiary-container p-3 text-body-small text-on-tertiary-container"
                >
                  {uyari}
                </p>
              )}

              <form onSubmit={hazirla} className="mt-5 flex flex-col gap-4">
                <h3 className="text-title-medium text-on-surface">Yedekten geri yükle</h3>
                <Select
                  label="Bu bilgisayardaki yedekler"
                  placeholder={ozet.backups.length ? "Yedek seçin" : "Yedek bulunamadı"}
                  options={ozet.backups.map((y) => ({ value: y.name, label: yedekEtiketi(y) }))}
                  value={secilenAd}
                  disabled={dosya !== null || ozet.backups.length === 0}
                  onChange={(e) => setSecilenAd(e.target.value)}
                />
                <div>
                  <label
                    htmlFor={dosyaAlaniId}
                    className="mb-1.5 block text-label-medium font-semibold text-on-surface-variant"
                  >
                    ya da başka bir yerdeki yedek dosyası (USB bellek vb.)
                  </label>
                  <input
                    id={dosyaAlaniId}
                    ref={dosyaAlani}
                    type="file"
                    accept=".ddbak,.sqlite3"
                    className="block w-full text-body-medium text-on-surface"
                    onChange={(e) => {
                      setDosya(e.target.files?.[0] ?? null);
                      setSecilenAd("");
                    }}
                  />
                  {dosya && (
                    <Button
                      variant="text"
                      type="button"
                      icon="close"
                      onClick={() => {
                        setDosya(null);
                        if (dosyaAlani.current) dosyaAlani.current.value = "";
                      }}
                    >
                      Dosyayı kaldır, listeden seç
                    </Button>
                  )}
                </div>

                {sifreli && (
                  <>
                    <TextField
                      label="Yedeğin alındığı tarihteki uygulama parolası"
                      type="password"
                      autoComplete="off"
                      value={parola}
                      onChange={(e) => setParola(e.target.value)}
                      helperText="Kilit açıksa ve yedek bu kurulumda alındıysa boş bırakabilirsiniz. Yedek başka bir kurulumdan geliyorsa, geri yüklemeden sonra geçerli parola bu parola olur."
                    />
                    <TextField
                      label="Parolayı hatırlamıyorsanız: kurtarma anahtarı"
                      autoComplete="off"
                      value={kurtarma}
                      onChange={(e) => setKurtarma(e.target.value)}
                    />
                  </>
                )}

                {hata && (
                  <p
                    role="alert"
                    className="rounded-shape-md bg-error-container p-3 text-body-small text-on-error-container"
                  >
                    {hata}
                  </p>
                )}

                <div>
                  <Button
                    type="submit"
                    variant="tonal"
                    icon="settings_backup_restore"
                    disabled={!secimVar || calisiyor}
                  >
                    {calisiyor ? "Yedek doğrulanıyor…" : "Geri yüklemeyi hazırla"}
                  </Button>
                </div>
              </form>
            </>
          )}
        </div>
      </div>
    </Card>
  );
}
