"""Immutable measured MCP tool catalogs; provenance in sources.md."""

from dataclasses import dataclass

# Date the pinned catalogs and every source link were last re-verified (see sources.md).
SNAPSHOT_DATE = "2026-11-09"
BENCHMARK_COMMIT = "8251908e2e32977467515d40fbd1d47c9668d25d"
BENCHMARK_TREE_URL = f"https://github.com/fmind/mcp-context-benchmark/tree/{BENCHMARK_COMMIT}"
BENCHMARK_URL = f"https://github.com/fmind/mcp-context-benchmark/blob/{BENCHMARK_COMMIT}/results/catalogue.json"


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
        "v2.0.2",
        46,
        11157,
        "2026-10-10",
        "https://github.com/github/github-mcp-server/tree/v2.0.2",
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
        "2026-10-13",
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
        "2026-10-13",
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
        "2026-10-13",
        "https://github.com/microsoft/playwright-mcp",
        "https://registry.npmjs.org/@playwright/mcp/0.0.83",
        "Package release",
        "Default tools/list; no browser launched. Package embeds Playwright 1.64.0-alpha-1790635538000.",
    ),
)
