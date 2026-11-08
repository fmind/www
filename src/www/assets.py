"""Fail-closed loading and hashing for deploy-static site assets."""

import json
import re
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from hashlib import file_digest, sha256
from pathlib import Path
from types import MappingProxyType

from www.highlighting import highlight_css


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

    def __post_init__(self) -> None:
        """Detach the published snapshot from caller-owned mutable mappings."""
        object.__setattr__(self, "root_files", MappingProxyType(dict(self.root_files)))
        object.__setattr__(self, "hashes", MappingProxyType(dict(self.hashes)))

    @property
    def stylesheet_digest(self) -> str:
        """Short content hash that versions the immutable stylesheet URL."""
        return sha256(self.stylesheet.encode()).hexdigest()[:8]

    @property
    def stylesheet_url(self) -> str:
        return f"{STYLESHEET_PATH}?v={self.stylesheet_digest}"


ROOT_FILE_SOURCES = {
    "/favicon.ico": ("favicon.ico", "image/x-icon"),
    "/robots.txt": ("robots.txt", "text/plain; charset=utf-8"),
    "/humans.txt": ("humans.txt", "text/plain; charset=utf-8"),
    "/site.webmanifest": ("site.webmanifest", "application/manifest+json"),
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


def _static_files(static_dir: Path) -> dict[str, Path]:
    return {
        f"/static/{path.relative_to(static_dir).as_posix()}": path
        for path in sorted(static_dir.rglob("*"))
        if path.is_file()
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
    except OSError as error:
        msg = f"hash static assets under {static_dir}: {error}"
        raise RuntimeError(msg) from error
    return entries


def _static_hashes(static_dir: Path, manifest: Path) -> dict[str, str]:
    """Use the build manifest when present, failing closed if the files differ from it."""
    if not manifest.is_file():
        return {route: str(entry["hash"]) for route, entry in hash_static_files(static_dir).items()}
    try:
        entries = json.loads(manifest.read_text(encoding="utf-8"))
        sizes = {route: path.stat().st_size for route, path in _static_files(static_dir).items()}
    except (OSError, ValueError) as error:
        msg = f"read static manifest {manifest}: {error}"
        raise RuntimeError(msg) from error
    valid = isinstance(entries, dict) and all(
        isinstance(entry, dict)
        and isinstance(entry.get("hash"), str)
        and _SHORT_HASH.fullmatch(entry["hash"])
        and entry.get("size") == sizes.get(route)
        for route, entry in entries.items()
    )
    if not valid or entries.keys() != sizes.keys():
        msg = f"static manifest {manifest} does not match {static_dir}; rebuild the image or delete the manifest"
        raise RuntimeError(msg)
    return {route: entry["hash"] for route, entry in entries.items()}


def load_application_assets(static_dir: Path = Path("static")) -> ApplicationAssets:
    """Validate required files and atomically publish immutable template assets."""
    stylesheet_path = static_dir / "dist" / "styles.css"
    try:
        stylesheet = stylesheet_path.read_text(encoding="utf-8")
    except OSError as error:
        msg = f"read generated stylesheet {stylesheet_path}: {error}; run `mise run build:css`"
        raise RuntimeError(msg) from error

    _validate_required_fonts(static_dir)

    hashes = _static_hashes(static_dir, static_dir.parent / STATIC_MANIFEST)

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
