"""Font release archives are verified before any glyph processing."""

import hashlib
from pathlib import Path

import pytest

import scripts.build_fonts as build_fonts


def test_download_rejects_a_tampered_cached_archive(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(build_fonts, "DOWNLOAD_CACHE", tmp_path)
    font = build_fonts.GOOGLE_SANS_CODE
    (tmp_path / font.url.rsplit("/", 1)[-1]).write_bytes(b"tampered")

    def no_network(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("a cached archive must not trigger a download")

    monkeypatch.setattr(build_fonts.urllib.request, "urlopen", no_network)
    with pytest.raises(ValueError, match="expected " + font.sha256):
        build_fonts.download(font)


def test_download_returns_a_verified_cached_archive(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(build_fonts, "DOWNLOAD_CACHE", tmp_path)
    payload = b"archive"
    font = build_fonts.FontBuild(
        family="Test",
        url="https://github.com/googlefonts/test/releases/download/v1/test.zip",
        sha256=hashlib.sha256(payload).hexdigest(),
        member="test.ttf",
        axes={},
        features=(),
        unicodes="0041",
        output="test.woff2",
    )
    (tmp_path / "test.zip").write_bytes(payload)

    assert build_fonts.download(font) == payload
