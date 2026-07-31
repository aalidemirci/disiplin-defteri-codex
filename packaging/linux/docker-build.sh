#!/usr/bin/env bash
# =============================================================================
# packaging/linux/docker-build.sh — Linux paketlerini Docker içinde üretir
# =============================================================================
# Host'a hiçbir şey kurulmaz (CLAUDE.md "saf Docker" kuralı). Derleme kabı
# BİLİNÇLİ olarak `python:3.12-bullseye`'dır: glibc 2.31 = Pardus 21 tabanı.
# Daha yeni bir tabanda derlenen paket Pardus 21'de açılmaz.
#
# Kullanım (depo kökünden):
#     bash packaging/linux/docker-build.sh          # Qt dahil (gerçek paket)
#     DD_WITH_QT=0 bash packaging/linux/docker-build.sh   # hızlı doğrulama
#
# Çıktılar: dist/cikti/{*.deb, *.tar.gz, SHA256SUMS.txt, pdf-duman.pdf}
# =============================================================================
set -euo pipefail

DEPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
IMAJ="${DD_BUILD_IMAGE:-python:3.12-bullseye}"

echo "== derleme kabı: $IMAJ (Qt: ${DD_WITH_QT:-1})"
docker run --rm \
    -v "$DEPO:/repo" \
    -w /repo \
    -e "DD_WITH_QT=${DD_WITH_QT:-1}" \
    -e "DD_SKIP_PIP=${DD_SKIP_PIP:-0}" \
    -e "HOST_UID=$(id -u)" \
    -e "HOST_GID=$(id -g)" \
    "$IMAJ" \
    bash /repo/packaging/linux/build.sh
