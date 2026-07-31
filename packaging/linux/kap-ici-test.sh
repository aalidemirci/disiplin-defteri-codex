#!/usr/bin/env bash
# =============================================================================
# kap-ici-test.sh — TEMİZ bir Debian kabında .deb kurulum provası
# =============================================================================
# `test-kurulum.sh` tarafından debian:11 ve debian:12 kaplarının İÇİNDE
# çalıştırılır (tasarım §8/§11: "iki Pardus provası" — Pardus 21 bullseye,
# Pardus 23 bookworm tabanlıdır).
#
# Sınananlar:
#   1. dpkg -i + apt-get -f install ile bağımlılıkların gerçekten çözülmesi
#   2. `--autotest` → ÇIKIŞ KODU 0 (açılış zinciri: kilit, yedek, göç, sunucu)
#   3. `--pdf-duman` → Türkçe metinli PDF üretimi + pypdf ile geri okuma
#   4. Dosya yerleşimi (menü kaydı, ikon, /usr/bin bağlantısı)
#   5. Temiz kaldırma
# =============================================================================
set -euo pipefail

export DEBIAN_FRONTEND=noninteractive

# Yerelde `test-kurulum.sh` paketleri /paketler'e bağlar; CI'da artefakt başka
# bir dizine iner → PAKET_DIZINI ile geçersiz kılınır.
PAKET_DIZINI="${PAKET_DIZINI:-/paketler}"

echo "== dağıtım"
head -2 /etc/os-release

echo "== apt-get update"
apt-get update -qq

DEB="$(find "$PAKET_DIZINI" -maxdepth 1 -name '*.deb' | sort | head -1)"
[ -n "$DEB" ] || { echo "HATA: $PAKET_DIZINI içinde .deb yok" >&2; exit 1; }
echo "== paket: $DEB"

echo "== dpkg -i (bağımlılıklar eksik olabilir)"
dpkg -i "$DEB" || true

echo "== apt-get -f install (bağımlılık çözümü)"
apt-get -f install -y -qq

echo "== paket durumu"
dpkg -s disiplin-defteri | grep -E '^(Package|Version|Status|Depends)'

echo "== dosya yerleşimi"
test -x /opt/disiplin-defteri/disiplin-defteri
test -L /usr/bin/disiplin-defteri
test -f /usr/share/applications/disiplin-defteri.desktop
test -f /usr/share/icons/hicolor/48x48/apps/disiplin-defteri.png

echo "== --pdf-duman (Türkçe PDF + font doğrulaması)"
disiplin-defteri --pdf-duman /tmp/duman.pdf
test -s /tmp/duman.pdf

echo "== --autotest (açılış zinciri; çıkış kodu 0 beklenir)"
disiplin-defteri --autotest

echo "== ikinci --autotest (var olan veritabanı üzerinde)"
disiplin-defteri --autotest

echo "== kaldırma"
dpkg -r disiplin-defteri
test ! -e /opt/disiplin-defteri
test ! -e /usr/bin/disiplin-defteri

echo "TAMAM"
