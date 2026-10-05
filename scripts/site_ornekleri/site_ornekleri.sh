#!/usr/bin/env bash
# =============================================================================
# okulapp.org program sayfası için ekran görüntüleri + örnek evrak (UYDURMA veriyle)
# =============================================================================
# Tek komut, beş adım; hepsi Docker'da, host'a Python/Node kurulmaz:
#   1. ön yüz derlemesi (frontend/dist — programın sunduğu arayüz);
#   2. geçici Playwright imajı (Microsoft'un resmî imajı + playwright paketi + Inter yazı
#      tipi + pdftoppm). Depo bağımlılığı DEĞİLDİR: requirements'a, spec'e, pakete
#      girmez; yalnız bu betiğin yerel imajıdır (`docker rmi dd-ekran-playwright:…`);
#   3. backend kabında program: örnek okul (`ornek_okul.py`) + örnek evrak PDF'leri,
#      ardından masaüstü açılış yolundan sunucu 127.0.0.1'de (`ornek_sunucu.py`);
#   4. Playwright kabı AYNI kabın ağ ad alanında ekranları çeker ve evrakın ilk sayfasını
#      görsele çevirir (`ekran_cekimi.py`); dışarıya hiçbir port açılmaz;
#   5. PNG → WebP (`webp_cevir.py`, backend kabında Pillow).
#
#     bash scripts/site_ornekleri/site_ornekleri.sh
#     DD_SITE_DERLE=0 bash scripts/site_ornekleri/site_ornekleri.sh   # ön yüzü derleme
#
# Çıktı: dist/site-ornekleri/{ekranlar/webp,ornek-evrak}/ (dist/ .gitignore'dadır).
# Veri dizini kabın /tmp'sindedir ve kapla silinir; depoya veri girmez.
# =============================================================================
set -euo pipefail
export MSYS_NO_PATHCONV=1
cd "$(dirname "${BASH_SOURCE[0]}")/../.."

CIKTI="dist/site-ornekleri"
AD="dd-site-ornekleri"
PW_SURUM="1.49.1"
PW_TABAN="mcr.microsoft.com/playwright/python:v${PW_SURUM}-noble"
PW_IMAJ="dd-ekran-playwright:${PW_SURUM}"
# Git Bash (Windows) bağlama yolu için sürücü harfli yol verir; Linux'ta düz pwd.
KOK="$(pwd -W 2>/dev/null || pwd)"

temizle() {
  docker rm -f "$AD" >/dev/null 2>&1 || true
  rm -f "$CIKTI/durum.json" "$CIKTI/bitti"
}
trap temizle EXIT
temizle
rm -rf "$CIKTI"
mkdir -p "$CIKTI"

if [ "${DD_SITE_DERLE:-1}" = "1" ]; then
  echo "== 1/5 ön yüz derlemesi"
  docker compose run --rm -T frontend sh -c \
    "[ -f node_modules/.package-lock.json ] || npm ci --no-audit --no-fund; npm run build" >/dev/null
else
  echo "== 1/5 ön yüz derlemesi atlandı (DD_SITE_DERLE=0; frontend/dist kullanılır)"
fi

echo "== 2/5 geçici Playwright imajı ($PW_IMAJ)"
docker build -q -t "$PW_IMAJ" - >/dev/null <<EOF
FROM $PW_TABAN
RUN pip install --no-cache-dir --break-system-packages playwright==$PW_SURUM \\
 && apt-get update \\
 && apt-get install -y --no-install-recommends fonts-inter poppler-utils \\
 && rm -rf /var/lib/apt/lists/*
EOF

echo "== 3/5 örnek okul + örnek evrak + program (backend kabı $AD)"
docker compose run -d --name "$AD" -w /repo -e PYTHONPATH=/repo backend \
  python scripts/site_ornekleri/ornek_sunucu.py --cikti "$CIKTI" >/dev/null
for _ in $(seq 1 600); do
  if docker logs "$AD" 2>&1 | grep -q "^HAZIR"; then break; fi
  if [ "$(docker inspect -f '{{.State.Running}}' "$AD" 2>/dev/null)" != "true" ]; then
    docker logs "$AD" >&2
    echo "HATA: program kabı durdu" >&2
    exit 1
  fi
  sleep 1
done
docker logs "$AD" 2>&1 | grep -E "^(TOHUM|EVRAK|HAZIR)"

echo "== 4/5 ekran görüntüleri + evrak önizlemeleri (Playwright, $AD ağında)"
docker run --rm --network "container:$AD" -v "$KOK:/repo" -w /repo \
  -e LANG=tr_TR.UTF-8 -e LANGUAGE=tr "$PW_IMAJ" \
  python scripts/site_ornekleri/ekran_cekimi.py --cikti "$CIKTI"

echo "== 5/5 WebP"
docker compose run --rm -T -w /repo backend \
  python scripts/site_ornekleri/webp_cevir.py --cikti "$CIKTI"
rm -rf "$CIKTI/ekranlar/png"
echo "Çıktı: $CIKTI"
