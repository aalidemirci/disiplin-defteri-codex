// Yıl devri sihirbazı (F5-D3; tasarım §4.6) — ders yılı geçişini beş adımda
// yürütür. OYS'de birebir karşılığı YOKTUR, sıfırdan yazıldı.
//
// Adımlar: hazırlık (kapanmamış dosya uyarısı) → yeni ders yılı (aktiflik taşınır,
// dosya no ön eki değişir) → tatiller → kurullar (yeni yılda TANIMSIZ; md. 188
// gereği üyeler her yıl yeniden belirlenir, KOPYALANMAZ) → öğrenciler.
//
// Tasarım kararları:
// - Adımlar arası gezinme SERBESTTİR (KurulumPage ile aynı ilke): sihirbaz yarım
//   bırakılıp yeniden açılabilsin; her adım kendi durumunu canlı okur.
// - GERİ ALINAMAZ iki adım (yeni yılı aktifleştirme, toplu sınıf yükseltme)
//   ConfirmProvider onayından geçer ve sonucu ekranda kalıcı olarak özetlenir.
// - Disiplin tarafı verisi (kapanmamış dosyalar, kurul/onur kurulu tanımı) ayrı
//   disiplin uçlarından okunur — `apps.okul` `apps.disiplin`e bağlanmaz (api.ts).

import { useCallback, useEffect, useState } from "react";
import type { FormEvent, ReactNode } from "react";
import { Link } from "react-router-dom";

import { ApiError } from "../../lib/api";
import { formatDate, formatNumber } from "../../lib/format";
import { parseApiFieldErrors } from "../../lib/formErrors";
import Button from "../../ui/Button";
import Card from "../../ui/Card";
import { useConfirm } from "../../ui/ConfirmProvider";
import Icon from "../../ui/Icon";
import { SkeletonList } from "../../ui/Skeleton";
import { useSnackbar } from "../../ui/SnackbarProvider";
import Stepper from "../../ui/Stepper";
import type { StepperItem, StepperStatus } from "../../ui/Stepper";
import TextField from "../../ui/TextField";
import { disiplinApi } from "../disiplin/api";
import type { DisciplineCase } from "../disiplin/api";
import { odulApi } from "../odul/api";
import { yilDevriApi } from "./api";
import type { PromotionReport, RolloverResult, YearRolloverStatus } from "./api";

const ADIMLAR = [
  { key: "hazirlik", label: "Hazırlık", icon: "fact_check" },
  { key: "yil", label: "Yeni ders yılı", icon: "calendar_add_on" },
  { key: "tatil", label: "Tatiller", icon: "event_busy" },
  { key: "kurul", label: "Kurullar", icon: "groups" },
  { key: "ogrenci", label: "Öğrenciler", icon: "group" },
] as const;

const SON_ADIM = ADIMLAR.length - 1;

/** Hata mesajını Türkçeleştirir: ApiError gövdesi varsa onu, yoksa yedek metni verir. */
function hataMesaji(err: unknown, yedek: string): string {
  return err instanceof ApiError ? err.message : yedek;
}

/** Kalıcı hata bandı — snackbar geçicidir, kalıcı durum satır içi gösterilir. */
function HataBandi({ mesaj }: { mesaj: string }) {
  return (
    <div
      role="alert"
      className="flex items-start gap-2 rounded-shape-sm bg-error-container px-4 py-3 text-body-medium text-on-error-container"
    >
      <Icon name="error" size="lg" />
      <span>{mesaj}</span>
    </div>
  );
}

/** Uyarı bandı — engel DEĞİL, dikkat çeker (kapanmamış dosyalar gibi). */
function UyariBandi({ children }: { children: ReactNode }) {
  return (
    <div
      role="alert"
      className="flex items-start gap-2 rounded-shape-sm bg-tertiary-container px-4 py-3 text-body-medium text-on-tertiary-container"
    >
      <Icon name="warning" size="lg" />
      <span>{children}</span>
    </div>
  );
}

