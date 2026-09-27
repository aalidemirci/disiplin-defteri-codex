"""GitHub Release tabanlı güncelleme servisinin ağsız birim testleri."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import pytest
from rest_framework.test import APIClient

from apps.okul.services import updates


@pytest.fixture
def client() -> APIClient:
    return APIClient()


def _release(
    *, digest: str = "", checksums: updates.ReleaseAsset | None = None
) -> updates.ReleaseInfo:
    installer = updates.ReleaseAsset(
        name="disiplin-defteri-2026.8.0-win64-setup.exe",
        download_url="https://github.com/aalidemirci/disiplin-defteri-codex/releases/download/v2026.8.0/disiplin-defteri-2026.8.0-win64-setup.exe",
        size=8,
        digest=digest,
    )
    return updates.ReleaseInfo(
        version="2026.8.0",
        tag_name="v2026.8.0",
        name="Disiplin Defteri 2026.8.0",
        published_at="2026-08-01T12:00:00Z",
        html_url="https://github.com/aalidemirci/disiplin-defteri-codex/releases/tag/v2026.8.0",
        installer=installer,
        checksums=checksums,
    )


def test_release_yaniti_windows_kurucusunu_ve_ozeti_cozer() -> None:
    release = updates._parse_release(  # noqa: SLF001
        {
            "tag_name": "v2026.8.0",
            "name": "Ağustos sürümü",
            "html_url": "https://github.com/aalidemirci/disiplin-defteri-codex/releases/tag/v2026.8.0",
            "assets": [
                {
                    "name": "disiplin-defteri-2026.8.0-win64-setup.exe",
                    "browser_download_url": "https://github.com/aalidemirci/disiplin-defteri-codex/releases/download/v2026.8.0/setup.exe",
                    "size": 1234,
                    "digest": f"sha256:{'a' * 64}",
                },
                {
                    "name": "SHA256SUMS.txt",
                    "browser_download_url": "https://github.com/aalidemirci/disiplin-defteri-codex/releases/download/v2026.8.0/SHA256SUMS.txt",
                    "size": 100,
                },
            ],
        }
    )

    assert release.version == "2026.8.0"
    assert release.installer is not None
    assert release.installer.size == 1234
    assert release.checksums is not None


def test_guvenilmeyen_varlik_adresi_kabul_edilmez() -> None:
    release = updates._parse_release(  # noqa: SLF001
        {
            "tag_name": "v2026.8.0",
            "assets": [
                {
                    "name": "disiplin-defteri-2026.8.0-win64-setup.exe",
                    "browser_download_url": "https://example.org/zararli.exe",
                }
            ],
        }
    )

    assert release.installer is None


def test_guncelleme_durumu_surumu_karsilastirir(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(updates, "latest_release", lambda **_kwargs: _release())

    status = updates.update_status(current_version="2026.7.0")

    assert status["update_available"] is True
    assert status["can_download"] is True
    assert status["latest_version"] == "2026.8.0"


def test_kurucu_sha256_dogrulanarak_onbellege_yazilir(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    content = b"kurulum"
    release = _release(digest=f"sha256:{hashlib.sha256(content).hexdigest()}")
    monkeypatch.setattr(updates, "latest_release", lambda **_kwargs: release)
    monkeypatch.setattr(updates, "get_app_version", lambda: "2026.7.0")
    monkeypatch.setattr(updates, "_read_url", lambda *_args, **_kwargs: content)
    monkeypatch.setattr(
        updates,
        "update_directory",
        lambda: tmp_path / "updates",
    )

    target = updates.download_latest_installer()

    assert target.read_bytes() == content
    assert target.parent == tmp_path / "updates"
    assert not target.with_suffix(target.suffix + ".part").exists()


def test_kurucu_ozeti_tutmazsa_dosya_yazilmaz(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    release = _release(digest=f"sha256:{'0' * 64}")
    monkeypatch.setattr(updates, "latest_release", lambda **_kwargs: release)
    monkeypatch.setattr(updates, "get_app_version", lambda: "2026.7.0")
    monkeypatch.setattr(updates, "_read_url", lambda *_args, **_kwargs: b"farkli")
    monkeypatch.setattr(
        updates,
        "update_directory",
        lambda: tmp_path / "updates",
    )

    with pytest.raises(updates.UpdateError, match="SHA-256"):
        updates.download_latest_installer()

    assert not (tmp_path / "updates").exists()


@pytest.mark.django_db
def test_guncelleme_api_durumu_dondurur(
    client: APIClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expected: dict[str, Any] = {
        "current_version": "2026.7.0",
        "latest_version": "2026.8.0",
        "update_available": True,
        "release_name": "Yeni sürüm",
        "published_at": "",
        "release_url": "",
        "can_download": True,
        "installer_name": "setup.exe",
        "installer_size": 42,
    }
    monkeypatch.setattr(updates, "update_status", lambda **_kwargs: expected)

    response = client.get("/api/v1/updates/latest/")

    assert response.status_code == 200
    assert response.json() == expected


def _liste_kaydi(tag: str, *, prerelease: bool = True, draft: bool = False) -> dict[str, Any]:
    surum = tag.removeprefix("v")
    return {
        "tag_name": tag,
        "name": f"Disiplin Defteri {tag}",
        "draft": draft,
        "prerelease": prerelease,
        "published_at": "2026-09-27T18:35:58Z",
        "html_url": f"https://github.com/aalidemirci/disiplin-defteri-codex/releases/tag/{tag}",
        "assets": [
            {
                "name": f"disiplin-defteri-{surum}-win64-setup.exe",
                "browser_download_url": (
                    "https://github.com/aalidemirci/disiplin-defteri-codex/releases/download/"
                    f"{tag}/disiplin-defteri-{surum}-win64-setup.exe"
                ),
                "size": 10,
                "digest": "sha256:" + "a" * 64,
            }
        ],
    }


def test_beta_surumler_de_guncelleme_olarak_gorulur(monkeypatch: pytest.MonkeyPatch) -> None:
    """GitHub `releases/latest` ön sürümleri döndürmez (404); liste okunur, beta dahil
    en yüksek sürüm seçilir, taslak atlanır."""
    import json

    liste = [
        _liste_kaydi("v2026.7.0-beta.1"),
        _liste_kaydi("v2026.9.0-beta.3", draft=True),
        _liste_kaydi("v2026.9.0-beta.2"),
        _liste_kaydi("v2026.9.0-beta.1"),
    ]
    okunan: list[str] = []

    def sahte_oku(url: str, **_kwargs: Any) -> bytes:
        okunan.append(url)
        return json.dumps(liste).encode("utf-8")

    monkeypatch.setattr(updates, "_read_url", sahte_oku)
    durum = updates.update_status(force=True, current_version="2026.9.0-beta.1")
    assert "/releases/latest" not in okunan[0]
    assert durum["update_available"] is True
    assert durum["latest_version"] == "2026.9.0-beta.2"


def test_yayimlanmis_surum_yoksa_anlasilir_hata(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        updates,
        "_read_url",
        lambda *_a, **_k: b'[{"tag_name": "v2026.9.0-beta.3", "draft": true, "assets": []}]',
    )
    with pytest.raises(updates.UpdateError, match="yayımlanmış bir sürüm"):
        updates.latest_release(force=True)


@pytest.mark.parametrize(
    ("dusuk", "yuksek"),
    [
        ("2026.9.0-beta.1", "2026.9.0-beta.2"),
        ("2026.9.0-beta.2", "2026.9.0-beta.10"),
        ("2026.9.0-beta.10", "2026.9.0"),
        ("2026.7.0", "2026.9.0-beta.1"),
    ],
)
def test_surum_siralamasi_semver(dusuk: str, yuksek: str) -> None:
    assert updates.version_key(dusuk) < updates.version_key(yuksek)
