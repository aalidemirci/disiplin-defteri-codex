"""27.09.2026 kod denetimi — parola kurulumunun çift şifreleme regresyonu (D-K2)."""

from __future__ import annotations

import pytest

from apps.okul.models import Student
from apps.okul.services import app_password
from apps.okul.tests.test_app_password import (  # noqa: F401 — autouse fikstür
    PAROLA,
    TCKN,
    YENI_PAROLA,
    guvenlik_ortami,
    ogrenci_olustur,
)
from shared import crypto

pytestmark = pytest.mark.django_db


def test_dk2_guvenlik_dosyasi_kayipken_yeniden_kurulum_reddedilir() -> None:
    """guvenlik.json kaybolmuşken yeni parola kurmak veriyi ikinci anahtarla sarmamalı."""
    ogrenci = ogrenci_olustur()
    app_password.enable(password=PAROLA)
    app_password.state_path().replace(app_password.state_path().with_name("guvenlik-kayip.json"))
    crypto.unload_key()
    with pytest.raises(app_password.AppPasswordError, match="guvenlik.json"):
        app_password.enable(password=YENI_PAROLA)
    # Asıl dosya geri konunca eski parolayla veri okunur kalmalı.
    app_password.state_path().with_name("guvenlik-kayip.json").replace(app_password.state_path())
    app_password.unlock(password=PAROLA)
    assert Student.all_objects.get(pk=ogrenci.pk).tckn == TCKN
