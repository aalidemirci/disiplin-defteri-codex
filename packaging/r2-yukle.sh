#!/usr/bin/env bash
# =============================================================================
# packaging/r2-yukle.sh — yayın paketlerini indir.okulapp.org'a (Cloudflare R2)
# =============================================================================
# Kullanım: r2-yukle.sh <paket-dizini> <sürüm>      (sürüm: 2026.9.0-beta.1)
#
# İki yerden çağrılır: paketleme.yml "yayin" işi (Release'in hemen ardından) ve
# r2-yukle.yml (var olan bir Release'in dosyalarını sonradan yeniden yüklemek
# için — ör. secret'lar Release'ten sonra eklendiyse).
#
# Kimlik: CLOUDFLARE_API_TOKEN + CLOUDFLARE_ACCOUNT_ID ortam değişkenleri.
# Yoksa İŞ DURMAZ: uyarı basılır ve 0 ile çıkılır (paketler Release'te kalır).
# =============================================================================
set -euo pipefail

DIZIN="${1:?paket dizini gerekli}"
SURUM="${2:?sürüm gerekli}"
R2_KOVA="${R2_KOVA:-okulapp-indirme}"
R2_ONEK="${R2_ONEK:-disiplin-defteri}"

if [ -z "${CLOUDFLARE_API_TOKEN:-}" ] || [ -z "${CLOUDFLARE_ACCOUNT_ID:-}" ]; then
    echo "::warning::CLOUDFLARE_API_TOKEN/ACCOUNT_ID tanımsız — R2 yüklemesi atlandı; paketler yalnız GitHub Release'te."
    exit 0
fi

cd "${DIZIN}"
for dosya in *; do
    # SHA256SUMS SÜRÜMLÜ adla yüklenir: kovada eski sürümlerin paketleri
    # durur, sabit ad her yayında onların özetini silerdi.
    case "${dosya}" in
        SHA256SUMS.txt) hedef="SHA256SUMS-${SURUM}.txt"; tip="text/plain; charset=utf-8" ;;
        *.exe)          hedef="${dosya}"; tip="application/vnd.microsoft.portable-executable" ;;
        *.zip)          hedef="${dosya}"; tip="application/zip" ;;
        *.deb)          hedef="${dosya}"; tip="application/vnd.debian.binary-package" ;;
        *.tar.gz)       hedef="${dosya}"; tip="application/gzip" ;;
        *)              echo "::warning::Türü bilinmeyen dosya R2'ye yüklenmedi: ${dosya}"; continue ;;
    esac
    echo "→ ${R2_ONEK}/${hedef}"
    npx --yes wrangler@4 r2 object put "${R2_KOVA}/${R2_ONEK}/${hedef}" \
        --file="${dosya}" --content-type="${tip}" --remote
done
echo "::notice::Paketler indir.okulapp.org/${R2_ONEK}/ altına yüklendi. Sıradaki elle iş: okulapp.org deposunda src/data/dd-release.json (sürüm, tarih ve boyutlar)."
