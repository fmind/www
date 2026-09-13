"""Contact exports preserve accents, framing, and escaped public text."""

from dataclasses import replace

import pytest

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
    assert "\r\nNOTE:" not in unfolded
    assert b"\n" not in card.replace(b"\r\n", b"")
