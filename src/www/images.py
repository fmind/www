"""Generate deterministic WebP derivatives for article images."""

from __future__ import annotations

import json
import os
import stat
import sys
from argparse import ArgumentParser
from collections.abc import Sequence
from dataclasses import dataclass
from hashlib import sha256
from io import BytesIO
from pathlib import Path, PurePosixPath
from tempfile import NamedTemporaryFile
from typing import Annotated, TextIO

import PIL
from PIL import Image, features
from pydantic import AfterValidator, BaseModel, ConfigDict, Field, field_validator

from www.models import CARD_COVER_WIDTH, DERIVATIVE_WIDTHS

ARTICLE_IMAGE_ROOT = Path("static/img/articles")
DERIVATIVE_LOCK_PATH = Path("assets/image-derivatives.json")
DERIVATIVE_QUALITY = 75
DERIVATIVE_METHOD = 6
GENERATED_FILE_MODE = 0o644
_COVER_STEM = "cover"
# Bump this identifier whenever resizing, color handling, or encoder semantics change;
# the library versions below bind the native codec implementation as well.
_ENCODER_ALGORITHM = "pillow-webp-bicubic-no-upscale-v1"
_LOCK_VERSION = 2
_SOURCE_EXTENSIONS = frozenset({".webp", ".png", ".jpg", ".jpeg", ".gif"})
# Article Markdown deliberately promotes local MP4 image syntax into video markup.
_ARTICLE_MEDIA_EXTENSIONS = _SOURCE_EXTENSIONS | {".mp4"}


class ImageDerivativeError(RuntimeError):
    """An article-image derivative could not be generated safely."""


def _trimmed(value: str) -> str:
    if not value or value.strip() != value:
        raise ValueError("expected a non-empty trimmed string")
    return value


type _Trimmed = Annotated[str, AfterValidator(_trimmed)]
type _Digest = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$", min_length=64, max_length=64)]


class _StrictModel(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)


class _LockEntry(_StrictModel):
    source_sha256: _Digest = Field(alias="sha256")
    targets: dict[str, _Digest]


class _EncoderRecipe(_StrictModel):
    algorithm: _Trimmed
    method: Annotated[int, Field(ge=0, le=6)]
    pillow_version: _Trimmed
    quality: Annotated[int, Field(ge=0, le=100)]
    webp_version: _Trimmed


class _LockDocument(_StrictModel):
    version: Annotated[int, Field(ge=_LOCK_VERSION, le=_LOCK_VERSION)]
    recipe: _EncoderRecipe
    widths: Annotated[list[Annotated[int, Field(gt=0)]], Field(min_length=1)]
    sources: dict[str, _LockEntry]

    @field_validator("widths")
    @classmethod
    def ascending_widths(cls, widths: list[int]) -> list[int]:
        if widths != sorted(set(widths)):
            raise ValueError("widths must be ascending and unique")
        return widths


@dataclass(frozen=True, slots=True)
class _DerivativeLock:
    recipe: _EncoderRecipe | None
    widths: tuple[int, ...]
    sources: dict[str, _LockEntry]


def is_source(path: Path) -> bool:
    """Return whether a path names an authored image rather than a derivative."""
    extension = path.suffix
    if extension.lower() not in _SOURCE_EXTENSIONS:
        return False
    stem = path.name[: -len(extension)]
    return not any(stem.endswith(f"-{width}") for width in DERIVATIVE_WIDTHS)


def derivative_name(source: Path, width: int) -> Path:
    """Return the renderer-owned filename for one source and ladder width."""
    return source.with_name(f"{source.stem}-{width}.webp")


def derivative_size(source_size: tuple[int, int], width: int) -> tuple[int, int]:
    """Return a proportional target size without upscaling the source."""
    source_width, source_height = source_size
    if source_width <= width:
        return source_size
    return width, source_height * width // source_width


def _read(source: Path) -> bytes:
    try:
        metadata = source.lstat()
        if stat.S_ISLNK(metadata.st_mode):
            raise ImageDerivativeError(f'read "{source}": symbolic links are not allowed')
        if not stat.S_ISREG(metadata.st_mode):
            raise ImageDerivativeError(f'read "{source}": expected a regular file')
        return source.read_bytes()
    except OSError as error:
        raise ImageDerivativeError(f'read "{source}": {error}') from error


