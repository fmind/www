"""Rebuild web branding from the full-resolution public PNG masters."""

import argparse
from collections.abc import Sequence
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any

from PIL import Image, ImageOps

STATIC = Path(__file__).resolve().parent.parent / "static"


def _save_atomically(image: Image.Image, destination: Path, **save_kwargs: Any) -> None:
    """Write a generated asset through a same-directory temp file so failures never truncate targets."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with NamedTemporaryFile(
            dir=destination.parent,
            prefix=f".{destination.name}.",
            suffix=destination.suffix,
            delete=False,
        ) as handle:
            temporary = Path(handle.name)
        image.save(temporary, **save_kwargs)
        temporary.chmod(0o644)
        temporary.replace(destination)
        temporary = None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def build_branding(static_dir: Path = STATIC) -> None:
    """Keep small UI assets separate from the reusable full-size downloads."""
    with Image.open(static_dir / "logo.png") as source:
        logo = source.convert("RGBA")
    with Image.open(static_dir / "banner.png") as source:
        banner = source.convert("RGBA")

    _save_atomically(
        logo.resize((80, 80), Image.Resampling.LANCZOS), static_dir / "img/logo.webp", quality=85, method=6
    )
    for name, size in (
        ("favicon-16x16.png", 16),
        ("favicon-32x32.png", 32),
        ("apple-touch-icon.png", 180),
        ("icon-192.png", 192),
    ):
        icon = logo.resize((size, size), Image.Resampling.LANCZOS)
        if size >= 180:
            # Home-screen icons need an opaque background across platforms.
            background = Image.new("RGBA", icon.size, "white")
            icon = Image.alpha_composite(background, icon).convert("RGB")
        _save_atomically(icon, static_dir / "img/favicons" / name, optimize=True)
    _save_atomically(logo, static_dir / "favicon.ico", sizes=[(16, 16), (32, 32), (48, 48)])

    # Fit the complete wide artwork into the established social-preview canvas.
    # A white matte makes the transparent margins independent of viewer themes.
    preview = Image.new("RGB", (1200, 630), "white")
    fitted = ImageOps.contain(banner, (1200, 630), Image.Resampling.LANCZOS)
    preview.paste(fitted, ((1200 - fitted.width) // 2, (630 - fitted.height) // 2), fitted)
    _save_atomically(
        preview, static_dir / "img/og-image.jpg", quality=90, subsampling=0, optimize=True, progressive=True
    )

    # Pre-build a metadata-free JPEG avatar for the vCard so serving needs no image decoder.
    with Image.open(static_dir / "img/avatar.webp") as source:
        avatar = ImageOps.exif_transpose(source).convert("RGB")
    avatar.info.clear()
    _save_atomically(avatar, static_dir / "img/avatar-vcard.jpg", format="JPEG", quality=85, optimize=True)


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False, suggest_on_error=True)
    parser.parse_args(argv)
    build_branding()


if __name__ == "__main__":
    main()
