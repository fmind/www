"""Public agent discovery and HTTP representation selection."""

from __future__ import annotations

import json
from hashlib import sha256
from importlib.resources import files
from re import fullmatch

from www.data import METADATA

AGENT_SKILL_PATH = "/.well-known/agent-skills/fmind-research/SKILL.md"
AGENT_LINKS = (
    '</.well-known/api-catalog>; rel="api-catalog"; type="application/linkset+json", '
    '</agents>; rel="service-doc"; type="text/html", '
    '</llms.txt>; rel="describedby"; type="text/plain"'
)


def render_api_catalog() -> bytes:
    origin = METADATA.site_url
    return (
        json.dumps(
            {
                "linkset": [
                    {
                        "anchor": origin + "/.well-known/api-catalog",
                        "item": [{"href": origin + "/api/profile"}, {"href": origin + "/mcp"}],
                    },
                    {
                        "anchor": origin + "/api/profile",
                        "describedby": [
                            {"href": origin + "/api/profile/schema.json", "type": "application/schema+json"}
                        ],
                        "service-doc": [{"href": origin + "/agents#http", "type": "text/html"}],
                        "status": [{"href": origin + "/health", "type": "application/json"}],
                    },
                    {
                        "anchor": origin + "/mcp",
                        "service-desc": [
                            {
                                "href": origin + "/.well-known/mcp/server-card.json",
                                "type": "application/mcp-server-card+json",
                            }
                        ],
                        "service-doc": [{"href": origin + "/agents#mcp", "type": "text/html"}],
                        "status": [{"href": origin + "/health", "type": "application/json"}],
                    },
                ]
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n"
    ).encode()


def public_skill() -> tuple[bytes, bytes]:
    """Hash the exact packaged artifact served by the skill endpoint."""
    body = files("www").joinpath("agent_skills/fmind-research/SKILL.md").read_bytes()
    description = next(
        line.removeprefix("description: ") for line in body.decode().splitlines() if line.startswith("description: ")
    )
    index = {
        "$schema": "https://schemas.agentskills.io/discovery/0.2.0/schema.json",
        "skills": [
            {
                "name": "fmind-research",
                "type": "skill-md",
                "description": description,
                "url": METADATA.site_url + AGENT_SKILL_PATH,
                "digest": "sha256:" + sha256(body).hexdigest(),
            }
        ],
    }
    return body, (json.dumps(index, ensure_ascii=False, indent=2) + "\n").encode()


def prefers_markdown(accept: str) -> bool:
    """Choose Markdown only when its effective quality exceeds HTML's.

    Specific ranges override wildcards even at q=0; ties keep the browser
    representation. Unsupported preferences fall back to HTML (RFC 9110).
    """
    qualities: dict[str, tuple[int, float]] = {"text/html": (-1, 0), "text/markdown": (-1, 0)}
    for entry in accept.lower().split(","):
        media, *parameters = (part.strip() for part in entry.split(";"))
        quality = 1.0
        supported = True
        seen_quality = False
        charset_specific = False
        for parameter in parameters:
            key, _, value = parameter.partition("=")
            if key.strip() == "q":
                if seen_quality or fullmatch(r"(?:0(?:\.[0-9]{0,3})?|1(?:\.0{0,3})?)", value.strip()) is None:
                    supported = False
                else:
                    quality = float(value)
                seen_quality = True
            elif key.strip() == "charset" and value.strip() in ("utf-8", '"utf-8"'):
                charset_specific = True
            else:
                supported = False
        if not supported:
            continue
        for representation, previous in qualities.items():
            specificity = 2 if media == representation else 1 if media == "text/*" else 0 if media == "*/*" else -1
            if specificity >= 0:
                specificity = specificity * 2 + int(charset_specific)
            if specificity >= 0 and (specificity, quality) > previous:
                qualities[representation] = (specificity, quality)
    return qualities["text/markdown"][1] > qualities["text/html"][1]
