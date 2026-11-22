"""Fail-closed loading, stdlib media dimension parsing, and hashing for deploy-static site assets."""

import json
import os
import re
import sys
from collections.abc import Mapping
from dataclasses import dataclass, field
from hashlib import file_digest, sha256
from pathlib import Path
from types import MappingProxyType
from typing import Any, BinaryIO

from www.highlighting import highlight_css
from www.models import SOURCE_EXTENSIONS


@dataclass(frozen=True, slots=True)
class StaticResponse:
    content_type: str
    body: bytes


# Every page links one content-addressed stylesheet instead of inlining it, so
# browsers download the ~120 KB of CSS once rather than with every no-cache page.
STYLESHEET_PATH = "/styles.css"


@dataclass(frozen=True, slots=True)
class ApplicationAssets:
    root_files: Mapping[str, StaticResponse]
    hashes: Mapping[str, str]
    stylesheet: str
    # Raster and MP4 dimensions by /static/ route, from the build manifest or startup scan.
    image_sizes: Mapping[str, tuple[int, int]] = field(default_factory=dict)
    # Pre-resolved regular file paths for every /static/ route (avoids per-request FS I/O).
    files: Mapping[str, Path] = field(default_factory=dict)
    # Short content hash that versions the immutable stylesheet URL, computed once.
    stylesheet_digest: str = field(init=False)

    def __post_init__(self) -> None:
        """Detach the published snapshot from caller-owned mutable mappings."""
        object.__setattr__(self, "root_files", MappingProxyType(dict(self.root_files)))
        object.__setattr__(self, "hashes", MappingProxyType(dict(self.hashes)))
        object.__setattr__(self, "image_sizes", MappingProxyType(dict(self.image_sizes)))
        object.__setattr__(self, "files", MappingProxyType(dict(self.files)))
        object.__setattr__(self, "stylesheet_digest", sha256(self.stylesheet.encode()).hexdigest()[:8])

    @property
    def stylesheet_url(self) -> str:
        return f"{STYLESHEET_PATH}?v={self.stylesheet_digest}"


ROOT_FILE_SOURCES = {
    "/favicon.ico": ("favicon.ico", "image/x-icon"),
    "/robots.txt": ("robots.txt", "text/plain; charset=utf-8"),
    "/humans.txt": ("humans.txt", "text/plain; charset=utf-8"),
}

_REQUIRED_WOFF2_FILES = (
    "fonts/GoogleSans-Variable.woff2",
    "fonts/GoogleSansCode-Variable.woff2",
)
_WOFF2_HEADER_SIZE = 48


def _validate_required_fonts(static_dir: Path) -> None:
    """Reject missing fonts and obvious WOFF2 corruption before serving traffic."""
    for relative in _REQUIRED_WOFF2_FILES:
        path = static_dir / relative
        try:
            font = path.read_bytes()
        except OSError as error:
            msg = f"read required WOFF2 font {path}: {error}"
            raise RuntimeError(msg) from error

        # WOFF2 has a fixed 48-byte big-endian header. Checking its signature,
        # declared length, table count, and sizes catches truncation or a wrong
        # file without pulling a font parser into the application runtime.
        valid_header = (
            len(font) >= _WOFF2_HEADER_SIZE
            and font[:4] == b"wOF2"
            and int.from_bytes(font[8:12], "big") == len(font)
            and int.from_bytes(font[12:14], "big") > 0
            and font[14:16] == b"\x00\x00"
            and int.from_bytes(font[16:20], "big") > 0
            and int.from_bytes(font[20:24], "big") > 0
        )
        if not valid_header:
            msg = f"invalid WOFF2 font {path}: malformed fixed header"
            raise RuntimeError(msg)


# The image build writes this manifest beside static/. Cloud Run fetches image file
# contents lazily, so hashing all ~50 MB of media at startup took 5.5s of a cold start;
# the manifest reduces startup to listing file metadata.
STATIC_MANIFEST = "static-hashes.json"
_SHORT_HASH = re.compile(r"[0-9a-f]{8}")
_RASTER_SUFFIXES = frozenset(SOURCE_EXTENSIONS)
_JPEG_SOF_MARKERS = frozenset(
    {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF},
)


