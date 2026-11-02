+++
title = "LiteLLM is the known option. agentgateway is the open one."
description = "Comparing LiteLLM and agentgateway for enterprise AI platforms: licensing boundaries, security advisories, ops footprints, and open governance."
date = "2026-08-16"
tags = ["Agent", "LLM", "Guide"]
slug = "agentgateway-vs-litellm"
draft = false
+++

An AI gateway is now a critical piece of an agent platform. It is how a company abstracts which model sits behind a call, and how it exposes AI assets such as [MCP](https://modelcontextprotocol.io) servers and [Agent-to-Agent endpoints](https://a2a-protocol.org/latest/) under one identity, policy, and audit surface.

Some teams will extend the gateway they already run: Apigee, Kong, Gravitee, or the mesh they standardized on. Others will look for an open source product built for this traffic. In that second conversation, the first name on the whiteboard is almost always [LiteLLM](https://github.com/BerriAI/litellm). It is the product everyone already knows: one OpenAI-compatible API, a huge provider catalog, virtual keys, and a UI that lets developers vend credentials before lunch.

A customer evaluation this year started there. The review compared LiteLLM with [agentgateway](https://agentgateway.dev/) on the trees, the licenses, the published advisories, and the docs. Two findings decided the recommendation. Most of the controls a platform team needs next sit behind `LITELLM_LICENSE`. And across that organization, the critical security issues that kept coming back were tied to LiteLLM already in use. LiteLLM is the most well known option. It is not the one with the fewest strings attached, and it is not the one the public record treats as the quieter default.

Disclosure, because it changes how the rest should be read. I am an AAIF Ambassador. agentgateway has been an [AAIF-hosted project since 4 June 2026](https://aaif.io/blog/agentgateway-joins-aaif-as-an-open-gateway-for-agentic-ai-infrastructure). This piece reports that evaluation. It is not an independent load test. The dates below are mid-August 2026: agentgateway [v1.4.1](https://github.com/agentgateway/agentgateway/releases/tag/v1.4.1), LiteLLM on the current 1.9x line.

![Two gates in one corridor: a crowded locked door on the left, an open unlocked path on the right](/static/img/articles/agentgateway-vs-litellm/cover.webp)

## They solve different jobs

[agentgateway](https://agentgateway.dev/docs/standalone/main/about/introduction/) is a general HTTP, gRPC, and TCP data plane that also fronts LLM, MCP, and A2A. The proxy is Rust. The Kubernetes controller is Go. It speaks [Gateway API](https://agentgateway.dev/docs/kubernetes/main/about/architecture/) (`HTTPRoute`, `GRPCRoute`, `TCPRoute`, `TLSRoute`) and can run as a [single binary](https://agentgateway.dev/docs/standalone/latest/deployment/binary/) with a watched YAML file. Its first-class LLM APIs cover chat, Responses, Anthropic Messages, embeddings, Realtime, rerank, and token count, plus [opaque passthrough](https://agentgateway.dev/docs/standalone/latest/llm/api-types/) for everything else.

LiteLLM is an AI gateway. It unifies a [wide provider catalog](https://docs.litellm.ai/docs/supported_endpoints) behind one OpenAI-compatible API: images, audio, video, batches, files, fine-tuning, OCR, skills, evals, search, plus MCP and A2A. It does not claim to be a general microservice gateway. Custom pass-through can forward selected HTTP paths. That is not Gateway API service routing.

![agentgateway as a data plane beside LiteLLM as an AI catalog](/static/img/articles/agentgateway-vs-litellm/plane-vs-catalog.webp)

The shared MCP and A2A boxes are the trap. They make the products look interchangeable on a feature matrix. Then one side also routes ordinary HTTP and gRPC, while the other adds images, audio, and batches as first-class APIs.

If the job is one data plane for services, models, and tools, the product under review is agentgateway. If the job is one SDK in front of a hundred providers, LiteLLM still wins that row. Feature-list comparisons hide that split, which is how a platform evaluation inherits the wrong default.

## The next controls sit behind a license

LiteLLM is open source. The MIT tree is real, large, and [self-hostable at $0](https://docs.litellm.ai/docs/enterprise). Saying it is "not OSS" is false. The precise claim from the evaluation is sharper: the controls a platform team needs next are not in that MIT tree.

The root [LICENSE](https://github.com/BerriAI/litellm/blob/main/LICENSE) splits the repository. Content outside `enterprise/` is MIT. Content under `enterprise/` uses the [BerriAI Enterprise license](https://github.com/BerriAI/litellm/blob/main/enterprise/LICENSE.md), which forbids production use without a valid subscription and allows copies only for development and testing. The gate is `LITELLM_LICENSE`. The official table is the source of truth:

| Area           | OSS                          | Enterprise                                    |
| -------------- | ---------------------------- | --------------------------------------------- |
| Auth           | API keys                     | SSO + SCIM, OIDC/JWT                          |
| Key management | Virtual keys, users, teams   | Organizations, delegated admin roles          |
| Security       | (blank in the table)         | Key rotation, secret managers                 |
| Guardrails     | Always-on / request-based    | Key and team scoped                           |
| Logging        | Request/response, Prometheus | Per-team callback routing, management-op logs |
| Deployment     | Single-region proxy          | Multi-region, admin/worker split              |

SSO is [free for up to five users](https://docs.litellm.ai/docs/enterprise). Beyond that, a license is required. Basic virtual keys, teams, and per-key budgets are OSS. Tag-based budgets, model-specific per-key budgets, soft alerts, and spend reports are Enterprise.

That list is not a set of nice-to-haves. It is close to what a security review asks for before it signs off: SSO past a handful of people, IdP tokens on the request path, a vault instead of `os.environ`, scoped guardrails, management-op logs. Those were the features the customer evaluation kept hitting.

agentgateway is [Apache 2.0](https://github.com/agentgateway/agentgateway/blob/main/LICENSE) end to end. The Linux Foundation [welcomed the project on 25 August 2025](https://www.linuxfoundation.org/press/linux-foundation-welcomes-agentgateway-project-to-accelerate-ai-agent-adoption-while-maintaining-security-observability-and-governance). The [charter](https://github.com/agentgateway/agentgateway/blob/main/CHARTER.md) puts technical oversight with a TSC under LF Projects. A search of the Apache tree for a license-key check returns nothing. JWT, CEL, mTLS, API keys, MCP OAuth, and external authorization are documented in the [OSS security pages](https://agentgateway.dev/docs/standalone/main/configuration/security/), not behind a key.

Solo.io sells [Solo Enterprise for agentgateway](https://docs.solo.io/agentgateway/latest/install/licensing/) as a separate distribution. It takes a license key at Helm install. When the key expires, the enterprise control plane warns and may stop reconciling; the data plane keeps running. Solo does not publish a complete OSS-versus-Enterprise feature matrix. That is a real gap for a buyer. It is not the same gap as a production-forbidden directory inside the project that was just cloned.

![LiteLLM enterprise features gated inside the same repository, Solo Enterprise as a separate distribution](/static/img/articles/agentgateway-vs-litellm/license-lock.webp)

Both projects have a paid tier and neither publishes a price. The difference is where the boundary sits. LiteLLM's is inside the repository and precisely documented: restrictive, and honest about being restrictive. agentgateway's is outside the repository and undocumented: permissive, and opaque. A buying decision can live with the first. A lasting architecture that needs to pivot cannot treat the second as the same kind of lock. That is the [Layer2C point](https://layer2c.com/) as well: a single platform is easy until the next control is the one it will not ship, or will only ship behind a contract.

## The security record is part of the default

A gateway sits in front of model keys, tool credentials, and agent traffic. Star count is not a security argument.

In the customer environment, LiteLLM was already deployed, and the critical issues that kept surfacing clustered on that proxy. The public record matches why that finding was hard to ignore.

LiteLLM's GitHub Security page lists [twelve advisories](https://github.com/BerriAI/litellm/security/advisories) in 2026, including three Critical. Two are in the [CISA Known Exploited Vulnerabilities catalog](https://www.cisa.gov/known-exploited-vulnerabilities-catalog): [CVE-2026-42208](https://nvd.nist.gov/vuln/detail/CVE-2026-42208), a pre-auth SQL injection in API-key verification (added 8 May 2026), and [CVE-2026-42271](https://nvd.nist.gov/vuln/detail/CVE-2026-42271), authenticated command execution via MCP stdio test endpoints (added 8 June 2026). KEV means CISA judged there was evidence of exploitation. On 24 March 2026 LiteLLM [disclosed](https://docs.litellm.ai/blog/security-update-march-2026) unauthorized PyPI publishes of 1.82.7 and 1.82.8 that harvested secrets. They pulled the packages, told operators to rotate, and rebuilt CI. Official Docker images were not affected. That disclosure is the behaviour a maintainer should show. It is also a class of event that does not belong on the default path for every team that reached for the familiar name.

agentgateway has [three published advisories](https://github.com/agentgateway/agentgateway/security/advisories). One is High: [GHSA-mvgg-jvj2-4frq](https://github.com/agentgateway/agentgateway/security/advisories/GHSA-mvgg-jvj2-4frq), stateful MCP sessions crossing routes and combining the original backend with the new route's authorization. Fixed in v1.4.0. Pin past it.

A smaller advisory list is not a proof of a smaller attack surface. LiteLLM is older and ships a management API, an admin UI, a database, user-supplied guardrail code, a Skills unzip path, and an MCP stdio launcher. agentgateway's OSS proxy ships fewer of those six. Counts track surface. Both projects patch first and disclose after.

The architectural point that belongs in an ADR is the shape of the failure. A Python service that accepts MCP stdio configs and talks to PostgreSQL for auth has a different failure mode than a Rust proxy with attachable CEL and JWT policies. CVE-2026-42208 and CVE-2026-42271 are examples of that shape. That is one reason the evaluation would not put LiteLLM on the default path for a multi-tenant agent platform.

## MCP and A2A are why the default matters

An AI gateway that only unifies `/chat/completions` is already behind the problem. The customer evaluation needed one place to front models and to expose MCP and A2A assets.

Both gateways terminate those protocols. Scoring them on a yes/no feature matrix hides the operational difference.

agentgateway treats tool and agent traffic as routes on the same plane as ordinary HTTP. MCP authorization uses the same [CEL engine](https://agentgateway.dev/docs/standalone/main/configuration/security/) as HTTP, and can hide disallowed tools from list responses. Callers authenticate to the gateway. The gateway injects upstream credentials. A mandatory audience check is one rule:

```yaml
authorization:
  rules:
    - require: 'jwt.aud == "my-service"'
```

`require` fails closed when the claim is missing. That is the documented reason to prefer it over a `deny` that errors open.

LiteLLM's MCP and A2A support is real, and its docs specify method coverage in more detail than agentgateway's. The OSS control plane around that traffic is virtual keys: model allowlists, budgets, rpm and tpm limits, team assignment. OIDC and JWT on the request path, SSO past five users, secret-manager reads, and key- or team-scoped guardrails are Enterprise.

If the first six months of an agent platform need IdP tokens on the data path, or a vault instead of `os.environ`, LiteLLM OSS is not the product that will be running. The deployment will be LiteLLM Enterprise, or the missing controls will be built next to it. agentgateway OSS already does the first of those jobs. That is the interoperability argument for a large organization: the next protocol should inherit the same plane, not a new license line.

## What you have to keep alive

agentgateway's minimum is one process: `agentgateway` or `agentgateway -f config.yaml`. No database is required on the request path. A Postgres or SQLite store is opt-in if the UI must persist edits. In Kubernetes the install adds the in-tree controller and the `agentgateway.dev` CRDs.

LiteLLM's documented production shape is a [Python FastAPI/Uvicorn proxy plus PostgreSQL](https://docs.litellm.ai/docs/proxy/prod). Redis 7.0+ is required as soon as there is more than one instance. Auth, budgets, model management, and spend tracking live in Postgres. Cross-instance rate limits and shared cache live in Redis. Official sizing is 1 vCPU and 4 Gi per worker, because the Prisma query engine's memory is a high-water mark that does not come back.

![agentgateway request path as one binary, LiteLLM as a proxy plus PostgreSQL and Redis](/static/img/articles/agentgateway-vs-litellm/ops-footprint.webp)

The stores are not a deployment inconvenience. They are where LiteLLM's virtual keys, teams, and spend logs live. Take them away and the OSS control plane the product was chosen for is gone. That is a fair price if that product surface is the requirement. It is the wrong bill if the requirement was a data plane.

LiteLLM's own [June 2026 migration post](https://docs.litellm.ai/blog/litellm-rust-launch) is the cleanest admission on the Python path. Under their harness it added about 7.5 ms and peaked around 359 MB. They describe CPU and memory climbing with concurrency, and pods getting OOM-killed. They committed a staged Rust cutover through 1 December 2026. As of this check a default deploy still serves `/chat/completions` from Python. Their Rust-path lab numbers (about 0.05 ms, 6,782 req/s, 32 MB) are that product measuring itself against a mock, not a comparison with agentgateway.

A public comparison does exist. It is not from the customer evaluation. On 26 June 2026 the agentgateway blog published a mock-upstream Fortio run by Lin Sun ([part 1](https://agentgateway.dev/blog/2026-06-26-benchmarking-agentgateway-vs-litellm/), [part 2](https://agentgateway.dev/blog/2026-06-26-benchmarking-agentgateway-vs-litellm-part-2/)), with scripts at [linsun/litellm-agw-perf](https://github.com/linsun/litellm-agw-perf). Part 1 pushed both proxies to the wall for three seconds: about 37k QPS and sub-2 ms P99 on agentgateway versus about 3.2k QPS and 32 ms P99 on LiteLLM, with LiteLLM near 12 GB RAM against tens of megabytes.

![Throughput and latency from Lin Sun's max-QPS Fortio run on the agentgateway blog, mock OpenAI backend](/static/img/articles/agentgateway-vs-litellm/bench-max-qps.webp)

Part 2 is the fairer chart. It held a 3,000 QPS target for 30 seconds. agentgateway held the rate at 0.23 ms P50. LiteLLM averaged about 2,466 QPS at 12 ms P50 and still sat near 12 GB.

![Fixed 3,000 QPS run from the same agentgateway blog series: agentgateway held the target, LiteLLM did not](/static/img/articles/agentgateway-vs-litellm/bench-fixed-qps.webp)

That is a project-published head-to-head, not a third-party one, and it measures proxy overhead against a mock, not model time. The 12 GB figure also does not match LiteLLM's own 359 MB peak on a different harness. Those tests were not rerun for this piece. The tables are not a settled speed winner. What the sources do carry is narrower: LiteLLM's maintainers treat the current Python path as the problem they are leaving, and the only public comparison of the two proxies shows agentgateway adding much less overhead on a mock. The operational claim that does not depend on those benches is still the process list.

## When LiteLLM is still the better pick

Take the catalog job. The requirement is first-class images, audio, video, batches, fine-tunes, evals, or skills, not passthrough. The team already lives in the Python SDK and wants in-process calls plus a proxy. Virtual keys, OSS budgets, and fallbacks are the control plane needed for the next year, and SSO or OIDC can wait. Gateway API, gRPC, and a general service plane are out of scope.

LiteLLM also ships on a weekly minor cadence, with patches on the [four most recent stable lines](https://docs.litellm.ai/docs/enterprise). If the constraint is "the provider landed yesterday and a driver is needed tonight," that machine is the point. Budget the license the day SSO, OIDC, or a vault shows up on the roadmap. Do not discover `LITELLM_LICENSE` after the virtual keys are already in production.

## What the evaluation concluded

The customer needed one plane for ordinary APIs and for LLM, MCP, and A2A. The next identity and policy controls had to live in the tree that gets cloned, not behind `LITELLM_LICENSE`. The process list had to stay short. Project ownership mattered: Apache 2.0 under LF technical governance, hosted by AAIF since June 2026, so a fork keeps the name and the charter.

That is why the evaluation recommended agentgateway for a lasting agent platform, and why LiteLLM stayed the wrong long-run default even though it was the first name in the room. The features a platform team actually needs next should not be the paid ones, and the published failure modes on the familiar proxy should not be the shared front door.

agentgateway still has strings. Solo Enterprise exists, and the public matrix of what stays Apache is incomplete. The first-class LLM catalog is smaller. The only public bake-off against LiteLLM is on its own blog, against a mock. Foundation hosting is a fork-and-name safeguard, not a proof that day-to-day maintenance is broadly distributed.

The "no strings attached" sentence stops being true the moment the architecture needs Solo's unpublished enterprise control plane: embedded OPA as a product, RFC 8693 on-behalf-of token exchange as a supported feature, distributed global rate limits, or ambient waypoint management. Then those controls are built around the Apache binary, or the distribution is bought. The starting point is still an unencumbered data plane, not a tree that already withholds SSO.

## When neither one is

If the organization already standardized on Envoy Gateway, [Envoy AI Gateway](https://github.com/envoyproxy/ai-gateway) is the filter to operate, not a second proxy. If Kong is already the API platform, AI is one more plugin class. If nobody can run a gateway at all, a hosted router is the honest answer. If the requirement is one control plane for ordinary north-south ingress and AI traffic, [kgateway](https://github.com/kgateway-dev/kgateway) can drive Envoy for services and agentgateway for agent workloads.

If there is no platform or tech team to own an open solution, stop and buy something. An unencumbered Apache 2.0 data plane is an asset only if somebody operates it. That is the build-versus-buy line [Layer2C](https://layer2c.com/) argues: a single platform is easy until the missing feature or the closed extension point shows up. Buying is the correct answer when the team cannot carry the ownership cost. A large organization that does have that team should treat integration and interoperability as the reason to stay on an open plane.

## Before a POC

Print [LiteLLM's OSS versus Enterprise table](https://docs.litellm.ai/docs/enterprise). Tick every control the first six months actually need. If SSO beyond five users, OIDC on the request path, or a secret manager is on that list, stop calling LiteLLM the open source option. The comparison is then a paid LiteLLM against an Apache data plane.

Then spend an hour with agentgateway. Run the [binary](https://agentgateway.dev/docs/standalone/latest/deployment/binary/) against one MCP server. If the catalog is still the binding constraint, run LiteLLM's compose against one provider and decide whether that row is worth the lock.

The evaluation's rule was simple. For a lasting agent platform, start with agentgateway. Reach for LiteLLM when the binding constraint is provider coverage, and put the license on the ADR the same day.
