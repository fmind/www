"""Export the public portrait from a private JPEG master without personal metadata."""

import argparse
from pathlib import Path

from PIL import Image, ImageOps

STATIC = Path(__file__).resolve().parent.parent / "static"


def export_portrait(source: Path, destination: Path) -> None:
    """Retain orientation and the color profile, dropping camera and contact records."""
    if source.resolve().is_relative_to(STATIC.resolve()):
        raise ValueError("keep the original portrait outside static/ and pass that private master")
    try:
        with Image.open(source) as original:
            if original.format != "JPEG":
                raise ValueError("portrait master must be a JPEG image")
            profile = original.info.get("icc_profile")
            portrait = ImageOps.exif_transpose(original).convert("RGB")
            portrait.info.clear()
            portrait.save(destination, "JPEG", quality=95, optimize=True, progressive=True, icc_profile=profile)
    except OSError as error:
        raise RuntimeError("cannot export portrait: check the JPEG master and destination permissions") from error


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="JPEG master outside the public static tree")
    arguments = parser.parse_args()
    export_portrait(arguments.source, STATIC / "portrait.jpg")


if __name__ == "__main__":
    main()