def _webp_chunk_dimensions(chunk: bytes, prefix: bytes, size: int) -> tuple[int, int] | None:
    if chunk == b"VP8X" and size == 10 and len(prefix) == 10:
        width = int.from_bytes(prefix[4:7], "little") + 1
        height = int.from_bytes(prefix[7:10], "little") + 1
        return (width, height) if width * height <= (1 << 32) - 1 else None
    if chunk == b"VP8 " and size >= 10 and len(prefix) == 10:
        if prefix[0] & 1 or prefix[3:6] != b"\x9d\x01\x2a":
            return None
        width = int.from_bytes(prefix[6:8], "little") & 0x3FFF
        height = int.from_bytes(prefix[8:10], "little") & 0x3FFF
        return (width, height) if width and height else None
    if chunk == b"VP8L" and size >= 5 and len(prefix) >= 5 and prefix[0] == 0x2F:
        packed = int.from_bytes(prefix[1:5], "little")
        if packed >> 29:
            return None
        return (packed & 0x3FFF) + 1, ((packed >> 14) & 0x3FFF) + 1
    return None


def _webp_size(image: BinaryIO) -> tuple[int, int] | None:
    """Read bounded WebP metadata while validating the complete RIFF shape."""
    image.seek(0)
    header = image.read(12)
    if len(header) != 12 or header[:4] != b"RIFF" or header[8:] != b"WEBP":
        return None
    file_size = os.fstat(image.fileno()).st_size
    if int.from_bytes(header[4:8], "little") + 8 != file_size:
        return None

    offset = 12
    dimensions: tuple[int, int] | None = None
    while offset < file_size:
        chunk_header = image.read(8)
        if len(chunk_header) != 8:
            return None
        chunk_size = int.from_bytes(chunk_header[4:8], "little")
        data_end = offset + 8 + chunk_size
        next_offset = data_end + (chunk_size & 1)
        if data_end > file_size or next_offset > file_size:
            return None
        if dimensions is None:
            prefix = image.read(min(chunk_size, 10))
            dimensions = _webp_chunk_dimensions(chunk_header[:4], prefix, chunk_size)
            if dimensions is None:
                return None
        if chunk_size & 1:
            image.seek(data_end)
            if image.read(1) != b"\0":
                return None
        image.seek(next_offset)
        offset = next_offset
    return dimensions


def _png_size(header: bytes) -> tuple[int, int] | None:
    if len(header) >= 24 and header[:8] == b"\x89PNG\r\n\x1a\n" and header[12:16] == b"IHDR":
        width = int.from_bytes(header[16:20], "big")
        height = int.from_bytes(header[20:24], "big")
        return (width, height) if width > 0 and height > 0 else None
    return None


def _gif_size(header: bytes) -> tuple[int, int] | None:
    if len(header) >= 10 and header[:6] in (b"GIF87a", b"GIF89a"):
        width = int.from_bytes(header[6:8], "little")
        height = int.from_bytes(header[8:10], "little")
        return (width, height) if width > 0 and height > 0 else None
    return None


def _jpeg_size(image: BinaryIO) -> tuple[int, int] | None:
    image.seek(0)
    if image.read(2) != b"\xff\xd8":
        return None
    while True:
        byte = image.read(1)
        while byte and byte != b"\xff":
            byte = image.read(1)
        while byte == b"\xff":
            byte = image.read(1)
        if not byte:
            return None
        marker = byte[0]
        if marker in (0xD8, 0xD9, 0x01) or 0xD0 <= marker <= 0xD7:
            if marker == 0xD9:
                return None
            continue
        length_bytes = image.read(2)
        if len(length_bytes) != 2:
            return None
        length = int.from_bytes(length_bytes, "big")
        if length < 2:
            return None
        if marker in _JPEG_SOF_MARKERS:
            segment = image.read(5)
            if len(segment) != 5:
                return None
            height = int.from_bytes(segment[1:3], "big")
            width = int.from_bytes(segment[3:5], "big")
            return (width, height) if width > 0 and height > 0 else None
        if marker == 0xDA:
            return None
        image.seek(length - 2, os.SEEK_CUR)