def _decode(source: Path, data: bytes | None = None) -> Image.Image:
    source_data = _read(source) if data is None else data
    try:
        with Image.open(BytesIO(source_data)) as decoded:
            # Loading before the byte buffer closes also makes decode failures
            # surface at the boundary carrying the source path.
            decoded.load()
            return decoded.copy()
    except (OSError, ValueError) as error:
        raise ImageDerivativeError(f'decode "{source}": {error}') from error


def _encode(decoded: Image.Image, target: Path, width: int) -> bytes:
    output_image = decoded
    size = derivative_size(decoded.size, width)
    if size != decoded.size:
        # Pillow's bicubic filter is the direct cubic-resampling counterpart to
        # the Go generator's Catmull-Rom scaler.
        output_image = decoded.resize(size, Image.Resampling.BICUBIC)
    encoded = BytesIO()
    try:
        output_image.save(
            encoded,
            format="WEBP",
            quality=DERIVATIVE_QUALITY,
            method=DERIVATIVE_METHOD,
        )
    except (OSError, ValueError) as error:
        raise ImageDerivativeError(f'encode "{target}": {error}') from error
    finally:
        if output_image is not decoded:
            output_image.close()
    return encoded.getvalue()


def _write_atomically(target: Path, data: bytes) -> None:
    temporary: Path | None = None
    try:
        try:
            with NamedTemporaryFile(
                mode="wb",
                dir=target.parent,
                prefix=f".{target.name}.",
                suffix=".tmp",
                delete=False,
            ) as destination:
                temporary = Path(destination.name)
                destination.write(data)
                destination.flush()
                os.fchmod(destination.fileno(), GENERATED_FILE_MODE)
                os.fsync(destination.fileno())
        except OSError as error:
            raise ImageDerivativeError(f'write "{target}": {error}') from error

        if temporary is None:
            raise ImageDerivativeError(f'write "{target}": temporary path unavailable')
        try:
            temporary.replace(target)
        except OSError as error:
            raise ImageDerivativeError(f'replace "{target}": {error}') from error
        temporary = None
    finally:
        if temporary is not None:
            try:
                temporary.unlink(missing_ok=True)
            except OSError as error:
                raise ImageDerivativeError(f'clean temporary for "{target}": {error}') from error


def _set_generated_mode(path: Path) -> bool:
    try:
        if stat.S_IMODE(path.stat().st_mode) == GENERATED_FILE_MODE:
            return False
        path.chmod(GENERATED_FILE_MODE)
    except OSError as error:
        raise ImageDerivativeError(f'chmod "{path}": {error}') from error
    return True


def _digest(data: bytes) -> str:
    return sha256(data).hexdigest()


def _current_recipe() -> _EncoderRecipe:
    webp_version = features.version("webp")
    if webp_version is None:
        raise ImageDerivativeError("Pillow was built without WebP encoder support")
    return _EncoderRecipe(
        algorithm=_ENCODER_ALGORITHM,
        method=DERIVATIVE_METHOD,
        pillow_version=PIL.__version__,
        quality=DERIVATIVE_QUALITY,
        webp_version=webp_version,
    )


