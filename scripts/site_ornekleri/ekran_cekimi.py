"""Ekran görüntülerini alır ve örnek evrakın ilk sayfasını görsele çevirir.

Geçici Playwright kabında koşar (depo bağımlılığı DEĞİLDİR); `ornek_sunucu.py`'nin
kabının ağ ad alanına bağlıdır: program o kabın 127.0.0.1'inde dinler, dışarıya port
açılmaz. Tarayıcı önce pencerenin belirteçli açılış adresini açar (masaüstü penceresi
gibi); belirteç çereze geçer, sonraki sayfalar çerezle yürür.

Görüntü: 1440×900 görünüm alanı, aygıt piksel oranı 2 (PNG 2880×1800), Türkçe yerel
ayar, Europe/Istanbul, açık tema. Örnek evrakın ilk sayfası `pdftoppm` ile 110 dpi PNG
olur (A4 dikey 910×1287). WebP'ye çeviri ayrı adımdır (`webp_cevir.py`).

    python scripts/site_ornekleri/ekran_cekimi.py --cikti dist/site-ornekleri
"""

from __future__ import annotations

import argparse
import json
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

from playwright.sync_api import Page, sync_playwright

GENISLIK, YUKSEKLIK = 1440, 900
BEKLEME_MS = 20_000


def _bekle(sayfa: Page) -> None:
    """Ağ sakinleşene, iskelet yükleyiciler ve kısa ömürlü bildirimler kaybolana dek."""
    sayfa.wait_for_load_state("networkidle", timeout=BEKLEME_MS)
    sayfa.wait_for_function(
        "() => !document.querySelector('[aria-busy=\"true\"], .animate-pulse')",
        timeout=BEKLEME_MS,
    )
    sayfa.evaluate("() => document.fonts.ready")
    sayfa.wait_for_timeout(500)


def _git(sayfa: Page, durum: dict[str, Any], yol: str) -> None:
    sayfa.goto(durum["taban"] + yol, wait_until="domcontentloaded")
    _bekle(sayfa)


def _sekme(sayfa: Page, ad: str) -> None:
    sayfa.get_by_role("tab", name=ad).click()
    _bekle(sayfa)


def _basa_kaydir(sayfa: Page, oge: Any) -> None:
    """Öğeyi görünüm alanının üstüne (yapışkan üst çubuğun altına) kaydırır."""
    oge.evaluate("(e) => { e.scrollIntoView({block: 'start'}); window.scrollBy(0, -88); }")
    sayfa.wait_for_timeout(400)


def panel(sayfa: Page, durum: dict[str, Any]) -> None:
    _git(sayfa, durum, "/")


def dosyalar(sayfa: Page, durum: dict[str, Any]) -> None:
    """Kapanan dosya da görünsün: "Yalnızca açık dosyalar" kaldırılır."""
    _git(sayfa, durum, "/disiplin")
    sayfa.get_by_label("Yalnızca açık dosyalar").uncheck()
    _bekle(sayfa)


def dosya_kurul(sayfa: Page, durum: dict[str, Any]) -> None:
    """Kurul & Karar sekmesi: toplantı (yedek üye ile) ve öğrenci bazlı kararlar."""
    _git(sayfa, durum, f"/disiplin/{durum['sahne']['kurul_dosyasi']}")
    _sekme(sayfa, "Kurul & Karar")
    _basa_kaydir(sayfa, sayfa.get_by_role("tablist").first)


def dosya_evrak(sayfa: Page, durum: dict[str, Any]) -> None:
    _git(sayfa, durum, f"/disiplin/{durum['sahne']['kurul_dosyasi']}")
    _sekme(sayfa, "Evraklar")


def odk_toplanti(sayfa: Page, durum: dict[str, Any]) -> None:
    toplanti = durum["sahne"]["odk_toplantisi"]
    _git(sayfa, durum, f"/odul-disiplin-kurulu?sekme=toplantilar&toplanti={toplanti}")
    # Bilgi kartı ve sayfa başlığı geçilsin; toplantı başlığı üstte dursun.
    _basa_kaydir(sayfa, sayfa.get_by_role("heading", name="Toplantı T001", exact=False))


def onur_teklifler(sayfa: Page, durum: dict[str, Any]) -> None:
    _git(sayfa, durum, "/onur-kurulu?sekme=teklifler")


def mudur_onayi(sayfa: Page, durum: dict[str, Any]) -> None:
    _git(sayfa, durum, "/odul-disiplin-kurulu?sekme=mudur-onayi")


def bilgi_notu(sayfa: Page, durum: dict[str, Any]) -> None:
    _git(sayfa, durum, "/bilgi-notlari/onur-kurulu")


Sahne = Callable[[Page, dict[str, Any]], None]
SAHNELER: tuple[tuple[str, Sahne], ...] = (
    ("panel", panel),
    ("dosyalar", dosyalar),
    ("dosya-kurul", dosya_kurul),
    ("dosya-evrak", dosya_evrak),
    ("odk-toplanti", odk_toplanti),
    ("onur-teklifler", onur_teklifler),
    ("mudur-onayi", mudur_onayi),
    ("bilgi-notu", bilgi_notu),
)


def _evrak_onizleme(cikti: Path, adlar: list[str]) -> None:
    """Her örnek belgenin ilk sayfası: 110 dpi PNG (A4 dikey → 910×1287)."""
    klasor = cikti / "ornek-evrak"
    for ad in adlar:
        subprocess.run(
            [
                "pdftoppm",
                "-r",
                "110",
                "-f",
                "1",
                "-l",
                "1",
                "-png",
                "-singlefile",
                str(klasor / f"{ad}.pdf"),
                str(klasor / ad),
            ],
            check=True,
        )
        print(f"ONIZLEME {ad}.png", flush=True)


def main() -> None:
    ayr = argparse.ArgumentParser()
    ayr.add_argument("--cikti", required=True)
    cikti = Path(ayr.parse_args().cikti)
    durum = json.loads((cikti / "durum.json").read_text(encoding="utf-8"))
    hedef = cikti / "ekranlar" / "png"
    hedef.mkdir(parents=True, exist_ok=True)
    try:
        with sync_playwright() as pw:
            tarayici = pw.chromium.launch(args=["--headless=new"])
            baglam = tarayici.new_context(
                viewport={"width": GENISLIK, "height": YUKSEKLIK},
                device_scale_factor=2,
                locale="tr-TR",
                timezone_id="Europe/Istanbul",
                color_scheme="light",
            )
            sayfa = baglam.new_page()
            sayfa.goto(durum["acilis"], wait_until="domcontentloaded")
            _bekle(sayfa)
            for ad, sahne in SAHNELER:
                sahne(sayfa, durum)
                sayfa.screenshot(path=str(hedef / f"ekran-{ad}.png"), full_page=False)
                print(f"GORUNTU ekran-{ad}.png", flush=True)
            tarayici.close()
        _evrak_onizleme(cikti, durum["evrak"])
    finally:
        (cikti / "bitti").write_text("1", encoding="utf-8")


if __name__ == "__main__":
    main()
