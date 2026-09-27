"""`--kripto-duman` teşhis kipi (teknik borç D7): parola zinciri pakette sınanır."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest

GIRIS = Path(__file__).parents[1] / "pyinstaller" / "giris.py"


def _giris() -> ModuleType:
    spec = importlib.util.spec_from_file_location("giris_kripto_test", GIRIS)
    assert spec is not None and spec.loader is not None
    modul = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modul)
    return modul


def test_kripto_duman_basarili(capsys: pytest.CaptureFixture[str]) -> None:
    giris = _giris()

    assert giris.run(["--kripto-duman"]) == 0
    assert "Kripto duman testi başarılı" in capsys.readouterr().err


def test_kripto_duman_anahtari_bellekte_birakmaz() -> None:
    giris = _giris()
    assert giris.run(["--kripto-duman"]) == 0

    from shared import crypto

    assert crypto.is_unlocked() is False


def test_sarmal_acilamazsa_9_ile_cikar(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    giris = _giris()
    giris.run(["--kripto-duman"])  # backend'i sys.path'e ekler
    from shared import crypto

    monkeypatch.setattr(crypto, "unwrap_key", lambda wrapped, *, wrapping_key: b"yanlis")

    assert giris.run(["--kripto-duman"]) == giris.EXIT_CRYPTO_SMOKE_FAILED
    assert "sarmaldan geri açılamadı" in capsys.readouterr().err


def test_zincir_coker_ise_9_ile_cikar(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Argon2 ikilisi pakette yoksa import/çağrı patlar — kip bunu rapor edip 9 döner."""
    giris = _giris()
    giris.run(["--kripto-duman"])
    from shared import crypto

    def patla(*_: object, **__: object) -> bytes:
        raise ImportError("_argon2_cffi_bindings yok")

    monkeypatch.setattr(crypto, "derive_key", patla)

    assert giris.run(["--kripto-duman"]) == giris.EXIT_CRYPTO_SMOKE_FAILED
    assert "kripto duman testi çöktü" in capsys.readouterr().err
