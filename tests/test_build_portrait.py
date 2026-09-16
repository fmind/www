"""Exercise public portrait export with actual camera/contact metadata."""

from pathlib import Path

import pytest
from PIL import Image, ImageCms

from scripts.build_portrait import STATIC, export_portrait


def test_export_drops_personal_metadata_and_preserves_orientation_and_profile(tmp_path: Path) -> None:
    master = tmp_path / "master.jpg"
    output = tmp_path / "public.jpg"
    profile = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()
    exif = Image.Exif()
    exif[274] = 6
    exif[315] = "Private photographer"
    Image.new("RGB", (12, 8), "blue").save(
        master, exif=exif, icc_profile=profile, xmp=b'<contact phone="private"/>', comment=b"private comment"
    )
    export_portrait(master, output)
    with Image.open(output) as result:
        assert result.size == (8, 12)
        assert result.info["icc_profile"] == profile
        assert not result.getexif()
        assert not {"xmp", "photoshop", "comment"}.intersection(result.info)
        pixel = result.getpixel((0, 0))
        assert isinstance(pixel, tuple)
        assert pixel[2] > 240
    first = output.read_bytes()
    export_portrait(master, output)
    assert output.read_bytes() == first


def test_export_rejects_a_public_master(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="outside static"):
        export_portrait(STATIC / "portrait.jpg", tmp_path / "public.jpg")


def test_export_reports_unreadable_master(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="check the JPEG master") as raised:
        export_portrait(tmp_path / "missing.jpg", tmp_path / "public.jpg")
    assert isinstance(raised.value.__cause__, OSError)


def test_export_rejects_non_jpeg(tmp_path: Path) -> None:
    master = tmp_path / "master.png"
    Image.new("RGB", (2, 2)).save(master)
    with pytest.raises(ValueError, match="must be a JPEG"):
        export_portrait(master, tmp_path / "public.jpg")
