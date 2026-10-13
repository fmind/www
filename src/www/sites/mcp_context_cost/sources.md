# MCP context-cost snapshot

Verified 2026-10-13. This calculator estimates repeated tool-definition/scaffold overhead, not total task cost or model quality. Runtime formulas never fetch sources or start MCP servers. Existing hosting modules remain separate.

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

## Model assumptions

Standard text API prices in USD per million tokens, verified against the [provider pricing page](https://developers.openai.com/api/docs/pricing) and model pages on 2026-10-13:

| Preset                                                                     | Context window | Input | Cache read | Cache write/input multiplier |
| -------------------------------------------------------------------------- | -------------: | ----: | ---------: | ---------------------------: |
| [GPT-5.4 Mini](https://developers.openai.com/api/docs/models/gpt-5.4-mini) |        400,000 |  0.75 |      0.075 |                            1 |
| [GPT-4.1](https://developers.openai.com/api/docs/models/gpt-4.1)           |      1,047,576 |  2.00 |       0.50 |                            1 |

These presets are reference price examples, not model recommendations. Corresponding model snapshots are `gpt-5.4-mini-2026-03-17` and `gpt-4.1-2025-04-14`. Prices exclude output, tool fees, discounts, regional uplifts and taxes. All assumptions are editable. The `model` parameter fills missing provider values; explicit values override it. Model preset links preserve the last calculated workload and tool counts while replacing context, input/cache price, write multiplier and minimum prefix. Submit unsaved edits before following a preset link.

The current [prompt caching guide](https://developers.openai.com/api/docs/guides/prompt-caching) makes minimum prefix eligibility request-dependent for these older models and applies no additional cache-write fee. The **1,024-token minimum is an editable planning assumption**, not a fixed verified limit for these presets. Cached-token reporting rounds down to multiples of 128; this calculator models marginal tool-block cost without provider alignment/rounding. Matching prefixes, retention and routing still constrain actual hits. Other stable prefix tokens can qualify a small tool block; their cost and occupied context are outside this calculator. A custom write multiplier models other providers' cache-write premiums but does not implement their complete billing policy or storage charges.

## Formulas and precedence

All calculations live in `calculator.py`. The native GET form and read-only `compare_mcp_context_cost` MCP tool use the same parser and formulas. Unknown query keys (including UTM tracking parameters) are silently ignored on the page and omitted from its effective scenario URL; MCP rejects unknown keys. Repeated, blank, whitespace-padded, non-finite, nonnumeric and out-of-range calculator values produce visible page messages with independent default fallbacks; MCP rejects the whole invalid scenario. Whole counts use integer syntax. Serialization preserves effective values; no client formula implementation exists.

Let each server catalog contain `N_i` tools and `T_i` measured tokens, with `n_i` enabled tools. A zero enabled count excludes that server entirely, including the all-tools baseline. All-tools `B = sum(T_i where n_i > 0)`. Filtering `F = ceil(sum(T_i * n_i / N_i))`. A partial count assumes equally sized tools and is only an estimate; measure an actual allowlist before relying on it. Dynamic discovery `D = ceil(discovery_tokens + F * loaded_percent / 100)`. CLI `L = skill_tokens + help_tokens`. Discovery and CLI values are caller-supplied average exposure per model request, including definitions/help retained in history. They are not the benchmark's measured full-task reductions. A strategy can cost more than the baseline.

For each strategy's `T` tokens/request, context share is `100 * T / context_window`. Let `R` be requests/session, `S` sessions/workday, `W` workdays/month, `P` input price, `C` cache-read price, `M` write multiplier and `h` follow-up hit percentage. No-cache session cost is `T * R * P / 1e6`. Let `K` be stable tokens: `discovery_tokens` for search, otherwise `T`. Eligible hits are `H = (R - 1) * h / 100`; cached session cost is `(K * ((R - H) * P * M + H * C) + (T - K) * R * P) / 1e6`. Search applies hits and write premiums only to its stable scaffold; changing loaded definitions pay standard input price on every request. This is a conservative modeling choice: loaded schemas need not repeat unchanged. Other strategies assume their entire block is stable, including loaded CLI help. Each session starts cold, and every eligible stable-prefix miss pays the chosen write rate. Eligibility requires `K > 0` and `K + other_prefix >= cache_minimum`; otherwise use standard no-cache cost, without write premiums. Loaded search definitions cannot satisfy the minimum prefix. Costs/day multiply by `S`; costs/month by `S * W`. Compare savings against `B` with the same cache policy. Negative savings mean a cost increase; cache-write premiums may cost more than uncached input.

Caching changes cost, never context occupancy. Uniform average tool exposure is assumed across a session. A fitting tool block does not prove the whole request fits; instructions, history, results, reasoning and output need additional context. Cache eligibility is conditional, not an assertion about provider acceptance. Extra search calls, search fees, command output, cache storage, operations and task quality are excluded. Costs are not an invoice or a measured production result.

## Mitigation sources

- [Current MCP tools specification](https://modelcontextprotocol.io/specification/2026-07-28/server/tools): schemas and discovery do not by themselves determine a host's model context.
- [GitHub tool selection](https://github.com/github/github-mcp-server#specifying-individual-tools): restrict individual tools/toolsets; combined selections are additive.
- [Claude Code MCP tool search](https://code.claude.com/docs/en/mcp#scale-with-mcp-tool-search) and [provider tool search](https://platform.claude.com/docs/en/agents-and-tools/tool-use/tool-search-tool): defer definitions; account for search scaffolding, loaded schemas and extra requests.
- [Prompt caching](https://developers.openai.com/api/docs/guides/prompt-caching): stable prefix reuse, eligibility and actual usage counters.
- [Agent Skills progressive disclosure](https://agentskills.io/specification#progressive-disclosure): metadata and loaded instructions have separate context costs; CLI usage still needs help and command output.

All links above were fetched on the snapshot date. No automatic refresh, inference, paid provider calls or runtime MCP process is required to serve this page.
