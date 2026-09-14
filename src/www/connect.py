"""Conference contact details derived from the public portfolio."""

from __future__ import annotations

from base64 import b64encode
from io import BytesIO
from pathlib import Path
from urllib.parse import urlsplit

from PIL import Image

from www.data import BADGES, EXPERTISE, LANGUAGES, LEADERSHIP, METADATA, WORK_CITY, WORK_COUNTRY

CONNECT_URL = f"{METADATA.site_url}/connect"
LINKEDIN_URL = next(social.url for social in METADATA.socials if social.name == "LinkedIn")


def _text(value: str) -> str:
    return (
        value.replace("\\", "\\\\")
        .replace("\r\n", "\n")
        .replace("\r", "\n")
        .replace("\n", "\\n")
        .replace(";", "\\;")
        .replace(",", "\\,")
    )


def _portrait(static_dir: Path) -> str:
    """Embed the public portrait as JPEG without camera or location metadata."""
    path = static_dir / "img/avatar.webp"
    try:
        with Image.open(path) as source:
            portrait = source.convert("RGB")
            portrait.thumbnail((384, 384))
            portrait.info.clear()
            output = BytesIO()
            portrait.save(output, format="JPEG", quality=85)
    except OSError as error:
        msg = f"read public contact portrait {path}: restore the committed avatar image"
        raise RuntimeError(msg) from error
    return b64encode(output.getvalue()).decode("ascii")


def _uri(value: str) -> str:
    """URI values cannot use vCard text escaping; reject field injection."""
    if any(ord(character) <= 32 or ord(character) == 127 for character in value):
        raise ValueError("public contact URL must not contain whitespace or control characters")
    parsed = urlsplit(value)
    if parsed.scheme not in {"https", "http"} or not parsed.netloc or parsed.username or parsed.password:
        raise ValueError("public contact URL must be an absolute HTTP(S) URL without credentials")
    return value


def render_contact_card(static_dir: Path = Path("static")) -> bytes:
    """Serialize a UTF-8 vCard 3.0 with CRLF and octet-bounded folded lines."""
    given, _, family = METADATA.name.rpartition(" ")
    public_links = (
        ("Website", METADATA.site_url),
        *((social.name, social.url) for social in METADATA.socials),
        ("Book a session", METADATA.calendar_url),
        ("Connect", CONNECT_URL),
    )
    # Labels in the standard NOTE field survive importers that show every URL
    # as a generic website. Affiliations do not imply an employment relationship.
    note = "\n\n".join(
        (
            METADATA.description,
            "Languages: " + ", ".join(name for _, name in LANGUAGES),
            "Expertise: " + "; ".join(card.title for card in EXPERTISE),
            "Leadership and community:\n" + "\n".join(f"{role.role} — {role.organization}" for role in LEADERSHIP),
            "Current credentials:\n" + "\n".join(f"{badge.title} — {badge.issuer}" for badge in BADGES if badge.active),
            "Public links:\n" + "\n".join(f"{label}: {url}" for label, url in public_links),
        )
    )
    lines = (
        "BEGIN:VCARD",
        "VERSION:3.0",
        f"UID:{_text(METADATA.site_url)}/#person",
        f"SOURCE:{_uri(METADATA.site_url)}/connect.vcf",
        f"FN:{_text(METADATA.name)}",
        f"N:{_text(family)};{_text(given)};;;",
        f"NICKNAME:{_text(METADATA.alternate_name)}",
        f"TITLE:{_text(METADATA.job_title)}",
        f"EMAIL;TYPE=INTERNET,WORK:{_text(METADATA.email)}",
        f"ADR;TYPE=WORK:;;;{_text(WORK_CITY)};;;{_text(WORK_COUNTRY)}",
        *(f"URL:{_uri(url)}" for _, url in public_links),
        "CATEGORIES:" + ",".join(_text(card.title) for card in EXPERTISE),
        f"NOTE:{_text(note)}",
        f"PHOTO;ENCODING=b;TYPE=JPEG:{_portrait(static_dir)}",
        "END:VCARD",
    )
    folded: list[str] = []
    for line in lines:
        part = ""
        for character in line:
            # Fold between characters so UTF-8 accents remain intact.
            if len((part + character).encode()) > 75:
                folded.append(part)
                part = " "
            part += character
        folded.append(part)
    return ("\r\n".join(folded) + "\r\n").encode()
