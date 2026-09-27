#!/usr/bin/env bash
# =============================================================================
# apt-yedekli.sh — Debian güvenlik deposu bozuk bir sürümü listelediğinde apt
# kurulumunu yedek yollarla yeniden dener. build.sh ve kap-ici-test.sh `source`
# eder.
# =============================================================================
# 27.09.2026: bullseye-security indeksi libglib2.0 2.66.8-1+deb11u8'i listeliyor
# ama dosya hem deb.debian.org hem security.debian.org havuzunda 404 (bozuk /
# geri çekilmiş yükleme); bullseye henüz archive.debian.org'da da yok. Pardus 21
# (glibc 2.31) uyumu için tabanı DEĞİŞTİRMİYORUZ; sırayla:
#   1. varsayılan kurulum,
#   2. --no-upgrade — kurulu paketi (python:3.12-bullseye'de libglib2.0 hazır)
#      olmayan sürüme yükseltmeye çalışmadan yalnız eksikleri kur,
#   3. debian-security kaynağını devre dışı bırakıp ana depodaki sürümle kur
#      (temiz debian:11 kurulum provası; derleme/prova kabı, kullanıcı makinesi
#      değil — güvenlik güncellemesi son kullanıcının kendi sisteminde gelir).
# Kullanım:  apt_yedekli install -y -qq --no-install-recommends paket...

_apt_kaynaklari() {
    find /etc/apt -maxdepth 2 \( -name 'sources.list' -o -name '*.list' -o -name '*.sources' \) \
        -type f 2>/dev/null
}

_apt_guvenligi_kapat() {
    _apt_kaynaklari | while read -r kaynak; do
        case "$kaynak" in
            *.sources) sed -i '/debian-security/a Enabled: no' "$kaynak" ;;
            *) sed -i 's|^\([^#].*debian-security.*\)$|# \1|' "$kaynak" ;;
        esac
    done
}

apt_yedekli() {
    if apt-get "$@"; then
        return 0
    fi
    echo "   (apt başarısız — kurulu paketler yükseltilmeden yeniden deneniyor)"
    if [ "$1" = "install" ] || [ "$1" = "-f" ]; then
        if apt-get --no-upgrade "$@"; then
            return 0
        fi
    fi
    echo "   (yine başarısız — debian-security kaynağı devre dışı bırakılıyor)"
    _apt_guvenligi_kapat
    apt-get update -qq && apt-get "$@"
}
