#!/usr/bin/env bash
# =============================================================================
# apt-yedekli.sh — Debian aynası 404 verdiğinde apt kurulumunu yedek kaynakla
# yeniden dener. build.sh ve kap-ici-test.sh tarafından `source` edilir.
# =============================================================================
# 27.09.2026: python:3.12-bullseye / debian:11 kaplarında `apt-get update`
# sonrası bile debian-security havuzu libglib2.0 (2.66.8-1+deb11u8) için 404
# verdi (iki koşuda aynı). Neden: bullseye LTS'in 31.08.2026'da bitip güvenlik
# deposunun arşive taşınması ya da deb.debian.org CDN'inde indeks/havuz
# tutarsızlığı. Pardus 21 (glibc 2.31) uyumu için tabanı DEĞİŞTİRMİYORUZ; yalnız
# paket kaynağını sırayla değiştirip yeniden deniyoruz:
#   1. varsayılan kaynaklar,
#   2. debian-security → doğrudan security.debian.org (CDN'siz),
#   3. her şey → archive.debian.org (arşivlenmiş sürüm; Valid-Until denetimi kapalı).
# Kullanım:  apt_yedekli install -y -qq --no-install-recommends paket...

_apt_kaynaklari() {
    find /etc/apt -maxdepth 2 \( -name 'sources.list' -o -name '*.list' -o -name '*.sources' \) \
        -type f 2>/dev/null
}

_apt_guncelle() {
    apt-get update -qq "$@"
}

apt_yedekli() {
    if apt-get "$@"; then
        return 0
    fi
    echo "   (apt başarısız — güvenlik kaynağı doğrudan security.debian.org'a çevriliyor)"
    _apt_kaynaklari | while read -r kaynak; do
        sed -i 's#://deb\.debian\.org/debian-security#://security.debian.org/debian-security#g' "$kaynak"
    done
    if _apt_guncelle && apt-get "$@"; then
        return 0
    fi
    echo "   (yine başarısız — kaynaklar archive.debian.org'a çevriliyor)"
    _apt_kaynaklari | while read -r kaynak; do
        sed -i -E \
            -e 's#://security\.debian\.org/debian-security#://archive.debian.org/debian-security#g' \
            -e 's#://deb\.debian\.org/debian([ /]|$)#://archive.debian.org/debian\1#g' \
            "$kaynak"
    done
    _apt_guncelle -o Acquire::Check-Valid-Until=false && \
        apt-get -o Acquire::Check-Valid-Until=false "$@"
}
