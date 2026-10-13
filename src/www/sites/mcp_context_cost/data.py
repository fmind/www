"""Immutable reference counts and provider assumptions; provenance in sources.md."""

from dataclasses import dataclass

SNAPSHOT_DATE = "2026-10-13"
BENCHMARK_COMMIT = "e83ad9431e41ffd745384a04c49b95d8e1090691"
BENCHMARK_URL = f"https://github.com/fmind/mcp-context-benchmark/blob/{BENCHMARK_COMMIT}/results.json"


@dataclass(frozen=True, slots=True)
class ServerSnapshot:
    id: str
    name: str
    version: str
    tools: int
    tokens: int
    measured_on: str
    source_url: str
    evidence_url: str
    evidence_label: str
    note: str


SERVERS = (
    ServerSnapshot(
        "github",
        "GitHub (default toolset)",
        "v1.12.2",
        45,
        10989,
        "2026-09-20",
        "https://github.com/github/github-mcp-server/tree/v1.12.2",
        BENCHMARK_URL,
        "Pinned measurement source",
        "Default catalog from the pinned public benchmark; not every available GitHub tool.",
    ),
    ServerSnapshot(
        "filesystem",
        "Filesystem",
        "1.0.0",
        14,
        1681,
        SNAPSHOT_DATE,
        "https://github.com/modelcontextprotocol/servers/tree/main/src/filesystem",
        "https://registry.npmjs.org/@modelcontextprotocol/server-filesystem/1.0.0",
        "Package release",
        "Official reference server; tools/list only, with an empty allowed directory.",
    ),
    ServerSnapshot(
        "memory",
        "Memory",
        "1.0.0",
        9,
        953,
        SNAPSHOT_DATE,
        "https://github.com/modelcontextprotocol/servers/tree/main/src/memory",
        "https://registry.npmjs.org/@modelcontextprotocol/server-memory/1.0.0",
        "Package release",
        "Official reference server; tools/list only, with a scratch memory path.",
    ),
    ServerSnapshot(
        "playwright",
        "Playwright",
        "0.0.83",
        25,
        3745,
        SNAPSHOT_DATE,
        "https://github.com/microsoft/playwright-mcp",
        "https://registry.npmjs.org/@playwright/mcp/0.0.83",
        "Package release",
        "Default tools/list; no browser launched. Package embeds Playwright 1.64.0-alpha-1790635538000.",
    ),
)


@dataclass(frozen=True, slots=True)
class ModelSnapshot:
    id: str
    name: str
    context_tokens: int
    input_price: float
    cache_price: float
    write_multiplier: float
    cache_minimum: int
    verified_on: str
    price_url: str
    model_url: str
    cache_url: str
    note: str


MODELS = (
    ModelSnapshot(
        "gpt-5.4-mini",
        "GPT-5.4 Mini",
        400000,
        0.75,
        0.075,
        1,
        1024,
        SNAPSHOT_DATE,
        "https://developers.openai.com/api/docs/pricing",
        "https://developers.openai.com/api/docs/models/gpt-5.4-mini",
        "https://developers.openai.com/api/docs/guides/prompt-caching",
        "Standard text rates. The 1,024-token cache minimum is a planning assumption: actual eligibility is request-dependent for this model.",
    ),
    ModelSnapshot(
        "gpt-4.1",
        "GPT-4.1",
        1047576,
        2,
        0.5,
        1,
        1024,
        SNAPSHOT_DATE,
        "https://developers.openai.com/api/docs/pricing",
        "https://developers.openai.com/api/docs/models/gpt-4.1",
        "https://developers.openai.com/api/docs/guides/prompt-caching",
        "Standard text rates. The 1,024-token cache minimum is a planning assumption: actual eligibility is request-dependent for this model.",
    ),
)