def image_dimensions(path: Path) -> tuple[int, int]:
    """Return raster dimensions using pure stdlib header parsers (no Pillow dependency)."""
    with path.open("rb") as image:
        header = image.read(24)
        dimensions = (
            _png_size(header)
            or _gif_size(header)
            or (_webp_size(image) if header[:4] == b"RIFF" else None)
            or (_jpeg_size(image) if header[:2] == b"\xff\xd8" else None)
        )
    if dimensions is None:
        msg = f"cannot identify image file {path}"
        raise ValueError(msg)
    return dimensions


def _iter_mp4_boxes(stream: BinaryIO, start: int, end: int) -> list[tuple[bytes, int, int]]:
    boxes: list[tuple[bytes, int, int]] = []
    offset = start
    while offset + 8 <= end:
        stream.seek(offset)
        header = stream.read(8)
        if len(header) != 8:
            break
        size = int.from_bytes(header[:4], "big")
        box_type = header[4:8]
        header_size = 8
        if size == 1:
            extended = stream.read(8)
            if len(extended) != 8:
                break
            size = int.from_bytes(extended, "big")
            header_size = 16
        elif size == 0:
            size = end - offset
        if size < header_size or offset + size > end:
            break
        boxes.append((box_type, offset + header_size, offset + size))
        offset += size
    return boxes


def video_dimensions(path: Path) -> tuple[int, int] | None:
    """Read display width and height from an MP4 `moov/trak/tkhd` box without external tools."""
    with path.open("rb") as stream:
        file_size = os.fstat(stream.fileno()).st_size
        for box_type, moov_start, moov_end in _iter_mp4_boxes(stream, 0, file_size):
            if box_type != b"moov":
                continue
            for child_type, trak_start, trak_end in _iter_mp4_boxes(stream, moov_start, moov_end):
                if child_type != b"trak":
                    continue
                for leaf_type, tkhd_start, tkhd_end in _iter_mp4_boxes(stream, trak_start, trak_end):
                    if leaf_type != b"tkhd" or tkhd_end - tkhd_start < 84:
                        continue
                    stream.seek(tkhd_start)
                    version = stream.read(1)
                    if not version:
                        continue
                    width_offset = 76 if version[0] == 0 else 88
                    if tkhd_end - tkhd_start < width_offset + 8:
                        continue
                    stream.seek(tkhd_start + width_offset)
                    raw = stream.read(8)
                    width = int.from_bytes(raw[:4], "big") >> 16
                    height = int.from_bytes(raw[4:8], "big") >> 16
                    if width > 0 and height > 0:
                        return width, height
    return None


def _static_files(static_dir: Path) -> dict[str, Path]:
    root = static_dir.resolve()
    return {
        f"/static/{path.relative_to(static_dir).as_posix()}": resolved
        for path in sorted(static_dir.rglob("*"))
        if path.is_file() and (resolved := path.resolve()).is_relative_to(root)
    }


def hash_static_files(static_dir: Path) -> dict[str, dict[str, int | str]]:
    """Hash every static file, recording its size so a manifest can be checked by metadata."""
    entries: dict[str, dict[str, int | str]] = {}
    try:
        for route, path in _static_files(static_dir).items():
            # Stream large article media so hashing does not allocate its entire
            # compressed payload inside the memory-constrained startup process.
            with path.open("rb") as source:
                digest = file_digest(source, "sha256").hexdigest()[:8]
            entries[route] = {"hash": digest, "size": path.stat().st_size}
            suffix = path.suffix.lower()
            if suffix in _RASTER_SUFFIXES:
                try:
                    entries[route]["width"], entries[route]["height"] = image_dimensions(path)
                except ValueError as error:
                    msg = f"read image dimensions of {path}: {error}"
                    raise RuntimeError(msg) from error
            elif suffix == ".mp4" and (dimensions := video_dimensions(path)):
                entries[route]["width"], entries[route]["height"] = dimensions
    except OSError as error:
        msg = f"hash static assets under {static_dir}: {error}"
        raise RuntimeError(msg) from error
    return entries


