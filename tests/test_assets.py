"""Static asset startup invariants."""

from pathlib import Path
from typing import cast

import pytest

from www.assets import ROOT_FILE_SOURCES, ApplicationAssets, load_application_assets

FONT_FILES = (
    "fonts/Inter-Variable.woff2",
    "fonts/Outfit-Variable.woff2",
)


def minimal_woff2() -> bytes:
    """Build the smallest header needed by the startup format check."""
    header = bytearray(48)
    header[0:4] = b"wOF2"
    header[4:8] = b"\x00\x01\x00\x00"
    header[8:12] = len(header).to_bytes(4, "big")
    header[12:14] = (1).to_bytes(2, "big")
    header[16:20] = (1).to_bytes(4, "big")
    header[20:24] = (1).to_bytes(4, "big")
    return bytes(header)


def static_tree(root: Path) -> Path:
    static = root / "static"
    (static / "dist").mkdir(parents=True)
    (static / "fonts").mkdir()
    (static / "dist" / "styles.css").write_text("body{color:red}", encoding="utf-8")
    for relative in FONT_FILES:
        (static / relative).write_bytes(minimal_woff2())
    for relative, _ in ROOT_FILE_SOURCES.values():
        (static / relative).write_bytes(relative.encode())
    return static


def test_load_assets_returns_an_isolated_immutable_snapshot(tmp_path: Path) -> None:
    static = static_tree(tmp_path)

    first = load_application_assets(static)
    (static / "dist" / "styles.css").write_text("body{color:blue}", encoding="utf-8")
    second = load_application_assets(static)

    assert first.hashes["/static/dist/styles.css"] == "15c42ab7"
    assert first.inline_styles.startswith("body{color:red}")
    assert second.hashes["/static/dist/styles.css"] != first.hashes["/static/dist/styles.css"]
    assert second.inline_styles.startswith("body{color:blue}")
    with pytest.raises(TypeError):
        cast(dict[str, str], first.hashes)["/static/dist/styles.css"] = "changed"
    with pytest.raises(TypeError):
        cast(dict[str, object], first.root_files)["/robots.txt"] = first.root_files["/humans.txt"]


def test_application_assets_detaches_caller_owned_mappings() -> None:
    hashes = {"/static/example.css": "original"}
    assets = ApplicationAssets(root_files={}, hashes=hashes, inline_styles="body{}")

    hashes["/static/example.css"] = "mutated"

    assert assets.hashes["/static/example.css"] == "original"


def test_load_assets_fails_without_generated_stylesheet(tmp_path: Path) -> None:
    static = static_tree(tmp_path)
    (static / "dist" / "styles.css").unlink()

    with pytest.raises(RuntimeError, match="generated stylesheet"):
        load_application_assets(static)


def test_load_assets_fails_without_required_root_file(tmp_path: Path) -> None:
    static = static_tree(tmp_path)
    (static / "robots.txt").unlink()

    with pytest.raises(RuntimeError, match="root file"):
        load_application_assets(static)


@pytest.mark.parametrize("relative", FONT_FILES)
def test_load_assets_fails_without_required_font(tmp_path: Path, relative: str) -> None:
    static = static_tree(tmp_path)
    (static / relative).unlink()

    with pytest.raises(RuntimeError, match=f"required WOFF2 font.*{Path(relative).name}"):
        load_application_assets(static)


@pytest.mark.parametrize("relative", FONT_FILES)
@pytest.mark.parametrize(
    "payload",
    [
        pytest.param(b"not a font", id="bad-magic"),
        pytest.param(b"wOF2" + b"\x00" * 44, id="invalid-header"),
    ],
)
def test_load_assets_rejects_corrupt_required_font(tmp_path: Path, relative: str, payload: bytes) -> None:
    static = static_tree(tmp_path)
    (static / relative).write_bytes(payload)

    with pytest.raises(RuntimeError, match=f"invalid WOFF2 font.*{Path(relative).name}"):
        load_application_assets(static)
