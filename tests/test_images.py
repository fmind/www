"""Contract tests for deterministic article-image derivatives."""

from __future__ import annotations

import json
import os
import stat
from hashlib import sha256
from io import StringIO
from pathlib import Path

import PIL
import pytest
from PIL import Image, features

from www import images


def _write_image(path: Path, width: int, height: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (width, height), (22, 47, 64)).save(path)


def test_frozen_derivative_contract_and_source_filtering() -> None:
    assert images.DERIVATIVE_WIDTHS == (800, 1280)
    assert images.DERIVATIVE_QUALITY == 75
    assert images.DERIVATIVE_METHOD == 6
    assert images.derivative_size((1000, 10), 800) == (800, 8)
    assert images.derivative_size((800, 8), 800) == (800, 8)

    expected = {
        "cover.png": True,
        "03.webp": True,
        "Diagram.JPEG": True,
        "cover-800.webp": False,
        "Cover-800.WEBP": False,
        "03-1280.webp": False,
        "demo.mp4": False,
        "notes.txt": False,
    }
    assert {name: images.is_source(Path(name)) for name in expected} == expected
    assert images.derivative_name(Path("example/Diagram.JPEG"), 800) == Path("example/Diagram-800.webp")


def test_generate_derivatives_resizes_every_rung_and_is_byte_idempotent(tmp_path: Path) -> None:
    source = tmp_path / "example" / "cover.png"
    _write_image(source, 2048, 16)

    summary = StringIO()
    images.generate_derivatives(tmp_path, output=summary)

    assert summary.getvalue() == "image derivatives: 1 generated, 0 skipped ([800 1280] px, q75)\n"
    generated = {}
    for width, expected_height in ((800, 6), (1280, 10)):
        target = source.with_name(f"cover-{width}.webp")
        generated[width] = target.read_bytes()
        with Image.open(target) as derivative:
            assert derivative.format == "WEBP"
            assert derivative.size == (width, expected_height)

    summary = StringIO()
    images.generate_derivatives(tmp_path, output=summary)

    assert summary.getvalue() == "image derivatives: 0 generated, 1 skipped ([800 1280] px, q75)\n"
    assert {width: source.with_name(f"cover-{width}.webp").read_bytes() for width in generated} == generated


def test_cover_keeps_required_card_rung_without_upscaling(tmp_path: Path) -> None:
    cover = tmp_path / "small" / "cover.png"
    figure = tmp_path / "small" / "02.webp"
    _write_image(cover, 800, 8)
    _write_image(figure, 500, 300)

    summary = StringIO()
    images.generate_derivatives(tmp_path, output=summary)

    with Image.open(cover.with_name("cover-800.webp")) as derivative:
        assert derivative.size == (800, 8)
    assert not cover.with_name("cover-1280.webp").exists()
    assert not figure.with_name("02-800.webp").exists()
    assert summary.getvalue() == "image derivatives: 1 generated, 1 skipped ([800 1280] px, q75)\n"


def test_generation_validates_existing_target_before_skipping(tmp_path: Path) -> None:
    source = tmp_path / "example" / "cover.png"
    _write_image(source, 1000, 10)
    images.generate_derivatives(tmp_path, output=StringIO())
    target = source.with_name("cover-800.webp")
    generated = target.read_bytes()

    source_time = source.stat().st_mtime_ns
    os.utime(target, ns=(source_time + 1_000_000_000, source_time + 1_000_000_000))
    summary = StringIO()
    images.generate_derivatives(tmp_path, output=summary)
    assert target.read_bytes() == generated
    assert summary.getvalue() == "image derivatives: 0 generated, 1 skipped ([800 1280] px, q75)\n"

    target.write_bytes(b"newer but corrupt")
    os.utime(target, ns=(source_time + 1_000_000_000, source_time + 1_000_000_000))
    summary = StringIO()
    images.generate_derivatives(tmp_path, output=summary)
    assert target.read_bytes() == generated
    assert summary.getvalue() == "image derivatives: 1 generated, 0 skipped ([800 1280] px, q75)\n"


