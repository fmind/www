# MCP context-cost snapshot

Verified 2026-10-13. This calculator counts the tool definitions that measured MCP servers add to every model request and prices them as standard input. It does not estimate total task cost, mitigation savings or model quality. Runtime formulas never fetch sources or start MCP servers.

## Tool catalogs

| Server     | Captured configuration                                                   | Tools | Reference tokens | Measured   |
| ---------- | ------------------------------------------------------------------------ | ----: | ---------------: | ---------- |
| GitHub     | v1.12.2, default toolset                                                 |    45 |           10,989 | 2026-09-20 |
| Filesystem | `@modelcontextprotocol/server-filesystem@1.0.0`, empty allowed directory |    14 |            1,681 | 2026-10-13 |
| Memory     | `@modelcontextprotocol/server-memory@1.0.0`, scratch memory path         |     9 |              953 | 2026-10-13 |
| Playwright | `@playwright/mcp@0.0.83`, default tools, headless/isolated flags         |    25 |            3,745 | 2026-10-13 |

GitHub comes exclusively from pushed benchmark commit [`e83ad9431e41ffd745384a04c49b95d8e1090691`](https://github.com/fmind/mcp-context-benchmark/tree/e83ad9431e41ffd745384a04c49b95d8e1090691): [results](https://github.com/fmind/mcp-context-benchmark/blob/e83ad9431e41ffd745384a04c49b95d8e1090691/results.json), [analyzer](https://github.com/fmind/mcp-context-benchmark/blob/e83ad9431e41ffd745384a04c49b95d8e1090691/analyze.py), and [methods](https://github.com/fmind/mcp-context-benchmark/blob/e83ad9431e41ffd745384a04c49b95d8e1090691/METHODS.md). Public raw files were compared with the local committed ref, without reading uncommitted benchmark work. The default catalog is deliberately separate from its 90-tool all catalog. Its exact read-only/focused aggregates are not interchangeable with our proportional count estimates.

The other measurements use official [Filesystem](https://github.com/modelcontextprotocol/servers/tree/main/src/filesystem), [Memory](https://github.com/modelcontextprotocol/servers/tree/main/src/memory) and [Playwright](https://github.com/microsoft/playwright-mcp) packages. `measurements.json` retains timestamps, package versions/tarball integrity, tool names, individual counts, server information, protocol and SHA-256 hashes. [`scripts/mcp_context_cost/measurement-package-lock.json`](../../../../scripts/mcp_context_cost/measurement-package-lock.json) pins transitive capture dependencies outside the runtime package. Only its root display name was normalized to `www-mcp-context-cost-measurements`; dependency entries are unchanged and `package_lock_sha256` in `measurements.json` hashes the retained file. The three npm links on the page are labeled "Package release": they identify packages, not published measurement evidence. Playwright MCP embeds `playwright@1.64.0-alpha-1790635538000` in this capture. Do not silently replace it with today's package when comparing counts.

All rows use **tiktoken 0.14.0, `o200k_base`**, with the benchmark's exact normalization:

```python
declarations = [
    {"name": tool["name"], "description": tool.get("description", ""), "parameters": tool["inputSchema"]}
    for tool in tools
]
normalized = json.dumps(declarations, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
tokens = len(tiktoken.get_encoding("o200k_base").encode(normalized))
declarations_sha256 = hashlib.sha256(normalized.encode()).hexdigest()
```

Tool order is the order returned by the server. The raw schema hash uses the same compact serialization over the complete tools array. Arrays are counted per server, then their counts are summed; a single merged array may tokenize differently. Individual tool counts do not sum exactly to the array count. Full output schemas, annotations, protocol envelopes and provider wrappers are excluded. Tokens are a consistent reference unit, not each provider's tokenizer or billing counter.

For a fresh capture, copy the measurement lock to an OS temporary directory as `package-lock.json`, create `package.json` using its root `packages[""].dependencies`, and run `npm ci --ignore-scripts --no-audit --no-fund` there. In an isolated Python environment with `mcp==2.3.0` and `tiktoken==0.14.0`, use `mcp.Client(StdioServerParameters(...), mode="legacy")` sequentially. Launch `node` with `node_modules/@modelcontextprotocol/server-filesystem/dist/index.js <empty-directory>`, `node_modules/@modelcontextprotocol/server-memory/dist/index.js`, or `node_modules/@playwright/mcp/cli.js --headless --isolated`; set `MEMORY_FILE_PATH` to a scratch file and `PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1`. Call paginated `list_tools(cache_mode="refresh")` until `next_cursor` is empty and serialize each tool with `model_dump(mode="json", by_alias=True, exclude_none=True)`. Apply the normalization above and compare both hashes and counts. The retained captures negotiated protocol `2025-11-25`; no tool calls or browsers ran. Use at most one server process at a time. A new capture date/version needs a new reviewed snapshot.

## Prices

Input prices, input limits and review dates come from the managed API snapshot shared with the LLM hosting comparison (`src/www/sites/data.py:API_BASELINES`, provenance in [`../sources.md`](../sources.md)), so both pages quote the same dated rates. The calculator applies that snapshot's announced date-based changes and flags prices whose review date has passed. Tool definitions are a short prompt prefix, so standard short-prompt rates apply; long-prompt tiers depend on the rest of the request and are excluded.

## Formulas and precedence

All calculations live in `calculator.py`; the native GET form and the read-only `compare_mcp_context_cost` MCP tool share them.

- Tokens per request `T = sum(T_i)` over the selected servers' measured catalogs.
- Tokens per month `= T * requests_per_day * 30`.
- For each model, context share `= 100 * T / input_token_limit`, cost per 1,000 requests `= T * 1000 * input_price / 1e6`, and monthly cost `= T * requests_per_day * 30 * input_price / 1e6`. Models are ordered by input price.

The page reads repeated `server` keys and one whole `requests` value from 1 to 10,000,000. A query without any calculator key selects every server at 1,000 requests per day; unrelated keys such as UTM tags are ignored. A submitted form with no server, an unknown server, or an invalid request count shows a visible message and falls back to all servers or 1,000 requests. The MCP tool takes typed `servers` (distinct known ids; omit for all) and `requests_per_day` arguments and fails on invalid values instead of falling back.

Excluded: prompt-caching discounts, instructions, history, tool results, output and reasoning, client wrappers, output schemas and extra tool-search calls. Caching would lower the price of repeated definitions, never the context they occupy. Results are planning estimates, not an invoice or a measured production result.

## Mitigation sources

- [Current MCP tools specification](https://modelcontextprotocol.io/specification/2026-07-28/server/tools): schemas and discovery do not by themselves determine a host's model context.
- [GitHub tool selection](https://github.com/github/github-mcp-server#tool-configuration): restrict individual tools/toolsets; combined selections are additive.
- [Claude Code MCP tool search](https://code.claude.com/docs/en/mcp#scale-with-mcp-tool-search) and [provider tool search](https://platform.claude.com/docs/en/agents-and-tools/tool-use/tool-search-tool): defer definitions; account for search scaffolding, loaded schemas and extra requests.
- [Prompt caching](https://developers.openai.com/api/docs/guides/prompt-caching): stable prefix reuse lowers price, not context occupancy.
- [Agent Skills progressive disclosure](https://agentskills.io/specification#progressive-disclosure): metadata and loaded instructions have separate context costs.

All links above were fetched on the snapshot date. No automatic refresh, inference, paid provider calls or runtime MCP process is required to serve this page.
