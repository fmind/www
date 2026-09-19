"""Contact exports preserve accents, framing, and escaped public text."""

from base64 import b64decode
from dataclasses import replace
from io import BytesIO
from pathlib import Path

import pytest
from PIL import Image

import www.connect as connect


def test_contact_card_folds_utf8_and_escapes_text(monkeypatch: pytest.MonkeyPatch) -> None:
    title = "Architecture é" * 20
    nickname = "Fmind, AI; security\\research\r\nNOTE:still a nickname"
    monkeypatch.setattr(connect, "METADATA", replace(connect.METADATA, job_title=title, alternate_name=nickname))
    card = connect.render_contact_card()
    assert all(len(line) <= 75 for line in card.split(b"\r\n"))
    unfolded = card.decode().replace("\r\n ", "")
    assert f"TITLE:{title}\r\n" in unfolded
    assert "NICKNAME:Fmind\\, AI\\; security\\\\research\\nNOTE:still a nickname\r\n" in unfolded
    assert unfolded.count("\r\nNOTE:") == 1
    assert "\r\nNOTE:still a nickname" not in unfolded
    assert b"\n" not in card.replace(b"\r\n", b"")


def test_contact_card_includes_public_professional_details() -> None:
    card = connect.render_contact_card()
    lines = card.decode().replace("\r\n ", "").split("\r\n")
    assert f"UID:{connect.METADATA.site_url}/#person" in lines
    assert f"SOURCE:{connect.METADATA.site_url}/connect.vcf" in lines
    assert f"URL:{connect.METADATA.calendar_url}" in lines
    for social in connect.METADATA.socials:
        assert f"URL:{social.url}" in lines
    note = next(line for line in lines if line.startswith("NOTE:"))
    assert note.startswith("NOTE:Médéric Hurier (Fmind)\\, freelance AI architect based in Luxembourg.")
    assert "PhD in AI and Computer Security" in note
    assert "Agentic AI Foundation Ambassador" in note
    assert "33N Ventures" in note
    assert "Professional Cloud Architect" in note
    assert "Book a session:" in note
    assert "Languages: French\\, English" in note
    assert "ADR;TYPE=WORK:;;;Luxembourg;;;Luxembourg" in lines
    assert any(line.startswith("CATEGORIES:") and "Production MLOps" in line for line in lines)
    assert not any(line.startswith(("TEL", "BDAY", "GEO", "KEY")) for line in lines)
    assert all(len(line) <= 75 for line in card.split(b"\r\n"))
    assert card == connect.render_contact_card()


def test_contact_portrait_is_embedded_without_source_metadata(tmp_path: Path) -> None:
    (tmp_path / "img").mkdir()
    source = Image.new("RGB", (384, 384), "blue")
    exif = Image.Exif()
    exif[0x010E] = "private camera annotation"
    source.save(tmp_path / "img/avatar.webp", exif=exif, icc_profile=b"private profile")
    lines = connect.render_contact_card(tmp_path).decode().replace("\r\n ", "").split("\r\n")
    photo = next(line for line in lines if line.startswith("PHOTO;ENCODING=b;TYPE=JPEG:"))
    with Image.open(BytesIO(b64decode(photo.partition(":")[2], validate=True))) as decoded:
        assert decoded.format == "JPEG"
        assert decoded.size == (384, 384)
        assert not decoded.getexif()
        assert "icc_profile" not in decoded.info
    assert "private" not in "\n".join(lines)


def test_contact_portrait_failure_explains_recovery(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="public contact portrait") as caught:
        connect.render_contact_card(tmp_path)
    assert isinstance(caught.value.__cause__, OSError)


@pytest.mark.parametrize(
    "url", ["https://example.org/\r\nTEL:injected", "javascript:alert(1)", "https://user:pass@example.org"]
)
def test_contact_card_rejects_unsafe_public_links(monkeypatch: pytest.MonkeyPatch, url: str) -> None:
    monkeypatch.setattr(connect, "METADATA", replace(connect.METADATA, calendar_url=url))
    with pytest.raises(ValueError, match="public contact URL"):
        connect.render_contact_card()
