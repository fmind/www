"""Conference contact details derived from the public portfolio."""

from __future__ import annotations

from www.data import METADATA

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


def render_contact_card() -> bytes:
    """Serialize a UTF-8 vCard 3.0 with CRLF and octet-bounded folded lines."""
    given, _, family = METADATA.name.rpartition(" ")
    lines = (
        "BEGIN:VCARD",
        "VERSION:3.0",
        f"FN:{_text(METADATA.name)}",
        f"N:{_text(family)};{_text(given)};;;",
        f"NICKNAME:{_text(METADATA.alternate_name)}",
        f"TITLE:{_text(METADATA.job_title)}",
        f"EMAIL;TYPE=INTERNET,WORK:{_text(METADATA.email)}",
        f"URL:{METADATA.site_url}",
        f"URL:{LINKEDIN_URL}",
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
