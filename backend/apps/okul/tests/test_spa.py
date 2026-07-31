"""SPA servis kapısı — paketlenmiş pencere kök URL'yi açar.

Masaüstü başlatıcısı pywebview penceresini `http://127.0.0.1:<port>/?t=…`
adresine yönlendirir. Kök URL bir HTML döndürmezse kullanıcı Django hata
sayfası görür — yani paket kurulur ama program AÇILMAZ. Bu testler o kapıyı
tutar (F5-D4 paketleme denetiminde bulundu: `GET /` 404 dönüyordu).
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from django.conf import settings
from django.test import Client

pytestmark = pytest.mark.django_db


@pytest.fixture
def spa_index() -> Iterator[Path]:
    """Derlenmiş SPA yoksa (temiz depo) testin kendi index.html'ini koyar."""
    index = settings.FRONTEND_DIR / "index.html"
    if index.exists():
        yield index
        return
    index.parent.mkdir(parents=True, exist_ok=True)
    index.write_text("<!doctype html><title>Disiplin Defteri</title>", encoding="utf-8")
    yield index
    index.unlink()


def test_kok_url_spa_dondurur(client: Client, spa_index: Path) -> None:
    resp = client.get("/")
    assert resp.status_code == 200
    assert resp["Content-Type"].startswith("text/html")


def test_istemci_rotasi_spa_dondurur(client: Client, spa_index: Path) -> None:
    """`/disiplin/12` sunucuda tanımlı DEĞİL; SPA yönlendiricisine düşmeli."""
    resp = client.get("/disiplin/12")
    assert resp.status_code == 200
    assert resp["Content-Type"].startswith("text/html")


def test_api_yolu_spa_ya_dusmez(client: Client, spa_index: Path) -> None:
    """Var olmayan API ucu 404 kalmalı — SPA'ya düşerse istemci HTML'i JSON sanır."""
    resp = client.get("/api/v1/boyle-bir-uc-yok/")
    assert resp.status_code == 404