def test_generation_replaces_newer_derivative_after_source_bytes_change(tmp_path: Path) -> None:
    source = tmp_path / "example" / "cover.png"
    lock_path = tmp_path / "image-derivatives.json"
    _write_image(source, 1000, 10)
    images.generate_derivatives(tmp_path, output=StringIO(), lock_path=lock_path)
    target = source.with_name("cover-800.webp")
    original = target.read_bytes()
    original_size = source.stat().st_size

    Image.new("RGB", (1000, 10), (199, 17, 29)).save(source)
    assert source.stat().st_size == original_size
    target_time = target.stat().st_mtime_ns
    os.utime(source, ns=(target_time - 1_000_000, target_time - 1_000_000))

    summary = StringIO()
    images.generate_derivatives(tmp_path, output=summary, lock_path=lock_path)

    assert target.read_bytes() != original
    assert summary.getvalue() == "image derivatives: 1 generated, 0 skipped ([800 1280] px, q75)\n"


def test_locked_generation_repairs_only_a_tampered_target(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = tmp_path / "example" / "cover.png"
    lock_path = tmp_path / "image-derivatives.json"
    _write_image(source, 2048, 16)
    images.generate_derivatives(tmp_path, output=StringIO(), lock_path=lock_path)
    first_target = source.with_name("cover-800.webp")
    second_target = source.with_name("cover-1280.webp")
    expected_first = first_target.read_bytes()
    expected_second = second_target.read_bytes()
    tampered = bytearray(expected_first)
    tampered[-1] ^= 1
    first_target.write_bytes(tampered)

    encoded_targets: list[Path] = []
    original_encode = images._encode  # noqa: SLF001 - spy proves selective regeneration.

    def track_encode(decoded: Image.Image, target: Path, width: int) -> bytes:
        encoded_targets.append(target)
        return original_encode(decoded, target, width)

    monkeypatch.setattr(images, "_encode", track_encode)
    summary = StringIO()
    images.generate_derivatives(tmp_path, output=summary, lock_path=lock_path)

    assert encoded_targets == [first_target]
    assert first_target.read_bytes() == expected_first
    assert second_target.read_bytes() == expected_second
    assert summary.getvalue() == "image derivatives: 1 generated, 0 skipped ([800 1280] px, q75)\n"


def test_locked_generation_reconciles_ladder_changes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = tmp_path / "example" / "cover.png"
    lock_path = tmp_path / "image-derivatives.json"
    _write_image(source, 2048, 16)
    images.generate_derivatives(tmp_path, output=StringIO(), lock_path=lock_path)
    original = {width: source.with_name(f"cover-{width}.webp").read_bytes() for width in images.DERIVATIVE_WIDTHS}

    monkeypatch.setattr(images, "DERIVATIVE_WIDTHS", (800, 1280, 1600))
    summary = StringIO()
    images.generate_derivatives(tmp_path, output=summary, lock_path=lock_path)

    assert source.with_name("cover-1600.webp").is_file()
    assert {width: source.with_name(f"cover-{width}.webp").read_bytes() for width in original} == original
    assert summary.getvalue() == "image derivatives: 1 generated, 0 skipped ([800 1280 1600] px, q75)\n"

    monkeypatch.setattr(images, "DERIVATIVE_WIDTHS", (800,))
    images.generate_derivatives(tmp_path, output=StringIO(), lock_path=lock_path)

    assert source.with_name("cover-800.webp").read_bytes() == original[800]
    assert not source.with_name("cover-1280.webp").exists()
    assert not source.with_name("cover-1600.webp").exists()
    assert json.loads(lock_path.read_text())["widths"] == [800]


def test_locked_generation_reconciles_encoder_recipe_changes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = tmp_path / "example" / "figure.png"
    lock_path = tmp_path / "image-derivatives.json"
    _write_image(source, 1000, 10)
    images.generate_derivatives(tmp_path, output=StringIO(), lock_path=lock_path)
    target = source.with_name("figure-800.webp")
    original = target.read_bytes()
    encoded_targets: list[Path] = []
    original_encode = images._encode  # noqa: SLF001 - spy proves recipe invalidation.

    def track_encode(decoded: Image.Image, target_path: Path, width: int) -> bytes:
        encoded_targets.append(target_path)
        return original_encode(decoded, target_path, width)

    monkeypatch.setattr(images, "_encode", track_encode)
    monkeypatch.setattr(images, "DERIVATIVE_QUALITY", 76)
    images.generate_derivatives(tmp_path, output=StringIO(), lock_path=lock_path)

    assert encoded_targets == [target]
    assert target.read_bytes() != original
    assert json.loads(lock_path.read_text())["recipe"]["quality"] == 76


def test_lock_binds_the_complete_encoder_recipe(tmp_path: Path) -> None:
    source = tmp_path / "example" / "figure.png"
    lock_path = tmp_path / "image-derivatives.json"
    _write_image(source, 1000, 10)

    images.generate_derivatives(tmp_path, output=StringIO(), lock_path=lock_path)

    assert json.loads(lock_path.read_text())["recipe"] == {
        "algorithm": "pillow-webp-bicubic-no-upscale-v1",
        "method": 6,
        "pillow_version": PIL.__version__,
        "quality": 75,
        "webp_version": features.version("webp"),
    }


def test_check_rejects_missing_non_card_target_without_repairing(tmp_path: Path) -> None:
    source = tmp_path / "example" / "figure.png"
    lock_path = tmp_path / "image-derivatives.json"
    _write_image(source, 2048, 16)
    images.generate_derivatives(tmp_path, output=StringIO(), lock_path=lock_path)
    target = source.with_name("figure-1280.webp")
    target.unlink()

    with pytest.raises(images.ImageDerivativeError, match=rf'missing derivative target "{target}"'):
        images.check_derivatives(tmp_path, output=StringIO(), lock_path=lock_path)

    assert not target.exists()


def test_check_is_read_only_for_a_valid_complete_archive(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = tmp_path / "example" / "figure.png"
    lock_path = tmp_path / "image-derivatives.json"
    _write_image(source, 2048, 16)
    images.generate_derivatives(tmp_path, output=StringIO(), lock_path=lock_path)
    paths = [source, source.with_name("figure-800.webp"), source.with_name("figure-1280.webp"), lock_path]
    before = {path: (path.read_bytes(), path.stat().st_mode, path.stat().st_mtime_ns) for path in paths}

    def fail_encode(_decoded: Image.Image, _target: Path, _width: int) -> bytes:
        raise AssertionError("check mode must not encode")

    monkeypatch.setattr(images, "_encode", fail_encode)
    summary = StringIO()
    images.check_derivatives(tmp_path, output=summary, lock_path=lock_path)

    assert summary.getvalue() == "image derivatives: 1 sources and 2 targets verified ([800 1280] px, q75)\n"
    assert {path: (path.read_bytes(), path.stat().st_mode, path.stat().st_mtime_ns) for path in paths} == before


def test_check_rejects_stale_source_without_repairing_targets(tmp_path: Path) -> None:
    source = tmp_path / "example" / "figure.png"
    lock_path = tmp_path / "image-derivatives.json"
    _write_image(source, 2048, 16)
    images.generate_derivatives(tmp_path, output=StringIO(), lock_path=lock_path)
    target = source.with_name("figure-1280.webp")
    target_before = target.read_bytes()
    Image.new("RGB", (2048, 16), (199, 17, 29)).save(source)

    with pytest.raises(images.ImageDerivativeError, match=r"source digest differs from the lock"):
        images.check_derivatives(tmp_path, output=StringIO(), lock_path=lock_path)

    assert target.read_bytes() == target_before


def test_check_rejects_recipe_drift_without_reencoding(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = tmp_path / "example" / "figure.png"
    lock_path = tmp_path / "image-derivatives.json"
    _write_image(source, 1000, 10)
    images.generate_derivatives(tmp_path, output=StringIO(), lock_path=lock_path)
    target = source.with_name("figure-800.webp")
    target_before = target.read_bytes()
    monkeypatch.setattr(images, "DERIVATIVE_METHOD", 5)

    with pytest.raises(images.ImageDerivativeError, match=r"encoder recipe differs from the derivative lock"):
        images.check_derivatives(tmp_path, output=StringIO(), lock_path=lock_path)

    assert target.read_bytes() == target_before


def test_check_rejects_unexpected_source_and_target_files(tmp_path: Path) -> None:
    source = tmp_path / "example" / "figure.png"
    lock_path = tmp_path / "image-derivatives.json"
    _write_image(source, 1000, 10)
    images.generate_derivatives(tmp_path, output=StringIO(), lock_path=lock_path)
    unexpected_source = tmp_path / "example" / "extra.png"
    _write_image(unexpected_source, 10, 10)

    with pytest.raises(images.ImageDerivativeError, match=rf'unexpected source image "{unexpected_source}"'):
        images.check_derivatives(tmp_path, output=StringIO(), lock_path=lock_path)

    unexpected_source.unlink()
    unexpected_target = tmp_path / "example" / "extra-800.webp"
    unexpected_target.write_bytes(source.with_name("figure-800.webp").read_bytes())
    with pytest.raises(images.ImageDerivativeError, match=rf'unexpected derivative target "{unexpected_target}"'):
        images.check_derivatives(tmp_path, output=StringIO(), lock_path=lock_path)


def test_check_rejects_unexpected_non_media_sidecars(tmp_path: Path) -> None:
    source = tmp_path / "example" / "figure.png"
    lock_path = tmp_path / "image-derivatives.json"
    _write_image(source, 1000, 10)
    images.generate_derivatives(tmp_path, output=StringIO(), lock_path=lock_path)
    sidecar = tmp_path / "example" / "figure.webp.tmp"
    sidecar.write_bytes(b"partial output")

    with pytest.raises(images.ImageDerivativeError, match=rf'unexpected article media file "{sidecar}"'):
        images.check_derivatives(tmp_path, output=StringIO(), lock_path=lock_path)


def test_check_rejects_a_regular_file_at_the_image_root(tmp_path: Path) -> None:
    root = tmp_path / "images"
    source = root / "example" / "figure.png"
    lock_path = tmp_path / "image-derivatives.json"
    _write_image(source, 1000, 10)
    images.generate_derivatives(root, output=StringIO(), lock_path=lock_path)
    unexpected = root / "orphan.webp"
    unexpected.write_bytes(source.read_bytes())

    with pytest.raises(images.ImageDerivativeError, match=rf'unexpected article image root entry "{unexpected}"'):
        images.check_derivatives(root, output=StringIO(), lock_path=lock_path)


def test_check_rejects_a_nested_article_image_directory(tmp_path: Path) -> None:
    root = tmp_path / "images"
    source = root / "example" / "figure.png"
    lock_path = tmp_path / "image-derivatives.json"
    _write_image(source, 1000, 10)
    images.generate_derivatives(root, output=StringIO(), lock_path=lock_path)
    nested = source.parent / "nested"
    nested.mkdir()

    with pytest.raises(images.ImageDerivativeError, match=rf'read "{nested}": expected a real regular file'):
        images.check_derivatives(root, output=StringIO(), lock_path=lock_path)


def test_check_validates_target_dimensions_after_its_digest(tmp_path: Path) -> None:
    source = tmp_path / "example" / "figure.png"
    lock_path = tmp_path / "image-derivatives.json"
    _write_image(source, 1000, 10)
    images.generate_derivatives(tmp_path, output=StringIO(), lock_path=lock_path)
    target = source.with_name("figure-800.webp")
    Image.new("RGB", (800, 9), (22, 47, 64)).save(target, format="WEBP")
    lock = json.loads(lock_path.read_text())
    lock["sources"]["example/figure.png"]["targets"]["example/figure-800.webp"] = sha256(
        target.read_bytes()
    ).hexdigest()
    lock_path.write_text(json.dumps(lock, indent=2, sort_keys=True) + "\n")

    with pytest.raises(images.ImageDerivativeError, match=rf'derivative target "{target}" must be 800x8, got 800x9'):
        images.check_derivatives(tmp_path, output=StringIO(), lock_path=lock_path)


def test_check_rejects_non_portable_modes_and_symlinks(tmp_path: Path) -> None:
    source = tmp_path / "example" / "figure.png"
    lock_path = tmp_path / "image-derivatives.json"
    _write_image(source, 1000, 10)
    images.generate_derivatives(tmp_path, output=StringIO(), lock_path=lock_path)
    target = source.with_name("figure-800.webp")
    target.chmod(0o600)

    with pytest.raises(images.ImageDerivativeError, match=rf'mode for "{target}" must be 0644, got 0600'):
        images.check_derivatives(tmp_path, output=StringIO(), lock_path=lock_path)

    target.chmod(0o644)
    external = tmp_path / "external.webp"
    target.replace(external)
    target.symlink_to(external)
    with pytest.raises(images.ImageDerivativeError, match=rf'read "{target}": expected a real regular file'):
        images.check_derivatives(tmp_path, output=StringIO(), lock_path=lock_path)


def test_check_rejects_a_symlinked_lock(tmp_path: Path) -> None:
    source = tmp_path / "example" / "figure.png"
    lock_path = tmp_path / "image-derivatives.json"
    _write_image(source, 1000, 10)
    images.generate_derivatives(tmp_path, output=StringIO(), lock_path=lock_path)
    external = tmp_path / "external-lock.json"
    lock_path.replace(external)
    lock_path.symlink_to(external)

    with pytest.raises(images.ImageDerivativeError, match=r"derivative lock.*symbolic link"):
        images.check_derivatives(tmp_path, output=StringIO(), lock_path=lock_path)


def test_check_rejects_a_symlinked_image_root(tmp_path: Path) -> None:
    root = tmp_path / "images"
    source = root / "example" / "figure.png"
    lock_path = tmp_path / "image-derivatives.json"
    _write_image(source, 1000, 10)
    images.generate_derivatives(root, output=StringIO(), lock_path=lock_path)
    linked_root = tmp_path / "linked-images"
    linked_root.symlink_to(root, target_is_directory=True)

    with pytest.raises(images.ImageDerivativeError, match=r"image root.*crosses symbolic link"):
        images.check_derivatives(linked_root, output=StringIO(), lock_path=lock_path)


@pytest.mark.parametrize("contents", [None, "not JSON", '{"version": 1, "widths": [], "sources": []}'])
def test_required_lock_fails_closed_before_writing_outputs(tmp_path: Path, contents: str | None) -> None:
    source = tmp_path / "example" / "cover.png"
    lock_path = tmp_path / "image-derivatives.json"
    _write_image(source, 1000, 10)
    if contents is not None:
        lock_path.write_text(contents)

    with pytest.raises(images.ImageDerivativeError, match=rf'^read derivative lock "{lock_path}":'):
        images.generate_derivatives(
            tmp_path,
            output=StringIO(),
            lock_path=lock_path,
            require_lock=True,
        )

    assert not source.with_name("cover-800.webp").exists()


def test_generated_derivative_and_lock_modes_are_world_readable(tmp_path: Path) -> None:
    source = tmp_path / "example" / "cover.png"
    lock_path = tmp_path / "image-derivatives.json"
    _write_image(source, 1000, 10)

    images.generate_derivatives(tmp_path, output=StringIO(), lock_path=lock_path)

    assert stat.S_IMODE(source.with_name("cover-800.webp").stat().st_mode) == 0o644
    assert stat.S_IMODE(lock_path.stat().st_mode) == 0o644


@pytest.mark.parametrize(
    ("target_format", "target_size"),
    [("PNG", (800, 8)), ("WEBP", (799, 8)), ("WEBP", (800, 9))],
)
def test_unlocked_generation_replaces_newer_wrong_format_or_size(
    tmp_path: Path, target_format: str, target_size: tuple[int, int]
) -> None:
    source = tmp_path / "example" / "cover.png"
    _write_image(source, 1000, 10)
    target = source.with_name("cover-800.webp")
    Image.new("RGB", target_size, (99, 88, 77)).save(target, format=target_format)
    source_time = source.stat().st_mtime_ns
    os.utime(target, ns=(source_time + 1_000_000_000, source_time + 1_000_000_000))

    images.generate_derivatives(tmp_path, output=StringIO())

    with Image.open(target) as derivative:
        derivative.load()
        assert derivative.format == "WEBP"
        assert derivative.size == (800, 8)


def test_failed_atomic_replace_preserves_target_and_cleans_temporary_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "example" / "cover.png"
    _write_image(source, 1000, 10)
    images.generate_derivatives(tmp_path, output=StringIO())
    target = source.with_name("cover-800.webp")
    original = target.read_bytes()
    Image.new("RGB", (1000, 10), (99, 88, 77)).save(source)

    def fail_replace(temporary_path: Path, destination: str | os.PathLike[str]) -> None:
        assert temporary_path.parent == target.parent
        assert Path(destination) == target
        assert temporary_path.read_bytes()
        raise OSError("interrupted replace")

    monkeypatch.setattr(Path, "replace", fail_replace)
    with pytest.raises(images.ImageDerivativeError, match=rf'^replace "{target}": interrupted replace$'):
        images.generate_derivatives(tmp_path, output=StringIO())

    assert target.read_bytes() == original
    assert list(target.parent.glob(f".{target.name}.*.tmp")) == []


def test_failed_atomic_fsync_preserves_target_and_cleans_temporary_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "example" / "cover.png"
    _write_image(source, 1000, 10)
    images.generate_derivatives(tmp_path, output=StringIO())
    target = source.with_name("cover-800.webp")
    original = target.read_bytes()
    Image.new("RGB", (1000, 10), (99, 88, 77)).save(source)

    def fail_fsync(_descriptor: int) -> None:
        raise OSError("interrupted fsync")

    monkeypatch.setattr(images.os, "fsync", fail_fsync)
    with pytest.raises(images.ImageDerivativeError, match=rf'^write "{target}": interrupted fsync$'):
        images.generate_derivatives(tmp_path, output=StringIO())

    assert target.read_bytes() == original
    assert list(target.parent.glob(f".{target.name}.*.tmp")) == []


def test_failed_atomic_lock_replace_preserves_lock_and_retry_converges(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "example" / "cover.png"
    lock_path = tmp_path / "image-derivatives.json"
    _write_image(source, 1000, 10)
    images.generate_derivatives(tmp_path, output=StringIO(), lock_path=lock_path)
    original_lock = lock_path.read_bytes()
    Image.new("RGB", (1000, 10), (99, 88, 77)).save(source)
    replace = Path.replace

    def fail_lock_replace(path: Path, destination: str | os.PathLike[str]) -> Path:
        if Path(destination) == lock_path:
            raise OSError("interrupted lock replace")
        return replace(path, destination)

    monkeypatch.setattr(Path, "replace", fail_lock_replace)
    with pytest.raises(images.ImageDerivativeError, match=rf'^replace "{lock_path}": interrupted lock replace$'):
        images.generate_derivatives(tmp_path, output=StringIO(), lock_path=lock_path)

    assert lock_path.read_bytes() == original_lock
    assert list(lock_path.parent.glob(f".{lock_path.name}.*.tmp")) == []
    monkeypatch.undo()
    summary = StringIO()
    images.generate_derivatives(tmp_path, output=summary, lock_path=lock_path)
    assert lock_path.read_bytes() != original_lock
    assert summary.getvalue() == "image derivatives: 0 generated, 1 skipped ([800 1280] px, q75)\n"


def test_generation_fails_closed_with_stable_context(tmp_path: Path) -> None:
    with pytest.raises(images.ImageDerivativeError, match=r'^list article images: no source images under ".+"$'):
        images.generate_derivatives(tmp_path, output=StringIO())

    first = tmp_path / "a" / "cover.png"
    second = tmp_path / "b" / "cover.png"
    first.parent.mkdir()
    second.parent.mkdir()
    first.write_bytes(b"not an image")
    second.write_bytes(b"also not an image")

    with pytest.raises(images.ImageDerivativeError, match=rf'^decode "{first}":'):
        images.generate_derivatives(tmp_path, output=StringIO())


@pytest.mark.parametrize("name", ["figure.webp", "figure.png", "figure.jpg", "figure.JPEG", "figure.gif"])
def test_generation_decodes_every_supported_source_format(tmp_path: Path, name: str) -> None:
    source = tmp_path / "example" / name
    _write_image(source, 1000, 10)

    images.generate_derivatives(tmp_path, output=StringIO())

    with Image.open(source.with_name("figure-800.webp")) as derivative:
        assert derivative.size == (800, 8)


def test_generation_contextualizes_target_and_summary_io_errors(tmp_path: Path) -> None:
    source = tmp_path / "example" / "cover.png"
    _write_image(source, 1000, 10)
    target = source.with_name("cover-800.webp")
    target.mkdir()

    with pytest.raises(images.ImageDerivativeError, match=rf'^read "{target}":'):
        images.generate_derivatives(tmp_path, output=StringIO())

    target.rmdir()

    class BrokenOutput(StringIO):
        def write(self, _value: str) -> int:
            raise OSError("closed pipe")

    with pytest.raises(images.ImageDerivativeError, match=r"^write summary: closed pipe$"):
        images.generate_derivatives(tmp_path, output=BrokenOutput())


def test_main_requires_lock_repairs_targets_and_reports_failures(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    source = tmp_path / "example" / "cover.png"
    lock_path = tmp_path / "image-derivatives.json"
    _write_image(source, 1000, 10)
    images.generate_derivatives(tmp_path, output=StringIO(), lock_path=lock_path)
    source.with_name("cover-800.webp").unlink()
    monkeypatch.setattr(images, "ARTICLE_IMAGE_ROOT", tmp_path)
    monkeypatch.setattr(images, "DERIVATIVE_LOCK_PATH", lock_path)
    images.main()

    captured = capsys.readouterr()
    assert captured.out == "image derivatives: 1 generated, 0 skipped ([800 1280] px, q75)\n"
    assert captured.err == ""

    target = source.with_name("cover-800.webp")
    target.write_bytes(b"newer target")
    source_time = source.stat().st_mtime_ns
    os.utime(target, ns=(source_time + 1_000_000_000, source_time + 1_000_000_000))
    images.main()
    assert capsys.readouterr().out == "image derivatives: 1 generated, 0 skipped ([800 1280] px, q75)\n"
    with Image.open(target) as derivative:
        derivative.load()
        assert derivative.format == "WEBP"
        assert derivative.size == (800, 8)

    empty = tmp_path / "empty"
    empty.mkdir()
    monkeypatch.setattr(images, "ARTICLE_IMAGE_ROOT", empty)
    with pytest.raises(SystemExit, match="1"):
        images.main()
    assert (
        capsys.readouterr().err
        == f'generate image derivatives: list article images: no source images under "{empty}"\n'
    )


def test_main_check_mode_is_read_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    source = tmp_path / "example" / "figure.png"
    lock_path = tmp_path / "image-derivatives.json"
    _write_image(source, 1000, 10)
    images.generate_derivatives(tmp_path, output=StringIO(), lock_path=lock_path)
    target = source.with_name("figure-800.webp")
    before = {path: path.stat().st_mtime_ns for path in (source, target, lock_path)}
    monkeypatch.setattr(images, "ARTICLE_IMAGE_ROOT", tmp_path)
    monkeypatch.setattr(images, "DERIVATIVE_LOCK_PATH", lock_path)

    images.main(["--check"])

    captured = capsys.readouterr()
    assert captured.out == "image derivatives: 1 sources and 1 targets verified ([800 1280] px, q75)\n"
    assert captured.err == ""
    assert {path: path.stat().st_mtime_ns for path in (source, target, lock_path)} == before