def _positive(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _static_inventory(
    static_dir: Path, manifest: Path
) -> tuple[dict[str, str], dict[str, tuple[int, int]], dict[str, Path]]:
    """Use the build manifest when present, failing closed if the files differ from it."""
    files = _static_files(static_dir)
    if not manifest.is_file():
        hashes, dimensions = _split_inventory(hash_static_files(static_dir))
        return hashes, dimensions, files
    try:
        entries = json.loads(manifest.read_text(encoding="utf-8"))
        sizes = {route: path.stat().st_size for route, path in files.items()}
    except (OSError, ValueError) as error:
        msg = f"read static manifest {manifest}: {error}"
        raise RuntimeError(msg) from error
    valid = isinstance(entries, dict) and all(
        isinstance(entry, dict)
        and isinstance(entry.get("hash"), str)
        and _SHORT_HASH.fullmatch(entry["hash"])
        and entry.get("size") == sizes.get(route)
        and (
            ("width" not in entry and "height" not in entry)
            or (_positive(entry.get("width")) and _positive(entry.get("height")))
        )
        for route, entry in entries.items()
    )
    if not valid or entries.keys() != sizes.keys():
        msg = f"static manifest {manifest} does not match {static_dir}; rebuild the image or delete the manifest"
        raise RuntimeError(msg)
    hashes, dimensions = _split_inventory(entries)
    return hashes, dimensions, files


def _split_inventory(entries: Mapping[str, Mapping[str, Any]]) -> tuple[dict[str, str], dict[str, tuple[int, int]]]:
    hashes = {route: entry["hash"] for route, entry in entries.items()}
    dimensions = {route: (entry["width"], entry["height"]) for route, entry in entries.items() if "width" in entry}
    return hashes, dimensions


def load_application_assets(static_dir: Path = Path("static")) -> ApplicationAssets:
    """Validate required files and atomically publish immutable template assets."""
    stylesheet_path = static_dir / "dist" / "styles.css"
    try:
        stylesheet = stylesheet_path.read_text(encoding="utf-8")
    except OSError as error:
        msg = f"read generated stylesheet {stylesheet_path}: {error}; run `mise run build:css`"
        raise RuntimeError(msg) from error

    _validate_required_fonts(static_dir)

    hashes, image_sizes, files = _static_inventory(static_dir, static_dir.parent / STATIC_MANIFEST)

    root_files: dict[str, StaticResponse] = {}
    for route, (relative, content_type) in ROOT_FILE_SOURCES.items():
        source = static_dir / relative
        try:
            root_files[route] = StaticResponse(content_type, source.read_bytes())
        except OSError as error:
            msg = f"read root file {source}: {error}"
            raise RuntimeError(msg) from error

    return ApplicationAssets(
        root_files=root_files,
        hashes=hashes,
        stylesheet=_version_font_urls(stylesheet, hashes) + highlight_css(),
        image_sizes=image_sizes,
        files=files,
    )


def _version_font_urls(stylesheet: str, hashes: Mapping[str, str]) -> str:
    """Point each @font-face at its content-addressed URL, the one templates preload, so fonts cache immutably."""
    for relative in _REQUIRED_WOFF2_FILES:
        path = f"/static/{relative}"
        # Tailwind keeps the authored quotes; accept either style so a minifier change cannot skip the rewrite.
        sources = [f"url({quote}{path}{quote})" for quote in ("'", '"', "")]
        if not any(source in stylesheet for source in sources):
            msg = f"generated stylesheet has no @font-face for {path}; keep assets/css/input.css and fonts in sync"
            raise RuntimeError(msg)
        for source in sources:
            stylesheet = stylesheet.replace(source, f'url("{path}?v={hashes[path]}")')
    return stylesheet


if __name__ == "__main__":
    # Image build step: python -m www.assets <static-dir> <manifest-path>
    source, target = (Path(argument) for argument in sys.argv[1:3])
    target.write_text(json.dumps(hash_static_files(source), sort_keys=True) + "\n", encoding="utf-8")
