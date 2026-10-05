# Site örnekleri — ekran görüntüleri ve örnek evrak

okulapp.org program sayfasının (`/disiplin-defteri/`) ekran görüntülerini ve örnek
evrakını **uydurma veriyle** ve tek komutla yeniden üretir. Her şey Docker'da koşar;
host'a Python ya da Node kurulmaz. Düzen Kütüphane Defteri'nin
`scripts/ekran_goruntuleri/` betiğiyle aynıdır.

```bash
bash scripts/site_ornekleri/site_ornekleri.sh
DD_SITE_DERLE=0 bash scripts/site_ornekleri/site_ornekleri.sh   # ön yüzü yeniden derleme
```

Çıktı `dist/site-ornekleri/` altındadır (`dist/` `.gitignore`'dadır):

| Klasör | İçerik |
|---|---|
| `ekranlar/webp/` | 1440×900 WebP (2x çekilip küçültülür, kalite 88) |
| `ornek-evrak/` | Programın evrak motoruyla üretilen PDF'ler + ilk sayfanın 910×1287 WebP önizlemesi |

Siteye kopyalama: ekranlar `okulapp.org/public/disiplin-defteri/`, evrak
`okulapp.org/public/disiplin-defteri/ornek-evrak/` altına; sayfa
`okulapp.org/src/pages/disiplin-defteri/index.astro` (ekran ve belge listeleri orada).

## Adımlar

1. **Ön yüz derlemesi** — `frontend` kabında `npm run build` (programın sunduğu arayüz).
2. **Geçici Playwright imajı** — Microsoft'un resmî `mcr.microsoft.com/playwright/python`
   imajı + `playwright` paketi + Inter yazı tipi + `pdftoppm` (poppler). **Depo bağımlılığı
   değildir:** requirements'a, PyInstaller spec'ine ve pakete girmez
   (`docker rmi dd-ekran-playwright:1.49.1`). İlk koşu imajı indirir (~3,5 GB).
3. **Program** — `ornek_sunucu.py` backend kabında örnek okulu kurar (`ornek_okul.py`),
   örnek evrakı üretir ve programı **masaüstü açılış yolundan** kaldırır
   (`desktop.django_bootstrap`: açılışa özel oturum belirteci, göç, belirteç koruması
   denetimi); sunucu 127.0.0.1'de dinler. Güncelleme şeridi görüntüye girmesin diye
   çalışan sürüm `VERSION`'dan okunur ve denetim var olmayan bir depoya yönlendirilir.
4. **Görüntüler** — `ekran_cekimi.py` Playwright kabında, program kabının **ağ ad
   alanında** (`--network container:dd-site-ornekleri`) koşar; dışarıya port açılmaz.
   Türkçe yerel ayar, Europe/Istanbul, açık tema. Evrakın ilk sayfası `pdftoppm` ile
   görsele çevrilir.
5. **WebP** — `webp_cevir.py` backend kabında Pillow ile.

## Veri (hepsi uydurma — CLAUDE.md §11)

- Okul: "Örnek Anadolu Lisesi", Örnek ilçesi; müdür "Adı SOYADI".
- Personel görev adıyla ("Müdür YARDIMCISI", "Matematik ÖĞRETMENİ"…); öğrenciler ÖRNEK /
  DENEME / SINAMA / TASLAK / MİSAL soyadlarıyla. T.C. kimlik numarası girilmez.
- 2026-2027 ders yılı, iki dönem, resmî/dini tatiller; Ödül ve Disiplin Kurulu, Onur
  Genel Kurulu ve Onur Kurulu.
- Dört disiplin dosyası (yeni dilekçe · rehberlikte · müdür uyarısıyla kapanan · kurulda
  karar: biri onaylı ve tebliğli, biri müdür onayı bekliyor), beş onur belgesi teklifi,
  bir Onur Kurulu ve bir Ödül ve Disiplin Kurulu toplantısı.
- Tarihler sabittir (Eylül-Ekim 2026); program "bugün"ü kabın saatinden okur, süre
  sayaçları çekim gününe göre görünür.

Veri dizini kabın `/tmp`'sindedir ve kapla silinir; depoya veri girmez. Herkese açık
metinde gerçek kurum ve kişi yazılmaz.

## Bilinen farklar

- Yazı tipi: program Windows'ta "Segoe UI Variable" ile görünür; kapta o yazı tipi yoktur,
  arayüz yığınındaki **Inter** kullanılır. Evrak gömülü DejaVu Sans'la aynıdır.
- Görüntü, programın o sürümdeki arayüzüdür; ekran metni ya da düzen değişince betik
  yeniden koşulur ve sitedeki kareler ile açıklamaları birlikte güncellenir.
