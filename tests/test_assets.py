"""Static asset startup invariants."""

import json
from pathlib import Path
from typing import cast

import pytest

from www.assets import ROOT_FILE_SOURCES, STATIC_MANIFEST, ApplicationAssets, hash_static_files, load_application_assets

FONT_FILES = (
    "fonts/GoogleSans-Variable.woff2",
    "fonts/GoogleSansCode-Variable.woff2",
)


FONT_FACES = "".join(f"@font-face{{src:url(/static/{relative})}}" for relative in FONT_FILES)


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
    (static / "dist" / "styles.css").write_text("body{color:red}" + FONT_FACES, encoding="utf-8")
    for relative in FONT_FILES:
        (static / relative).write_bytes(minimal_woff2())
    for relative, _ in ROOT_FILE_SOURCES.values():
        (static / relative).write_bytes(relative.encode())
    return static


def test_load_assets_returns_an_isolated_immutable_snapshot(tmp_path: Path) -> None:
    static = static_tree(tmp_path)

    first = load_application_assets(static)
    (static / "dist" / "styles.css").write_text("body{color:blue}" + FONT_FACES, encoding="utf-8")
    second = load_application_assets(static)

    assert len(first.hashes["/static/dist/styles.css"]) == 8
    assert first.stylesheet.startswith("body{color:red}")
    assert second.hashes["/static/dist/styles.css"] != first.hashes["/static/dist/styles.css"]
    assert second.stylesheet.startswith("body{color:blue}")
    assert first.stylesheet_url == f"/styles.css?v={first.stylesheet_digest}"
    assert second.stylesheet_digest != first.stylesheet_digest
    with pytest.raises(TypeError):
        cast(dict[str, str], first.hashes)["/static/dist/styles.css"] = "changed"
    with pytest.raises(TypeError):
        cast(dict[str, object], first.root_files)["/robots.txt"] = first.root_files["/humans.txt"]


def test_application_assets_detaches_caller_owned_mappings() -> None:
    hashes = {"/static/example.css": "original"}
    assets = ApplicationAssets(root_files={}, hashes=hashes, stylesheet="body{}")

    hashes["/static/example.css"] = "mutated"

    assert assets.hashes["/static/example.css"] == "original"


def test_load_assets_fails_without_generated_stylesheet(tmp_path: Path) -> None:
    static = static_tree(tmp_path)
    (static / "dist" / "styles.css").unlink()

    with pytest.raises(RuntimeError, match=r"generated stylesheet .*; run `mise run build:css`$"):
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


def test_load_assets_versions_font_urls_with_their_content_hash(tmp_path: Path) -> None:
    assets = load_application_assets(static_tree(tmp_path))

    for relative in FONT_FILES:
        path = f"/static/{relative}"
        assert f'url("{path}?v={assets.hashes[path]}")' in assets.stylesheet
        assert f"url({path})" not in assets.stylesheet


def test_load_assets_fails_when_the_stylesheet_drops_a_font_face(tmp_path: Path) -> None:
    static = static_tree(tmp_path)
    (static / "dist" / "styles.css").write_text("body{color:red}", encoding="utf-8")

    with pytest.raises(RuntimeError, match=r"no @font-face for /static/fonts/GoogleSans-Variable\.woff2"):
        load_application_assets(static)


def test_build_manifest_replaces_startup_hashing_and_fails_closed_on_drift(tmp_path: Path) -> None:
    static = static_tree(tmp_path)
    hashed = load_application_assets(static).hashes
    manifest = tmp_path / STATIC_MANIFEST
    manifest.write_text(json.dumps(hash_static_files(static)), encoding="utf-8")

    assert load_application_assets(static).hashes == hashed

    extra = static / "img" / "late.webp"
    extra.parent.mkdir(exist_ok=True)
    extra.write_bytes(b"late")
    with pytest.raises(RuntimeError, match="does not match"):
        load_application_assets(static)
    extra.unlink()

    robots = static / "robots.txt"
    robots.write_text(robots.read_text(encoding="utf-8") + "# resized\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match="does not match"):
        load_application_assets(static)


@pytest.mark.parametrize("content", ["not json", "[]", '{"/static/robots.txt": {"hash": "XYZ", "size": 1}}'])
def test_malformed_build_manifest_fails_startup(tmp_path: Path, content: str) -> None:
    static = static_tree(tmp_path)
    (tmp_path / STATIC_MANIFEST).write_text(content, encoding="utf-8")
    with pytest.raises(RuntimeError, match="static manifest"):
        load_application_assets(static)