/** Bilgi/mevzuat notu. */
function BilgiNotu({ children }: { children: ReactNode }) {
  return (
    <Card elevation={0} className="flex items-start gap-3 bg-surface-container p-4">
      <Icon name="info" className="shrink-0 text-primary" />
      <p className="text-body-small text-on-surface-variant">{children}</p>
    </Card>
  );
}

/** Adım sonucunun kalıcı özeti (yeşil/olumlu ton). */
function SonucBandi({ children }: { children: ReactNode }) {
  return (
    <div className="flex items-start gap-2 rounded-shape-sm bg-secondary-container px-4 py-3 text-body-medium text-on-secondary-container">
      <Icon name="check_circle" size="lg" />
      <span>{children}</span>
    </div>
  );
}

function AdimBasligi({ no, baslik, aciklama }: { no: number; baslik: string; aciklama: string }) {
  return (
    <div>
      <h2 className="text-title-large text-on-surface">{`${no}. ${baslik}`}</h2>
      <p className="mt-1 text-body-medium text-on-surface-variant">{aciklama}</p>
    </div>
  );
}

export default function YilDevriPage() {
  const snackbar = useSnackbar();

  const [adim, setAdim] = useState(0);
  const [durum, setDurum] = useState<YearRolloverStatus | null>(null);
  const [durumYukleniyor, setDurumYukleniyor] = useState(true);
  const [durumHatasi, setDurumHatasi] = useState<string | null>(null);
  // Bu oturumda yapılan devrin sonucu (adım özetleri + tatil sayıları buradan).
  const [devirSonucu, setDevirSonucu] = useState<RolloverResult | null>(null);

  const durumYukle = useCallback(() => {
    setDurumYukleniyor(true);
    yilDevriApi
      .getStatus()
      .then((d) => {
        setDurum(d);
        setDurumHatasi(null);
      })
      .catch((e: unknown) => setDurumHatasi(hataMesaji(e, "Devir durumu yüklenemedi.")))
      .finally(() => setDurumYukleniyor(false));
  }, []);
  useEffect(durumYukle, [durumYukle]);

  const adimDurumu = (i: number): StepperStatus => {
    if (i === 1 && devirSonucu !== null && i !== adim) return "done";
    if (i < adim) return "done";
    if (i === adim) return "current";
    return "upcoming";
  };

  const stepperItems: StepperItem[] = ADIMLAR.map((a, i) => ({
    key: a.key,
    label: a.label,
    icon: a.icon,
    status: adimDurumu(i),
  }));

  const devirTamamlandi = (sonuc: RolloverResult) => {
    setDevirSonucu(sonuc);
    snackbar.success(`'${sonuc.school_year.name}' aktif ders yılı oldu.`);
    durumYukle();
    setAdim(2);
  };

  return (
    <div className="space-y-6">
      <div className="dd-page-header">
        <div>
          <h1 className="dd-page-title">Yıl devri</h1>
          <p className="dd-page-description">
            Yeni ders yılına geçiş sihirbazı. Yeni yıl aktifleşince disiplin dosya numaraları yeni
            yılın ön ekiyle 1&apos;den başlar; <strong>eski dosya numaraları değişmez</strong>.
            Devam eden (kapanmamış) dosyalar devirden etkilenmez.
          </p>
        </div>
      </div>

      <Stepper items={stepperItems} ariaLabel="Yıl devri adımları" />

      {durumHatasi && <HataBandi mesaj={durumHatasi} />}

      {durumYukleniyor ? (
        <SkeletonList rows={4} />
      ) : (
        <>
          {adim === 0 && <HazirlikAdimi durum={durum} />}
          {adim === 1 && (
            <YeniYilAdimi durum={durum} sonuc={devirSonucu} onTamamlandi={devirTamamlandi} />
          )}
          {adim === 2 && <TatilAdimi sonuc={devirSonucu} />}
          {adim === 3 && <KurulAdimi />}
          {adim === 4 && <OgrenciAdimi />}
        </>
      )}

      <div className="flex flex-wrap items-center justify-between gap-3">
        <Button
          variant="text"
          icon="arrow_back"
          onClick={() => setAdim(adim - 1)}
          disabled={adim === 0}
        >
          Geri
        </Button>
        <p className="text-label-medium text-on-surface-variant">
          Adım {adim + 1} / {ADIMLAR.length}
        </p>
        <Button
          variant="tonal"
          icon="arrow_forward"
          onClick={() => setAdim(adim + 1)}
          disabled={adim === SON_ADIM}
        >
          İleri
        </Button>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// 1. Hazırlık — mevcut durum + kapanmamış dosya UYARISI (engel değil)
// ---------------------------------------------------------------------------
function HazirlikAdimi({ durum }: { durum: YearRolloverStatus | null }) {
  const [acikDosyalar, setAcikDosyalar] = useState<DisciplineCase[] | null>(null);
  const [hata, setHata] = useState<string | null>(null);

  useEffect(() => {
    let iptal = false;
    disiplinApi
      .listCases({ onlyOpen: true })
      .then((rows) => {
        if (!iptal) setAcikDosyalar(rows);
      })
      .catch((e: unknown) => {
        if (!iptal) setHata(hataMesaji(e, "Kapanmamış dosyalar okunamadı."));
      });
    return () => {
      iptal = true;
    };
  }, []);

  return (
    <div className="space-y-6">
      <AdimBasligi
        no={1}
        baslik="Hazırlık"
        aciklama="Devirden önce mevcut durumu gözden geçirin. Bu adım hiçbir şey değiştirmez."
      />

      <Card elevation={1} className="p-6">
        <p className="text-title-medium text-on-surface">Mevcut durum</p>
        <dl className="mt-4 grid grid-cols-1 gap-4 sm:grid-cols-3">
          <div>
            <dt className="text-label-small text-on-surface-variant">Aktif ders yılı</dt>
            <dd className="text-body-large text-on-surface">
              {durum?.active_school_year ? durum.active_school_year.name : "Tanımsız"}
            </dd>
            {durum?.active_school_year && (
              <dd className="text-label-small text-on-surface-variant">
                {formatDate(durum.active_school_year.start_date)} –{" "}
                {formatDate(durum.active_school_year.end_date)}
              </dd>
            )}
          </div>
          <div>
            <dt className="text-label-small text-on-surface-variant">Aktif öğrenci</dt>
            <dd className="text-body-large text-on-surface">
              {formatNumber(durum?.active_student_count ?? 0)}
            </dd>
          </div>
          <div>
            <dt className="text-label-small text-on-surface-variant">Sınıfı girilmemiş öğrenci</dt>
            <dd className="text-body-large text-on-surface">
              {formatNumber(durum?.students_without_level ?? 0)}
            </dd>
          </div>
        </dl>
      </Card>

      {hata && <HataBandi mesaj={hata} />}

      <Card elevation={1} className="p-6">
        <p className="text-title-medium text-on-surface">Kapanmamış disiplin dosyaları</p>
        {acikDosyalar === null ? (
          <SkeletonList rows={2} className="mt-4" />
        ) : acikDosyalar.length === 0 ? (
          <p className="mt-2 text-body-medium text-on-surface-variant">
            Kapanmamış dosya yok. Devir için engel bulunmuyor.
          </p>
        ) : (
          <div className="mt-3 space-y-3">
            <UyariBandi>
              <strong>{formatNumber(acikDosyalar.length)} dosya</strong> hâlâ açık. Bu bir{" "}
              <strong>engel değildir</strong> — disiplin süreci ders yılını aşabilir; dosyalar eski
              numaralarıyla açık kalır ve işlemleri devirden sonra da sürdürülebilir.
            </UyariBandi>
            <ul className="divide-y divide-outline-variant/50">
              {acikDosyalar.map((d) => (
                <li key={d.id} className="flex flex-wrap items-center justify-between gap-3 py-3">
                  <div className="min-w-0">
                    <p className="text-body-medium text-on-surface">{d.case_no}</p>
                    <p className="text-label-small text-on-surface-variant">
                      {d.current_stage_display} · {formatDate(d.petition_date)}
                    </p>
                  </div>
                  <Link
                    to={`/disiplin/${d.id}`}
                    className="inline-flex min-h-12 items-center rounded-full px-3 text-label-large text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
                  >
                    Dosyayı aç
                  </Link>
                </li>
              ))}
            </ul>
          </div>
        )}
      </Card>
    </div>
  );
}

// ---------------------------------------------------------------------------
// 2. Yeni ders yılı — GERİ ALINAMAZ (aktiflik taşınır, dosya no ön eki değişir)
// ---------------------------------------------------------------------------
function YeniYilAdimi({
  durum,
  sonuc,
  onTamamlandi,
}: {
  durum: YearRolloverStatus | null;
  sonuc: RolloverResult | null;
  onTamamlandi: (sonuc: RolloverResult) => void;
}) {
  const confirm = useConfirm();
  const [ad, setAd] = useState(durum?.suggested_year.name ?? "");
  const [baslangic, setBaslangic] = useState(durum?.suggested_year.start_date ?? "");
  const [bitis, setBitis] = useState(durum?.suggested_year.end_date ?? "");
  const sonrakiYil = Number((durum?.suggested_year.start_date ?? "").slice(0, 4)) + 1;
  const [birinciDonemBitis, setBirinciDonemBitis] = useState(
    Number.isFinite(sonrakiYil) ? `${sonrakiYil}-01-16` : "",
  );
  const [ikinciDonemBaslangic, setIkinciDonemBaslangic] = useState(
    Number.isFinite(sonrakiYil) ? `${sonrakiYil}-02-02` : "",
  );
  const [tatilYukle, setTatilYukle] = useState(true);
  const [alanHatalari, setAlanHatalari] = useState<Record<string, string>>({});
  const [formHatasi, setFormHatasi] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const gonder = async (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setFormHatasi(null);
    const eksik: Record<string, string> = {};
    if (!ad.trim()) eksik.name = "Ders yılı adı yazılmalıdır.";
    if (!baslangic) eksik.start_date = "Başlangıç tarihi seçilmelidir.";
    if (!bitis) eksik.end_date = "Bitiş tarihi seçilmelidir.";
    if (!birinciDonemBitis) eksik.first_term_end = "1. dönem bitişi seçilmelidir.";
    if (!ikinciDonemBaslangic) eksik.second_term_start = "2. dönem başlangıcı seçilmelidir.";
    if (Object.keys(eksik).length > 0) {
      setAlanHatalari(eksik);
      return;
    }
    setAlanHatalari({});

    const eskiAd = durum?.active_school_year?.name;
    const onaylandi = await confirm({
      title: "Yeni ders yılına geç",
      message:
        `'${ad.trim()}' ders yılı oluşturulup AKTİF yapılsın mı?` +
        (eskiAd ? ` '${eskiAd}' pasife çekilecek.` : "") +
        ` Bundan sonra açılacak disiplin dosyaları '${ad.trim()}-0001' numarasıyla başlar;` +
        " eski dosya numaraları değişmez. Bu adım geri alınamaz.",
      confirmLabel: "Devret",
    });
    if (!onaylandi) return;

    setBusy(true);
    try {
      const result = await yilDevriApi.createSchoolYear({
        name: ad.trim(),
        start_date: baslangic,
        end_date: bitis,
        first_term_end: birinciDonemBitis,
        second_term_start: ikinciDonemBaslangic,
        seed_holidays: tatilYukle,
      });
      onTamamlandi(result);
    } catch (err) {
      const alanlar = parseApiFieldErrors(err) ?? {};
      if (Object.keys(alanlar).length > 0) setAlanHatalari(alanlar);
      else setFormHatasi(hataMesaji(err, "Yeni ders yılı oluşturulamadı."));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-6">
      <AdimBasligi
        no={2}
        baslik="Yeni ders yılı"
        aciklama="Yeni yıl oluşturulur ve AKTİF yapılır; aynı anda yalnız bir yıl aktif olabilir."
      />

      {sonuc ? (
        <SonucBandi>
          <strong>{sonuc.school_year.name}</strong> aktif ders yılı oldu
          {sonuc.previous_school_year_name
            ? ` ('${sonuc.previous_school_year_name}' pasife çekildi).`
            : "."}{" "}
          Yeni dosya numaraları <strong>{sonuc.school_year.name}-0001</strong> ile başlar.
        </SonucBandi>
      ) : (
        <Card elevation={1} className="p-6">
          <p className="text-title-medium text-on-surface">Yeni yıl bilgileri</p>
          <p className="mt-1 text-body-medium text-on-surface-variant">
            Tarihler önceki ders yılından bir yıl ileri taşınarak önerildi; okulunuzun takvimine
            göre düzeltebilirsiniz.
          </p>
          <form className="mt-4 space-y-4" onSubmit={gonder} noValidate>
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
              <TextField
                label="Ders yılı adı"
                required
                value={ad}
                onChange={(e) => setAd(e.target.value)}
                placeholder="2026-2027"
                error={alanHatalari.name}
              />
              <TextField
                label="Başlangıç"
                required
                type="date"
                value={baslangic}
                onChange={(e) => setBaslangic(e.target.value)}
                error={alanHatalari.start_date}
              />
              <TextField
                label="Bitiş"
                required
                type="date"
                value={bitis}
                onChange={(e) => setBitis(e.target.value)}
                error={alanHatalari.end_date}
              />
            </div>
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              <TextField
                label="1. dönem bitişi"
                required
                type="date"
                value={birinciDonemBitis}
                onChange={(e) => setBirinciDonemBitis(e.target.value)}
                error={alanHatalari.first_term_end}
              />
              <TextField
                label="2. dönem başlangıcı"
                required
                type="date"
                value={ikinciDonemBaslangic}
                onChange={(e) => setIkinciDonemBaslangic(e.target.value)}
                error={alanHatalari.second_term_start}
              />
            </div>
            <label className="flex min-h-12 items-center gap-3 text-body-medium text-on-surface">
              <input
                type="checkbox"
                checked={tatilYukle}
                onChange={(e) => setTatilYukle(e.target.checked)}
                className="h-5 w-5 accent-primary"
              />
              Yeni yılın resmî ve dini tatillerini otomatik yükle
            </label>
            {formHatasi && <HataBandi mesaj={formHatasi} />}
            <div className="flex justify-end">
              <Button type="submit" icon="calendar_add_on" disabled={busy}>
                {busy ? "Devrediliyor…" : "Yeni yıla devret"}
              </Button>
            </div>
          </form>
        </Card>
      )}

      <BilgiNotu>
        Dosya numarası aktif ders yılının adından türetilir. Devirden sonra açılan dosyalar yeni ön
        eki alır; eski yılın numaraları olduğu gibi kalır ve kapanmamış dosyalar açık kalmaya devam
        eder.
      </BilgiNotu>
    </div>
  );
}

// ---------------------------------------------------------------------------
// 3. Tatiller
// ---------------------------------------------------------------------------
function TatilAdimi({ sonuc }: { sonuc: RolloverResult | null }) {
  return (
    <div className="space-y-6">
      <AdimBasligi
        no={3}
        baslik="Tatil takvimi"
        aciklama="Yasal süreler iş günü üzerinden hesaplanır; yeni yılın tatilleri doğru olmalıdır."
      />

      {sonuc ? (
        <SonucBandi>
          {formatNumber(sonuc.holidays_created)} tatil eklendi,{" "}
          {formatNumber(sonuc.holidays_skipped)} kayıt zaten vardı.
        </SonucBandi>
      ) : (
        <UyariBandi>
          Bu oturumda tatil yükleme yapılmadı. Yeni yılın takvimini Ayarlar &gt; Tatiller ekranından
          kontrol edin.
        </UyariBandi>
      )}

      <BilgiNotu>
        Dini bayramlar Diyanet ilanından önce <strong>tahmini</strong> yüklenir; ilan çıkınca takvim
        ekranından düzeltin. Ara tatil ve yarıyıl tatili buraya <strong>girilmez</strong> — o
        günlerde memur çalışır, yasal süreler işler.
      </BilgiNotu>

      <Card elevation={1} className="p-6">
        <p className="text-title-medium text-on-surface">Takvimi gözden geçir</p>
        <p className="mt-1 text-body-medium text-on-surface-variant">
          Yeni yılın tatillerini listeleyip elle ekleme/silme yapabilirsiniz.
        </p>
        <Link
          to="/ayarlar?tab=tatiller"
          className="mt-3 inline-flex min-h-12 items-center gap-2 rounded-full bg-secondary-container px-6 text-label-large text-on-secondary-container focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
        >
          <Icon name="event_busy" size="lg" />
          Tatil takvimini aç
        </Link>
      </Card>
    </div>
  );
}

// ---------------------------------------------------------------------------
// 4. Kurullar — yeni yılda TANIMSIZ; üyeler her yıl yeniden belirlenir (md. 188)
// ---------------------------------------------------------------------------
function KurulAdimi() {
  const [kurulVar, setKurulVar] = useState<boolean | null>(null);
  const [onurVar, setOnurVar] = useState<boolean | null>(null);
  const [hata, setHata] = useState<string | null>(null);

  useEffect(() => {
    let iptal = false;
    Promise.all([disiplinApi.getCommittee(), odulApi.getBoard()])
      .then(([k, o]) => {
        if (iptal) return;
        setKurulVar(k.committee !== null);
        setOnurVar(o.board !== null);
      })
      .catch((e: unknown) => {
        if (!iptal) setHata(hataMesaji(e, "Kurul bilgileri okunamadı."));
      });
    return () => {
      iptal = true;
    };
  }, []);

  return (
    <div className="space-y-6">
      <AdimBasligi
        no={4}
        baslik="Kurullar"
        aciklama="Yeni ders yılının disiplin ve onur kurulları yeniden tanımlanmalıdır."
      />

      {hata && <HataBandi mesaj={hata} />}

      <BilgiNotu>
        Kurul üyeleri <strong>her ders yılı yeniden belirlenir</strong> (md. 185-188); bu yüzden
        sihirbaz eski yılın kurulunu kopyalamaz. Aktif yılda kurul tanımlanmadan kurul kararı
        işlenemez.
      </BilgiNotu>

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        <KurulKarti
          baslik="Ödül ve Disiplin Kurulu"
          ikon="gavel"
          tanimli={kurulVar}
          yol="/disiplin/kurul"
          eylem="Kurulu tanımla"
        />
        <KurulKarti
          baslik="Onur Kurulu"
          ikon="workspace_premium"
          tanimli={onurVar}
          yol="/odul"
          eylem="Onur kurulunu tanımla"
          ipucu='Onur Kurulu ekranında "Kurul Üyeleri" sekmesini kullanın.'
        />
      </div>
    </div>
  );
}

function KurulKarti({
  baslik,
  ikon,
  tanimli,
  yol,
  eylem,
  ipucu,
}: {
  baslik: string;
  ikon: string;
  tanimli: boolean | null;
  yol: string;
  eylem: string;
  ipucu?: string;
}) {
  return (
    <Card elevation={1} className="flex flex-col gap-3 p-6">
      <p className="flex items-center gap-2 text-title-medium text-on-surface">
        <Icon name={ikon} className="text-primary" />
        {baslik}
      </p>
      {tanimli === null ? (
        <SkeletonList rows={1} />
      ) : tanimli ? (
        <p className="text-body-medium text-on-surface-variant">
          Aktif ders yılı için tanımlı. Üyeleri gözden geçirmeyi unutmayın.
        </p>
      ) : (
        <p className="text-body-medium text-error">
          Aktif ders yılı için <strong>tanımsız</strong>.
        </p>
      )}
      {ipucu && <p className="text-label-small text-on-surface-variant">{ipucu}</p>}
      <Link
        to={yol}
        className="inline-flex min-h-12 w-fit items-center gap-2 rounded-full bg-secondary-container px-6 text-label-large text-on-secondary-container focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
      >
        <Icon name="arrow_forward" size="lg" />
        {eylem}
      </Link>
    </Card>
  );
}

// ---------------------------------------------------------------------------
// 5. Öğrenciler — önerilen yol yeniden import; alternatif toplu yükseltme
// ---------------------------------------------------------------------------
function OgrenciAdimi() {
  const confirm = useConfirm();
  const snackbar = useSnackbar();
  const [mezunEt, setMezunEt] = useState(true);
  const [onizleme, setOnizleme] = useState<PromotionReport | null>(null);
  const [uygulanan, setUygulanan] = useState<PromotionReport | null>(null);
  const [hata, setHata] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const onizlemeYukle = useCallback((graduate: boolean) => {
    yilDevriApi
      .promoteStudents({ apply: false, graduateFinalLevel: graduate })
      .then((r) => {
        setOnizleme(r);
        setHata(null);
      })
      .catch((e: unknown) => setHata(hataMesaji(e, "Yükseltme önizlemesi alınamadı.")));
  }, []);

  useEffect(() => {
    if (uygulanan === null) onizlemeYukle(mezunEt);
  }, [mezunEt, uygulanan, onizlemeYukle]);

  const uygula = async () => {
    const onaylandi = await confirm({
      title: "Toplu sınıf yükseltme",
      message:
        `${formatNumber(onizleme?.promoted ?? 0)} öğrenci bir üst sınıfa taşınacak` +
        (mezunEt
          ? `, 12. sınıftaki ${formatNumber(onizleme?.graduated ?? 0)} öğrenci "Ayrıldı" (mezun) olarak işaretlenecek`
          : "") +
        ". Bu işlem GERİ ALINAMAZ: öğrencilerin önceki sınıf bilgisi saklanmaz. Devam edilsin mi?",
      confirmLabel: "Yükselt",
    });
    if (!onaylandi) return;
    setBusy(true);
    try {
      const rapor = await yilDevriApi.promoteStudents({ apply: true, graduateFinalLevel: mezunEt });
      setUygulanan(rapor);
      snackbar.success(`${formatNumber(rapor.promoted)} öğrenci bir üst sınıfa taşındı.`);
    } catch (e) {
      setHata(hataMesaji(e, "Toplu sınıf yükseltme yapılamadı."));
    } finally {
      setBusy(false);
    }
  };

  const rapor = uygulanan ?? onizleme;

  return (
    <div className="space-y-6">
      <AdimBasligi
        no={5}
        baslik="Öğrenci listesi"
        aciklama="Yeni yılın öğrenci sicilini güncelleyin. Önerilen yol güncel Excel şablonunu yeniden aktarmaktır."
      />

      {hata && <HataBandi mesaj={hata} />}

      <Card elevation={1} className="p-6">
        <p className="flex items-center gap-2 text-title-medium text-on-surface">
          <Icon name="recommend" className="text-primary" />
          Önerilen: güncel Excel şablonunu yeniden aktar
        </p>
        <p className="mt-1 text-body-medium text-on-surface-variant">
          Yeni yılın &quot;Veli İletişim Bilgileri&quot; dosyası TCKN eşleşmesiyle güncellenir
          (upsert): sınıf/şube, numara ve veli bilgileri tek seferde doğru hale gelir. Nakil
          gelen/giden öğrenciler de böylece yerine oturur.
        </p>
        <Link
          to="/kisiler"
          className="mt-3 inline-flex min-h-12 w-fit items-center gap-2 rounded-full bg-secondary-container px-6 text-label-large text-on-secondary-container focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
        >
          <Icon name="upload_file" size="lg" />
          Kişiler ekranını aç
        </Link>
        <p className="mt-2 text-label-small text-on-surface-variant">
          Kişiler &gt; Öğrenciler ekranındaki içe aktarma panelinden dosyayı seçip önce
          <strong> önizleyin</strong>, sonra aktarın.
        </p>
      </Card>

      <Card elevation={1} className="p-6">
        <p className="flex items-center gap-2 text-title-medium text-on-surface">
          <Icon name="moving" className="text-primary" />
          Alternatif: toplu sınıf yükseltme
        </p>
        <p className="mt-1 text-body-medium text-on-surface-variant">
          Yeni liste elinizde yoksa mevcut kayıtlar bir üst sınıfa taşınabilir. Nakil ve kayıt
          değişiklikleri yansımaz — listeyi sonra düzeltmeniz gerekir.
        </p>

        <label className="mt-3 flex min-h-12 items-center gap-3 text-body-medium text-on-surface">
          <input
            type="checkbox"
            checked={mezunEt}
            disabled={uygulanan !== null}
            onChange={(e) => setMezunEt(e.target.checked)}
            className="h-5 w-5 accent-primary"
          />
          12. sınıfları mezun say (&quot;Ayrıldı&quot; olarak işaretle)
        </label>
        <p className="text-label-small text-on-surface-variant">
          Kayıt silinmez: geçmiş disiplin dosyaları erişilebilir kalır, sınıf bilgisi 12 olarak
          korunur; mezun öğrenciye yeni dosya açılamaz. İşaretlemezseniz 12. sınıflar olduğu gibi
          bırakılır.
        </p>

        {rapor === null ? (
          <SkeletonList rows={3} className="mt-4" />
        ) : (
          <div className="mt-4 space-y-3">
            {uygulanan !== null && (
              <SonucBandi>
                {formatNumber(uygulanan.promoted)} öğrenci yükseltildi,{" "}
                {formatNumber(uygulanan.graduated)} öğrenci mezun (Ayrıldı) olarak işaretlendi.
              </SonucBandi>
            )}
            <ul className="divide-y divide-outline-variant/50">
              {rapor.moves.map((m) => (
                <li key={m.from_level} className="flex items-center justify-between gap-3 py-2">
                  <span className="text-body-medium text-on-surface">
                    {m.from_level}. sınıf → {m.to_level}. sınıf
                  </span>
                  <span className="text-body-medium text-on-surface-variant">
                    {formatNumber(m.count)} öğrenci
                  </span>
                </li>
              ))}
              <li className="flex items-center justify-between gap-3 py-2">
                <span className="text-body-medium text-on-surface">
                  12. sınıf → {rapor.graduate_final_level ? "mezun (Ayrıldı)" : "değişmez"}
                </span>
                <span className="text-body-medium text-on-surface-variant">
                  {formatNumber(
                    rapor.graduate_final_level ? rapor.graduated : rapor.final_level_kept,
                  )}{" "}
                  öğrenci
                </span>
              </li>
            </ul>
            <p className="text-label-small text-on-surface-variant">
              Dokunulmayan kayıtlar: {formatNumber(rapor.skipped_inactive)} ayrılmış,{" "}
              {formatNumber(rapor.skipped_no_level)} sınıfsız,{" "}
              {formatNumber(rapor.skipped_out_of_range)} sınıfı 9-12 dışında.
            </p>
          </div>
        )}

        {uygulanan === null && (
          <div className="mt-4 flex justify-end">
            <Button icon="moving" onClick={uygula} disabled={busy || rapor === null}>
              {busy ? "Yükseltiliyor…" : "Toplu yükseltmeyi uygula"}
            </Button>
          </div>
        )}
      </Card>
    </div>
  );
}
