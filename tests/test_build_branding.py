"""Branding asset generation keeps UI derivatives small, clean, and self-contained."""

from pathlib import Path

from PIL import Image

from scripts.build_branding import build_branding


def test_build_branding_writes_sized_ui_assets_without_unused_icons(tmp_path: Path) -> None:
    (tmp_path / "img" / "favicons").mkdir(parents=True)
    Image.new("RGBA", (512, 512), (26, 115, 232, 255)).save(tmp_path / "logo.png")
    Image.new("RGBA", (1600, 600), (26, 115, 232, 255)).save(tmp_path / "banner.png")

    build_branding(tmp_path)

    with Image.open(tmp_path / "img/logo.webp") as logo:
        assert (logo.format, logo.size) == ("WEBP", (80, 80))
    for name, size, mode in (
        ("favicon-16x16.png", 16, "RGBA"),
        ("favicon-32x32.png", 32, "RGBA"),
        ("apple-touch-icon.png", 180, "RGB"),
        ("icon-192.png", 192, "RGB"),
    ):
        with Image.open(tmp_path / "img/favicons" / name) as icon:
            assert (icon.format, icon.size, icon.mode) == ("PNG", (size, size), mode)
    assert not (tmp_path / "img/favicons/icon-512.png").exists()
    with Image.open(tmp_path / "favicon.ico") as favicon:
        assert favicon.format == "ICO"
    with Image.open(tmp_path / "img/og-image.jpg") as preview:
        assert (preview.format, preview.size, preview.mode) == ("JPEG", (1200, 630), "RGB")
        assert preview.info.get("progressive")
