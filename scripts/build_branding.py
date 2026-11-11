"""Rebuild web branding from the full-resolution public PNG masters."""

from pathlib import Path

from PIL import Image, ImageOps

STATIC = Path(__file__).resolve().parent.parent / "static"


def build_branding(static_dir: Path = STATIC) -> None:
    """Keep small UI assets separate from the reusable full-size downloads."""
    with Image.open(static_dir / "logo.png") as source:
        logo = source.convert("RGBA")
    with Image.open(static_dir / "banner.png") as source:
        banner = source.convert("RGBA")

    logo.resize((80, 80), Image.Resampling.LANCZOS).save(static_dir / "img/logo.webp", quality=85, method=6)
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
        icon.save(static_dir / "img/favicons" / name, optimize=True)
    logo.save(static_dir / "favicon.ico", sizes=[(16, 16), (32, 32), (48, 48)])

    # Fit the complete wide artwork into the established social-preview canvas.
    # A white matte makes the transparent margins independent of viewer themes.
    preview = Image.new("RGB", (1200, 630), "white")
    fitted = ImageOps.contain(banner, (1200, 630), Image.Resampling.LANCZOS)
    preview.paste(fitted, ((1200 - fitted.width) // 2, (630 - fitted.height) // 2), fitted)
    preview.save(static_dir / "img/og-image.jpg", quality=90, subsampling=0, optimize=True, progressive=True)


def main() -> None:
    build_branding()


if __name__ == "__main__":
    main()
