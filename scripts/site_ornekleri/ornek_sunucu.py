"""Örnek okulu kurar, örnek evrakı üretir ve programı ekran çekimi için sunar.

`site_ornekleri.sh` bunu backend kabında çalıştırır (depo kökü `/repo`). Program
**masaüstü açılış yolundan** kalkar (`desktop.django_bootstrap`): açılışa özel oturum
belirteci, göç, belirteç korumasının zincirde olduğu denetimi; sunucu waitress ile
127.0.0.1'de dinler, dışarıya port açılmaz. Ekran çekimi kabı bu kabın ağ ad alanına
bağlanır ve pencerenin belirteçli açılış adresini açar.

Veri dizini kabın /tmp'sindedir ve kapla silinir; depoya veri girmez. Örnek evrak
`<cikti>/ornek-evrak/*.pdf` olarak programın kendi evrak motoruyla yazılır. Çekim bitince
`<cikti>/bitti` dosyası belirir ve sunucu kapanır.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import threading
import time
from datetime import date
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(Path(__file__).resolve().parent))

# Geçici kabın /tmp'si: kapla silinir, depoya ve host'a veri yazılmaz.
VERI = Path("/tmp/dd-site-ornekleri")  # noqa: S108
PORT = 8765
# Çekim takılırsa sunucu en geç bu süre sonunda kapanır.
KAPANIS_SURESI_SN = 30 * 60


def _ortam() -> None:
    from desktop.session_guard import ENV_TOKEN, generate_session_token

    os.environ[ENV_TOKEN] = generate_session_token()
    os.environ["DD_FRONTEND_DIR"] = str(REPO / "frontend" / "dist")
    os.environ["DD_DEBUG"] = "0"
    # Güncelleme şeridi görüntüye girmesin: çalışan sürüm depodaki VERSION'dır ve denetim
    # var olmayan bir depoya gider (ağdan sürüm bilgisi alınmaz).
    os.environ["DD_APP_VERSION"] = (REPO / "VERSION").read_text(encoding="utf-8").strip()
    os.environ["DD_UPDATE_REPOSITORY"] = "ornek/yok"


def _ornek_evrak(okul: object, hedef: Path) -> list[str]:
    """Programın evrak motoruyla örnek belgeler (sıra = sitedeki sıra)."""
    from apps.disiplin import documents as evrak
    from apps.disiplin import honor_documents, selectors
    from apps.disiplin.models import DocumentType

    o = okul  # OrnekOkul
    hedef.mkdir(parents=True, exist_ok=True)
    kurul = o.dosya["kurul"]  # type: ignore[attr-defined]
    mehmet = o.ogrenci["Mehmet SINAMA"]  # type: ignore[attr-defined]
    burak = o.ogrenci["Burak MİSAL"]  # type: ignore[attr-defined]
    burak_katilimci = kurul.participants.get(student=burak, role="ACCUSED")

    def belge(case: object, tur: str, gun: date, **kw: object) -> bytes:
        pdf, _kayit = evrak.generate_document(case, document_type=tur, generated_on=gun, **kw)  # type: ignore[arg-type]
        return pdf

    onur = o.toplanti["onur"]  # type: ignore[attr-defined]
    odk = o.toplanti["odk"]  # type: ignore[attr-defined]
    uygun = [m.honor_certificate for m in onur.agenda_items.all() if m.outcome == "FAVORABLE"]
    kabul = [m.honor_certificate for m in odk.agenda_items.all() if m.outcome == "FAVORABLE"]

    uretim: list[tuple[str, bytes]] = [
        (
            "01-savunmaya-cagri",
            belge(
                kurul,
                DocumentType.DEFENSE_CALL,
                date(2026, 9, 23),
                participant_id=burak_katilimci.pk,
                statement_date=date(2026, 9, 25),
                statement_time="10:30",
                statement_place="Müdür yardımcısı odası",
            ),
        ),
        (
            "02-kurul-karari-ek1",
            belge(
                kurul,
                DocumentType.COMMITTEE_DECISION,
                date(2026, 9, 29),
                student_id=mehmet.pk,
            ),
        ),
        (
            "03-ceza-tebligi-veli",
            belge(
                kurul,
                DocumentType.PENALTY_NOTICE,
                date(2026, 10, 1),
                student_id=mehmet.pk,
                recipient=evrak.RECIPIENT_PARENT,
            ),
        ),
        (
            "04-mudur-uyarisi",
            belge(
                o.dosya["uyari"],
                DocumentType.WARNING_LETTER,
                date(2026, 9, 18),  # type: ignore[attr-defined]
                student_id=o.ogrenci["Ayşe DENEME"].pk,  # type: ignore[attr-defined]
            ),
        ),
        (
            "05-dizi-pusulasi",
            evrak.generate_document(
                kurul,
                document_type=DocumentType.INDEX_SHEET,
                generated_on=date(2026, 10, 2),
                log=False,
            )[0],
        ),
        (
            "06-onur-kurulu-teklif-tutanagi",
            honor_documents.render_recommendation_record(
                uygun,
                board=onur.honor_board,
                committee=selectors.get_active_committee(),
                meeting=onur,
            ),
        ),
        (
            "07-odk-onur-belgesi-karari",
            honor_documents.render_award_decision_record(
                kabul,
                meeting=odk,
            ),
        ),
        ("08-karar-defteri-onur-kurulu", evrak.render_council_meeting_minutes(onur)),
    ]
    adlar = []
    for ad, pdf in uretim:
        (hedef / f"{ad}.pdf").write_bytes(pdf)
        adlar.append(ad)
        print(f"EVRAK {ad}.pdf", flush=True)
    return adlar


def main() -> None:
    ayr = argparse.ArgumentParser()
    ayr.add_argument("--cikti", required=True)
    cikti = REPO / ayr.parse_args().cikti
    cikti.mkdir(parents=True, exist_ok=True)

    shutil.rmtree(VERI, ignore_errors=True)
    VERI.mkdir(parents=True)
    _ortam()

    from desktop import django_bootstrap
    from desktop.session_guard import ENV_TOKEN, window_url

    django_bootstrap.prepare_django(REPO / "backend", VERI)
    django_bootstrap.run_migrations()
    django_bootstrap.assert_session_guard_installed()

    import ornek_okul

    okul = ornek_okul.kur()
    print("TOHUM tamam", flush=True)
    evrak = _ornek_evrak(okul, cikti / "ornek-evrak")

    from waitress import create_server

    uygulama = django_bootstrap.build_wsgi_application()
    sunucu = create_server(uygulama, host="127.0.0.1", port=PORT, threads=4)
    threading.Thread(target=sunucu.run, daemon=True).start()

    taban = f"http://127.0.0.1:{PORT}"
    durum = {
        "taban": taban,
        "acilis": window_url(taban + "/", os.environ[ENV_TOKEN]),
        "evrak": evrak,
        "sahne": {
            "kurul_dosyasi": okul.dosya["kurul"].pk,
            "odk_toplantisi": okul.toplanti["odk"].pk,
            "onur_toplantisi": okul.toplanti["onur"].pk,
        },
    }
    (cikti / "durum.json").write_text(json.dumps(durum, ensure_ascii=False), encoding="utf-8")
    print("HAZIR", flush=True)

    bitti = cikti / "bitti"
    son = time.monotonic() + KAPANIS_SURESI_SN
    while not bitti.exists() and time.monotonic() < son:
        time.sleep(1)
    sunucu.close()


if __name__ == "__main__":
    main()
