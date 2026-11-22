"""Export the public portrait from a private JPEG master without personal metadata."""

import argparse
import tempfile
from collections.abc import Sequence
from pathlib import Path

from PIL import Image, ImageOps

STATIC = Path(__file__).resolve().parent.parent / "static"
# 2048px covers retina and press use; the 3771px master exported to a 3 MB download.
MAX_SIDE = 2048


def export_portrait(source: Path, destination: Path) -> None:
    """Retain orientation and the color profile, dropping camera and contact records."""
    if source.resolve().is_relative_to(STATIC.resolve()):
        raise ValueError("keep the original portrait outside static/ and pass that private master")
    temporary: Path | None = None
    try:
        with Image.open(source) as original:
            # Pillow reports a JPEG that embeds an MPF secondary image (camera preview or
            # Ultra HDR gain map) as MPO; the export keeps only the primary frame.
            if original.format not in {"JPEG", "MPO"}:
                raise ValueError("portrait master must be a JPEG image")
            profile = original.info.get("icc_profile")
            portrait = ImageOps.exif_transpose(original).convert("RGB")
            portrait.thumbnail((MAX_SIDE, MAX_SIDE), Image.Resampling.LANCZOS)
            portrait.info.clear()
            with tempfile.NamedTemporaryFile(
                dir=destination.parent, prefix=f".{destination.name}.", suffix=".tmp", delete=False
            ) as handle:
                temporary = Path(handle.name)
            portrait.save(temporary, "JPEG", quality=90, optimize=True, progressive=True, icc_profile=profile)
            temporary.chmod(0o644)
            temporary.replace(destination)
            temporary = None
    except OSError as error:
        raise RuntimeError("cannot export portrait: check the JPEG master and destination permissions") from error
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False, suggest_on_error=True)
    parser.add_argument("source", type=Path, help="JPEG master outside the public static tree")
    arguments = parser.parse_args(argv)
    export_portrait(arguments.source, STATIC / "portrait.jpg")


if __name__ == "__main__":
    main()
