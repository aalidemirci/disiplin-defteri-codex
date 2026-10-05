"""PNG → WebP (site görselleri). Backend kabında Pillow ile koşar.

Ekranlar 2880×1800 PNG → 1440×900 WebP (kalite 88); örnek evrak önizlemeleri olduğu
boyda WebP (kalite 85). Kardeş proje sayfalarındaki görsellerle aynı ölçüler.

    python scripts/site_ornekleri/webp_cevir.py --cikti dist/site-ornekleri
"""

from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image


def main() -> None:
    ayr = argparse.ArgumentParser()
    ayr.add_argument("--cikti", required=True)
    cikti = Path(ayr.parse_args().cikti)

    ekran_hedef = cikti / "ekranlar" / "webp"
    ekran_hedef.mkdir(parents=True, exist_ok=True)
    for png in sorted((cikti / "ekranlar" / "png").glob("*.png")):
        with Image.open(png) as resim:
            kucuk = resim.convert("RGB").resize((1440, 900), Image.Resampling.LANCZOS)
            kucuk.save(ekran_hedef / f"{png.stem}.webp", "WEBP", quality=88, method=6)
        print(f"WEBP {png.stem}.webp", flush=True)

    for png in sorted((cikti / "ornek-evrak").glob("*.png")):
        with Image.open(png) as resim:
            resim.convert("RGB").save(png.with_suffix(".webp"), "WEBP", quality=85, method=6)
        png.unlink()
        print(f"WEBP {png.stem}.webp", flush=True)


if __name__ == "__main__":
    main()
