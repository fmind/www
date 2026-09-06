"""Fail-closed loading and hashing for deploy-static site assets."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from hashlib import file_digest
from pathlib import Path
from types import MappingProxyType

from www.highlighting import highlight_css


@dataclass(frozen=True, slots=True)
class StaticResponse:
    content_type: str
    body: bytes


@dataclass(frozen=True, slots=True)
class ApplicationAssets:
    root_files: Mapping[str, StaticResponse]
    hashes: Mapping[str, str]
    inline_styles: str

    def __post_init__(self) -> None:
        """Detach the published snapshot from caller-owned mutable mappings."""
        object.__setattr__(self, "root_files", MappingProxyType(dict(self.root_files)))
        object.__setattr__(self, "hashes", MappingProxyType(dict(self.hashes)))


ROOT_FILE_SOURCES = {
    "/favicon.ico": ("favicon.ico", "image/x-icon"),
    "/robots.txt": ("robots.txt", "text/plain; charset=utf-8"),
    "/humans.txt": ("humans.txt", "text/plain; charset=utf-8"),
    "/site.webmanifest": ("site.webmanifest", "application/manifest+json"),
}

_REQUIRED_WOFF2_FILES = (
    "fonts/Inter-Variable.woff2",
    "fonts/Outfit-Variable.woff2",
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


def load_application_assets(static_dir: Path = Path("static")) -> ApplicationAssets:
    """Validate required files and atomically publish immutable template assets."""
    stylesheet_path = static_dir / "dist" / "styles.css"
    try:
        stylesheet = stylesheet_path.read_text(encoding="utf-8")
    except OSError as error:
        msg = f"read generated stylesheet {stylesheet_path}: {error}"
        raise RuntimeError(msg) from error

    _validate_required_fonts(static_dir)

    hashes: dict[str, str] = {}
    try:
        files = sorted(path for path in static_dir.rglob("*") if path.is_file())
        for path in files:
            relative = path.relative_to(static_dir).as_posix()
            # Stream large article media so hashing does not allocate its entire
            # compressed payload inside the memory-constrained startup process.
            with path.open("rb") as source:
                hashes[f"/static/{relative}"] = file_digest(source, "sha256").hexdigest()[:8]
    except OSError as error:
        msg = f"hash static assets under {static_dir}: {error}"
        raise RuntimeError(msg) from error

    root_files: dict[str, StaticResponse] = {}
    for route, (relative, content_type) in ROOT_FILE_SOURCES.items():
        source = static_dir / relative
        try:
            root_files[route] = StaticResponse(content_type, source.read_bytes())
        except OSError as error:
            msg = f"read root file {source}: {error}"
            raise RuntimeError(msg) from error

    inline_styles = stylesheet + highlight_css()
    return ApplicationAssets(
        root_files=root_files,
        hashes=hashes,
        inline_styles=inline_styles,
    )
