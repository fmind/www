#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.14"
# dependencies = ["fonttools[woff]==4.65.0"]
# ///
"""Rebuild the self-hosted WOFF2 faces from pinned upstream font releases.

Both families ship under SIL OFL 1.1. Upstream publishes full-coverage variable
TTFs (5 MB for the sans), so the site cannot serve them directly: this script
pins the release tag, clamps the variation axes the design actually uses, and
subsets to the codepoints the site actually renders. Subsetting also drops the
Google logo ligature glyphs that the upstream trademark notice reserves for
Google's own brand use; the output is verified to contain none.

Run it after bumping a release tag, then commit the regenerated WOFF2 files.
"""

from __future__ import annotations

import io
import sys
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path

# fontTools is declared inline above and installed by uv for this script only,
# so it is absent from the project environment the type checker resolves against.
from fontTools import subset  # ty: ignore[unresolved-import]
from fontTools.ttLib import TTFont  # ty: ignore[unresolved-import]
from fontTools.varLib import instancer  # ty: ignore[unresolved-import]

REPOSITORY = Path(__file__).resolve().parent.parent
STATIC_FONTS = REPOSITORY / "static" / "fonts"
DOWNLOAD_CACHE = REPOSITORY / "tmp" / "fonts"

# Google Fonts' "latin" subset: the floor every Latin page needs.
LATIN = (
    "0000-00FF,0131,0152-0153,02BB-02BC,02C6,02DA,02DC,0304,0308,0329,"
    "2000-206F,2074,20AC,2122,2191,2193,2212,2215,FEFF,FFFD"
)
# Beyond that floor, only what articles and site pages actually use: prose
# arrows and marks for the sans, box drawing for CLI transcripts in the mono.
PROSE_MARKS = "0130,2190,2192,2197,25CF,2713"
BOX_DRAWING = "0130,2190,2192,2500-257F,2580-259F,25CF"


@dataclass(frozen=True, slots=True)
class FontBuild:
    """One upstream release reduced to a single served WOFF2 face."""

    family: str
    url: str
    member: str
    axes: dict[str, tuple[float, float] | float]
    features: tuple[str, ...]
    unicodes: str
    output: str

    @property
    def destination(self) -> Path:
        return STATIC_FONTS / self.output


# Google Sans keeps its optical size axis (17 text, 18 display) so headings and
# body text get the drawing they were designed for; weight tops out at 700
# upstream, and GRAD is a Material grade control the site does not expose.
GOOGLE_SANS = FontBuild(
    family="Google Sans",
    url="https://github.com/googlefonts/googlesans/releases/download/v14.000/GoogleSans-v14.000.zip",
    member="build/GoogleSans/variable/GoogleSans[GRAD,opsz,wght].ttf",
    axes={"wght": (400, 700), "GRAD": 0},
    features=("kern", "liga", "calt", "tnum"),
    unicodes=f"{LATIN},{PROSE_MARKS}",
    output="GoogleSans-Variable.woff2",
)
# MONO is pinned to the monospaced end: code blocks are the only consumer.
GOOGLE_SANS_CODE = FontBuild(
    family="Google Sans Code",
    url="https://github.com/googlefonts/googlesans-code/releases/download/v7.001/GoogleSansCode-v7.001.zip",
    member="GoogleSansCode[MONO,wght].ttf",
    axes={"wght": (300, 800), "MONO": 1},
    features=("kern", "calt"),
    unicodes=f"{LATIN},{BOX_DRAWING}",
    output="GoogleSansCode-Variable.woff2",
)
BUILDS = (GOOGLE_SANS, GOOGLE_SANS_CODE)


def parse_unicodes(spec: str) -> set[int]:
    """Expand a comma-separated list of hexadecimal codepoints and ranges."""
    codepoints: set[int] = set()
    for entry in spec.split(","):
        start, _, end = entry.partition("-")
        codepoints.update(range(int(start, 16), int(end or start, 16) + 1))
    return codepoints


def download(url: str) -> bytes:
    """Fetch a pinned release archive, caching it under tmp/ between runs."""
    cached = DOWNLOAD_CACHE / url.rsplit("/", 1)[-1]
    if cached.is_file():
        return cached.read_bytes()
    if not url.startswith("https://github.com/googlefonts/"):
        msg = f"refusing to download a font from an unpinned origin: {url}"
        raise ValueError(msg)
    with urllib.request.urlopen(url) as response:  # noqa: S310 - origin checked above
        payload: bytes = response.read()
    DOWNLOAD_CACHE.mkdir(parents=True, exist_ok=True)
    cached.write_bytes(payload)
    return payload


def build(font_build: FontBuild) -> tuple[int, int]:
    """Instance, subset, and write one face; return its previous and new size."""
    archive = zipfile.ZipFile(io.BytesIO(download(font_build.url)))
    font = TTFont(io.BytesIO(archive.read(font_build.member)))
    instancer.instantiateVariableFont(font, font_build.axes, inplace=True)
    # Round-trip the instance: the subsetter reads variation tables that only
    # become consistent once the clamped font has been serialized again.
    instanced = io.BytesIO()
    font.save(instanced)
    font = TTFont(instanced)

    options = subset.Options()
    options.flavor = "woff2"
    options.layout_features = list(font_build.features)
    # Layout closure would pull in every glyph a feature can produce, including
    # the reserved Google logo ligatures. Keeping the glyph set cmap-driven
    # drops them (and the rules that reach them) at the cost of the optional
    # fi/fl ligature glyphs, which this design never relies on.
    options.layout_closure = False
    subsetter = subset.Subsetter(options=options)
    subsetter.populate(unicodes=parse_unicodes(font_build.unicodes))
    subsetter.subset(font)

    reserved = [name for name in font.getGlyphOrder() if "logo" in name.lower()]
    if reserved:
        msg = f"{font_build.family} subset retained reserved brand glyphs: {reserved}"
        raise RuntimeError(msg)

    destination = font_build.destination
    previous = destination.stat().st_size if destination.is_file() else 0
    destination.parent.mkdir(parents=True, exist_ok=True)
    subset.save_font(font, destination, options)
    return previous, destination.stat().st_size


def main() -> int:
    for font_build in BUILDS:
        previous, current = build(font_build)
        change = f"{previous / 1024:.1f} KB -> " if previous else ""
        sys.stdout.write(f"{font_build.output}: {change}{current / 1024:.1f} KB\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