def _relative_name(root: Path, path: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError as error:
        raise ImageDerivativeError(f'path "{path}" is outside image root "{root}"') from error


def _reject_symlink_components(path: Path, *, label: str) -> None:
    absolute = path if path.is_absolute() else Path.cwd() / path
    current = Path(absolute.anchor)
    for component in absolute.parts[1:]:
        current /= component
        try:
            metadata = current.lstat()
        except FileNotFoundError:
            return
        except OSError as error:
            raise ImageDerivativeError(f'inspect {label} "{path}": {error}') from error
        if stat.S_ISLNK(metadata.st_mode):
            raise ImageDerivativeError(f'{label} "{path}" crosses symbolic link "{current}"')


def _validated_relative_path(value: object, *, field: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field} must be a string")
    path = PurePosixPath(value)
    if path.is_absolute() or len(path.parts) != 2 or path.as_posix() != value or ".." in path.parts:
        raise ValueError(f'{field} must be a two-level relative POSIX path, got "{value}"')
    return value


def _parse_lock(data: object) -> _DerivativeLock:
    document = _LockDocument.model_validate(data)
    widths = tuple(document.widths)
    # Shape validation cannot establish filename ownership; retain this explicit
    # check before any supplied path can affect the derivative archive.
    for source_name, entry in document.sources.items():
        source_path = PurePosixPath(_validated_relative_path(source_name, field="source path"))
        valid_targets = {source_path.with_name(f"{source_path.stem}-{width}.webp").as_posix() for width in widths}
        for target_name in entry.targets:
            _validated_relative_path(target_name, field="target path")
            if target_name not in valid_targets:
                raise ValueError(f'target "{target_name}" does not belong to source "{source_name}"')
    return _DerivativeLock(recipe=document.recipe, widths=widths, sources=document.sources)


def _load_lock(path: Path, *, required: bool) -> _DerivativeLock:
    _reject_symlink_components(path, label="derivative lock")
    try:
        metadata = path.lstat()
    except FileNotFoundError as error:
        if not required:
            return _DerivativeLock(recipe=None, widths=(), sources={})
        raise ImageDerivativeError(f'read derivative lock "{path}": {error}') from error
    except OSError as error:
        raise ImageDerivativeError(f'read derivative lock "{path}": {error}') from error
    if stat.S_ISLNK(metadata.st_mode):
        raise ImageDerivativeError(f'read derivative lock "{path}": symbolic links are not allowed')
    if not stat.S_ISREG(metadata.st_mode):
        raise ImageDerivativeError(f'read derivative lock "{path}": expected a regular file')
    try:
        data = path.read_bytes()
    except OSError as error:
        raise ImageDerivativeError(f'read derivative lock "{path}": {error}') from error
    try:
        return _parse_lock(json.loads(data))
    except (json.JSONDecodeError, UnicodeDecodeError, ValueError) as error:
        raise ImageDerivativeError(f'read derivative lock "{path}": {error}') from error


def _lock_bytes(lock: _DerivativeLock) -> bytes:
    if lock.recipe is None:
        raise ImageDerivativeError("cannot serialize a derivative lock without an encoder recipe")
    payload = {
        "recipe": lock.recipe.model_dump(),
        "version": _LOCK_VERSION,
        "widths": list(lock.widths),
        "sources": {name: entry.model_dump(by_alias=True) for name, entry in lock.sources.items()},
    }
    return (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode()


def _write_lock(path: Path, lock: _DerivativeLock) -> None:
    data = _lock_bytes(lock)
    try:
        existing = path.read_bytes()
    except FileNotFoundError:
        existing = None
    except OSError as error:
        raise ImageDerivativeError(f'read "{path}": {error}') from error
    if existing == data:
        _set_generated_mode(path)
        return
    _write_atomically(path, data)


def write_derivative(decoded: Image.Image, target: Path, width: int) -> bool:
    """Write a rung only when its deterministic encoded bytes have changed."""
    data = _encode(decoded, target, width)
    try:
        existing = target.read_bytes()
    except FileNotFoundError:
        existing = None
    except OSError as error:
        raise ImageDerivativeError(f'read "{target}": {error}') from error
    if existing == data:
        return _set_generated_mode(target)
    _write_atomically(target, data)
    return True


def _is_cover(source: Path) -> bool:
    return source.stem == _COVER_STEM


def _eligible_widths(source: Path, source_width: int) -> tuple[int, ...]:
    return tuple(
        width
        for width in DERIVATIVE_WIDTHS
        if source_width > width or (width == CARD_COVER_WIDTH and _is_cover(source))
    )


def generate_derivative(source: Path) -> bool:
    """Verify every eligible rung against its source and report byte changes."""
    decoded = _decode(source)
    changed = False
    try:
        for width in _eligible_widths(source, decoded.width):
            target = derivative_name(source, width)
            changed = write_derivative(decoded, target, width) or changed
    finally:
        decoded.close()
    return changed


def _read_optional_target(target: Path) -> bytes | None:
    try:
        metadata = target.lstat()
    except FileNotFoundError:
        return None
    except OSError as error:
        raise ImageDerivativeError(f'read "{target}": {error}') from error
    if stat.S_ISLNK(metadata.st_mode):
        raise ImageDerivativeError(f'read "{target}": symbolic links are not allowed')
    if not stat.S_ISREG(metadata.st_mode):
        raise ImageDerivativeError(f'read "{target}": expected a regular file')
    try:
        return target.read_bytes()
    except OSError as error:
        raise ImageDerivativeError(f'read "{target}": {error}') from error


def _ensure_locked_target(
    decoded: Image.Image,
    target: Path,
    width: int,
    trusted_digest: str | None,
) -> tuple[str, bool]:
    existing = _read_optional_target(target)
    if existing is not None and trusted_digest is not None and _digest(existing) == trusted_digest:
        return trusted_digest, _set_generated_mode(target)

    encoded = _encode(decoded, target, width)
    encoded_digest = _digest(encoded)
    if existing == encoded:
        return encoded_digest, _set_generated_mode(target)
    _write_atomically(target, encoded)
    return encoded_digest, True


def _remove_obsolete_target(target: Path) -> bool:
    try:
        target.unlink()
    except FileNotFoundError:
        return False
    except OSError as error:
        raise ImageDerivativeError(f'remove obsolete derivative "{target}": {error}') from error
    return True


def _locked_target_names(lock: _DerivativeLock) -> set[str]:
    return {target for entry in lock.sources.values() for target in entry.targets}


def _scan_image_tree(root: Path, *, allowed_root_file: Path | None = None) -> list[Path]:
    _reject_symlink_components(root, label="image root")
    try:
        root_metadata = root.lstat()
    except OSError as error:
        raise ImageDerivativeError(f'inspect image root "{root}": {error}') from error
    if stat.S_ISLNK(root_metadata.st_mode) or not stat.S_ISDIR(root_metadata.st_mode):
        raise ImageDerivativeError(f'image root "{root}" must be a real directory')

    files: list[Path] = []
    try:
        directories = sorted(root.iterdir())
    except OSError as error:
        raise ImageDerivativeError(f"list article image directories: {error}") from error
    for directory in directories:
        try:
            directory_metadata = directory.lstat()
        except OSError as error:
            raise ImageDerivativeError(f'inspect article image directory "{directory}": {error}') from error
        if stat.S_ISLNK(directory_metadata.st_mode):
            raise ImageDerivativeError(f'article image path "{directory}" must be a real directory')
        if stat.S_ISREG(directory_metadata.st_mode):
            # Tests and library callers may colocate the explicitly supplied lock
            # with the image root; every other root entry would escape membership.
            if allowed_root_file is not None and directory.absolute() == allowed_root_file.absolute():
                continue
            raise ImageDerivativeError(f'unexpected article image root entry "{directory}"')
        if not stat.S_ISDIR(directory_metadata.st_mode):
            raise ImageDerivativeError(f'article image path "{directory}" must be a real directory')
        try:
            entries = sorted(directory.iterdir())
        except OSError as error:
            raise ImageDerivativeError(f'list article image directory "{directory}": {error}') from error
        for path in entries:
            try:
                metadata = path.lstat()
            except OSError as error:
                raise ImageDerivativeError(f'inspect article image path "{path}": {error}') from error
            if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
                raise ImageDerivativeError(f'read "{path}": expected a real regular file')
            files.append(path)
    return files


def _discover_sources(root: Path, lock: _DerivativeLock | None, lock_path: Path | None) -> list[Path]:
    known_targets = _locked_target_names(lock) if lock is not None else set()
    return [
        path
        for path in _scan_image_tree(root, allowed_root_file=lock_path)
        if _relative_name(root, path) not in known_targets and is_source(path)
    ]


def _generate_locked(
    root: Path,
    sources: list[Path],
    old_lock: _DerivativeLock,
    recipe: _EncoderRecipe,
) -> tuple[_DerivativeLock, int]:
    new_entries: dict[str, _LockEntry] = {}
    changed_sources: set[str] = set()
    current_targets: set[str] = set()

    for source in sources:
        source_name = _relative_name(root, source)
        source_data = _read(source)
        source_digest = _digest(source_data)
        old_entry = old_lock.sources.get(source_name)
        decoded = _decode(source, source_data)
        target_digests: dict[str, str] = {}
        try:
            for width in _eligible_widths(source, decoded.width):
                target = derivative_name(source, width)
                target_name = _relative_name(root, target)
                current_targets.add(target_name)
                trusted_digest = None
                if old_lock.recipe == recipe and old_entry is not None and old_entry.source_sha256 == source_digest:
                    trusted_digest = old_entry.targets.get(target_name)
                target_digest, changed = _ensure_locked_target(
                    decoded,
                    target,
                    width,
                    trusted_digest,
                )
                target_digests[target_name] = target_digest
                if changed:
                    changed_sources.add(source_name)
        finally:
            decoded.close()
        new_entries[source_name] = _LockEntry(
            sha256=source_digest,
            targets=target_digests,
        )

    obsolete_targets = _locked_target_names(old_lock) - current_targets
    current_source_names = set(new_entries)
    for target_name in sorted(obsolete_targets):
        if _remove_obsolete_target(root / PurePosixPath(target_name)):
            old_owner = next(
                (source_name for source_name, entry in old_lock.sources.items() if target_name in entry.targets),
                None,
            )
            if old_owner in current_source_names:
                changed_sources.add(old_owner)

    return (
        _DerivativeLock(recipe=recipe, widths=tuple(DERIVATIVE_WIDTHS), sources=new_entries),
        len(changed_sources),
    )


def _require_mode(path: Path) -> None:
    try:
        mode = stat.S_IMODE(path.lstat().st_mode)
    except OSError as error:
        raise ImageDerivativeError(f'inspect mode for "{path}": {error}') from error
    if mode != GENERATED_FILE_MODE:
        raise ImageDerivativeError(f'mode for "{path}" must be 0644, got {mode:04o}')


def _image_details(path: Path, data: bytes) -> tuple[str | None, tuple[int, int]]:
    try:
        with Image.open(BytesIO(data)) as decoded:
            decoded.load()
            return decoded.format, decoded.size
    except (OSError, ValueError) as error:
        raise ImageDerivativeError(f'decode "{path}": {error}') from error


def _write_summary(output: TextIO | None, summary: str) -> None:
    destination = sys.stdout if output is None else output
    try:
        destination.write(summary)
    except (OSError, ValueError) as error:
        raise ImageDerivativeError(f"write summary: {error}") from error


def check_derivatives(root: Path, *, lock_path: Path, output: TextIO | None = None) -> None:
    """Validate the complete derivative archive without changing filesystem state."""
    lock = _load_lock(lock_path, required=True)
    _require_mode(lock_path)
    recipe = _current_recipe()
    if lock.recipe != recipe:
        raise ImageDerivativeError("encoder recipe differs from the derivative lock; run `mise run build:images`")
    if lock.widths != tuple(DERIVATIVE_WIDTHS):
        raise ImageDerivativeError(
            f"derivative widths differ from the lock: expected {list(DERIVATIVE_WIDTHS)}, got {list(lock.widths)}; "
            "run `mise run build:images`"
        )

    files = _scan_image_tree(root, allowed_root_file=lock_path)
    if unexpected_media := next(
        (path for path in files if path.suffix.lower() not in _ARTICLE_MEDIA_EXTENSIONS),
        None,
    ):
        raise ImageDerivativeError(f'unexpected article media file "{unexpected_media}"')
    image_paths = {_relative_name(root, path): path for path in files if path.suffix.lower() in _SOURCE_EXTENSIONS}
    source_paths = {name: path for name, path in image_paths.items() if is_source(path)}
    expected_source_names = set(lock.sources)
    actual_source_names = set(source_paths)
    if missing_sources := sorted(expected_source_names - actual_source_names):
        raise ImageDerivativeError(f'missing source image "{root / PurePosixPath(missing_sources[0])}"')
    if unexpected_sources := sorted(actual_source_names - expected_source_names):
        raise ImageDerivativeError(f'unexpected source image "{source_paths[unexpected_sources[0]]}"')

    expected_targets: dict[str, tuple[Path, tuple[int, int], str]] = {}
    for source_name in sorted(lock.sources):
        source = source_paths[source_name]
        _require_mode(source)
        source_data = _read(source)
        entry = lock.sources[source_name]
        if _digest(source_data) != entry.source_sha256:
            raise ImageDerivativeError(
                f'source digest differs from the lock for "{source}"; run `mise run build:images`'
            )
        _, source_size = _image_details(source, source_data)
        eligible_widths = _eligible_widths(source, source_size[0])
        expected_names = {_relative_name(root, derivative_name(source, width)): width for width in eligible_widths}
        if missing_entries := sorted(set(expected_names) - set(entry.targets)):
            raise ImageDerivativeError(f'derivative target is absent from the lock: "{root / missing_entries[0]}"')
        if obsolete_entries := sorted(set(entry.targets) - set(expected_names)):
            raise ImageDerivativeError(
                f'obsolete derivative target remains in the lock: "{root / obsolete_entries[0]}"'
            )
        for target_name, width in expected_names.items():
            target = root / PurePosixPath(target_name)
            expected_targets[target_name] = (target, derivative_size(source_size, width), entry.targets[target_name])

    actual_target_names = set(image_paths) - actual_source_names
    expected_target_names = set(expected_targets)
    if missing_targets := sorted(expected_target_names - actual_target_names):
        raise ImageDerivativeError(f'missing derivative target "{root / PurePosixPath(missing_targets[0])}"')
    if unexpected_targets := sorted(actual_target_names - expected_target_names):
        raise ImageDerivativeError(f'unexpected derivative target "{image_paths[unexpected_targets[0]]}"')

    for target_name in sorted(expected_targets):
        target, expected_size, expected_digest = expected_targets[target_name]
        _require_mode(target)
        target_data = _read(target)
        if _digest(target_data) != expected_digest:
            raise ImageDerivativeError(
                f'target digest differs from the lock for "{target}"; run `mise run build:images`'
            )
        target_format, target_size = _image_details(target, target_data)
        if target_format != "WEBP":
            raise ImageDerivativeError(f'derivative target "{target}" must use WebP, got {target_format or "unknown"}')
        if target_size != expected_size:
            raise ImageDerivativeError(
                f'derivative target "{target}" must be {expected_size[0]}x{expected_size[1]}, '
                f"got {target_size[0]}x{target_size[1]}"
            )

    widths = " ".join(str(width) for width in DERIVATIVE_WIDTHS)
    _write_summary(
        output,
        f"image derivatives: {len(source_paths)} sources and {len(expected_targets)} targets verified "
        f"([{widths}] px, q{DERIVATIVE_QUALITY})\n",
    )


def generate_derivatives(
    root: Path,
    *,
    output: TextIO | None = None,
    lock_path: Path | None = None,
    require_lock: bool = False,
) -> None:
    """Generate article derivatives in stable source-path order."""
    if require_lock and lock_path is None:
        raise ImageDerivativeError("a required derivative lock path was not provided")
    old_lock = _load_lock(lock_path, required=require_lock) if lock_path is not None else None
    sources = _discover_sources(root, old_lock, lock_path)
    if not sources:
        raise ImageDerivativeError(f'list article images: no source images under "{root}"')

    if old_lock is None:
        generated = sum(generate_derivative(source) for source in sources)
    else:
        new_lock, generated = _generate_locked(root, sources, old_lock, _current_recipe())
        if lock_path is None:
            raise ImageDerivativeError("derivative lock path became unavailable")
        _write_lock(lock_path, new_lock)
    skipped = len(sources) - generated
    widths = " ".join(str(width) for width in DERIVATIVE_WIDTHS)
    summary = f"image derivatives: {generated} generated, {skipped} skipped ([{widths}] px, q{DERIVATIVE_QUALITY})\n"
    _write_summary(output, summary)


def main(argv: Sequence[str] = ()) -> None:
    """Verify every repository derivative against its current source bytes."""
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="validate the derivative archive without writing")
    options = parser.parse_args(argv)
    try:
        if options.check:
            check_derivatives(ARTICLE_IMAGE_ROOT, lock_path=DERIVATIVE_LOCK_PATH)
        else:
            generate_derivatives(
                ARTICLE_IMAGE_ROOT,
                lock_path=DERIVATIVE_LOCK_PATH,
                require_lock=True,
            )
    except ImageDerivativeError as error:
        action = "check" if options.check else "generate"
        sys.stderr.write(f"{action} image derivatives: {error}\n")
        raise SystemExit(1) from None


if __name__ == "__main__":
    main(sys.argv[1:])
