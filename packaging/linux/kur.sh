#!/usr/bin/env bash
# =============================================================================
# kur.sh — Disiplin Defteri'ni yönetici yetkisi OLMADAN kurar
# =============================================================================
# Taşınabilir arşivin (.tar.gz) içinden çalıştırılır:
#
#     tar -xzf disiplin-defteri-*-linux-x64.tar.gz
#     cd disiplin-defteri-*
#     ./kur.sh
#
# Her şey kullanıcının kendi ev dizinine kurulur; sistem dosyalarına
# DOKUNULMAZ. Okul bilgisayarında yönetici parolası yoksa bu yol kullanılır
# (.deb kurulumu için `sudo` gerekir).
#
# Kaldırmak için: ./kaldir.sh   (verileriniz silinmez)
# =============================================================================
set -euo pipefail

KAYNAK="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HEDEF="$HOME/.local/opt/disiplin-defteri"
BIN_DIZINI="$HOME/.local/bin"
UYGULAMALAR="$HOME/.local/share/applications"
IKON_KOKU="$HOME/.local/share/icons/hicolor"

if [ ! -x "$KAYNAK/uygulama/disiplin-defteri" ]; then
    echo "HATA: Arşiv eksik görünüyor (uygulama/disiplin-defteri bulunamadı)." >&2
    exit 1
fi

echo "Kuruluyor: $HEDEF"
rm -rf "$HEDEF"
mkdir -p "$HEDEF" "$BIN_DIZINI" "$UYGULAMALAR"
cp -a "$KAYNAK/uygulama/." "$HEDEF/"

ln -sf "$HEDEF/disiplin-defteri" "$BIN_DIZINI/disiplin-defteri"

# Masaüstü kısayolu — Exec satırı ev dizinindeki yola çevrilir.
sed "s|^Exec=.*|Exec=$HEDEF/disiplin-defteri|" \
    "$KAYNAK/disiplin-defteri.desktop" > "$UYGULAMALAR/disiplin-defteri.desktop"
chmod 0644 "$UYGULAMALAR/disiplin-defteri.desktop"

for boyut in 16 24 32 48 64 128 256; do
    dizin="$IKON_KOKU/${boyut}x${boyut}/apps"
    mkdir -p "$dizin"
    cp "$KAYNAK/ikonlar/disiplin-defteri-${boyut}.png" "$dizin/disiplin-defteri.png"
done

command -v update-desktop-database >/dev/null 2>&1 && \
    update-desktop-database -q "$UYGULAMALAR" || true
command -v gtk-update-icon-cache >/dev/null 2>&1 && \
    gtk-update-icon-cache -q -f "$IKON_KOKU" || true

echo
echo "Kurulum tamamlandı."
echo "  Menüden 'Disiplin Defteri' ile açabilirsiniz."
echo "  Uçbirimden: disiplin-defteri"
case ":$PATH:" in
    *":$BIN_DIZINI:"*) ;;
    *)
        echo
        echo "NOT: $BIN_DIZINI PATH'inizde görünmüyor. Uçbirimden çalıştırmak için"
        echo "     ~/.bashrc dosyanıza şu satırı ekleyin:"
        echo "     export PATH=\"\$HOME/.local/bin:\$PATH\""
        ;;
esac
echo
echo "Verileriniz: $HOME/.local/share/disiplin-defteri"
