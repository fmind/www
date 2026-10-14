+++
title = "MCP 2026–07–28: Stateless core, enterprise authorization, and SDK betas"
description = "Running a remote Model Context Protocol (MCP) server behind multiple instances presents immediate infrastructure challenges."
date = "2026-07-08"
tags = ["Agent", "Guide"]
slug = "mcp-2026-07-28-stateless-core-enterprise-authorization-and-sdk-betas"
syndicated = "https://medium.com/@fmind/mcp-2026-07-28-stateless-core-enterprise-authorization-and-sdk-betas-2646a980d594"
draft = false
+++

Running a remote [Model Context Protocol](https://modelcontextprotocol.io) (MCP) server behind multiple instances presents immediate infrastructure challenges. Because the original spec requires an `initialize` handshake and pins sessions to a specific instance via the `Mcp-Session-Id` header, you are forced to configure sticky routing or a shared session store at the load balancer level. This makes scaling beyond a single process unnecessarily complex.

To address these limitations, the MCP project released three updates in mid-2026: a [release candidate for the 2026–07–28 specification](https://blog.modelcontextprotocol.io/posts/2026-07-28-release-candidate/), a stable [enterprise-managed authorization extension](https://blog.modelcontextprotocol.io/posts/enterprise-managed-auth/), and [beta SDKs](https://blog.modelcontextprotocol.io/posts/sdk-betas-2026-07-28/) across Python, TypeScript, Go, and C#.

Together, these changes address three core production challenges: stateless scaling, centralized identity management, and protocol version stability.

![Photo by Robynne O on Unsplash](/static/img/articles/mcp-2026-07-28-stateless-core-enterprise-authorization-and-sdk-betas/cover.webp)

Photo by [Robynne O](https://unsplash.com/@roborobs?utm_source=medium&utm_medium=referral) on [Unsplash](https://unsplash.com?utm_source=medium&utm_medium=referral)

### Stateless core: scaling without handshakes

The 2026–07–28 specification removes the stateful handshake and session management. The `initialize`/`initialized` handshake is gone, and so is the protocol-level session. Client information, protocol version, and capabilities now travel in a request’s `_meta` field on every call, making each request self-describing.

This allows remote servers to run behind standard round-robin load balancers without session affinity or synchronization. Any instance can answer any request without first replaying a handshake or looking up shared session state.

A standard tool call now requires no prior initialization and carries all context self-contained:

```http
POST /mcp HTTP/1.1
Mcp-Protocol-Version: 2026-07-28
Mcp-Method: tools/call
Mcp-Name: search

{"jsonrpc":"2.0","id":1,"method":"tools/call",
 "params":{"name":"search","arguments":{"q":"otters"},
           "_meta":{"io.modelcontextprotocol/protocolVersion":"2026-07-28",
                    "io.modelcontextprotocol/clientInfo":{"name":"my-app","version":"1.0"}}}}
```

The `_meta` block carries the client identity and protocol version. The `Mcp-Method` and `Mcp-Name` HTTP headers allow load balancers or gateways to route the call without parsing the JSON payload body.

Because the protocol is now stateless, servers can no longer interrupt an active connection to request input. Instead, the spec introduces Multi Round-Trip Requests. When a tool requires input, the server returns an `InputRequiredResult` containing an opaque `requestState`. The client must then re-invoke the tool call, passing the user’s input alongside the `requestState` token. This design allows any available instance to process the response without holding a connection open.

This stateless model increases request payload sizes because client capabilities and session parameters must be transmitted with each call. However, it enables standard production features: full JSON Schema 2020–12 validation, cache-control hints (`ttlMs` and `cacheScope`), W3C Trace Context propagation for OpenTelemetry, and a modular extensions framework. The first two official extensions are MCP Apps (sandboxed HTML-based user interfaces) and a stateless version of Tasks.

### Centralized identity: enterprise-managed authorization

Beyond horizontal scaling, managing MCP server access across a team requires central authorization. The standard per-user OAuth flow forces every employee to authorize each MCP server individually, which complicates onboarding, lacks centralized audit logs, and mixes personal and corporate access.

To address this, the enterprise-managed authorization extension (stabilized in June 2026) implements the [Identity Assertion JWT Authorization Grant](https://datatracker.ietf.org/doc/draft-ietf-oauth-identity-assertion-authz-grant/) (ID-JAG). During single sign-on (SSO), the client trades the user’s identity token for an ID-JAG scoped to a specific target server via [RFC 8693](https://www.rfc-editor.org/rfc/rfc8693) token exchange. The client then presents this grant to the MCP server’s authorization server to obtain an access token. This token exchange runs entirely in the background, removing the need for individual interactive consent screens:

```text
# 1. IdP: swap the SSO identity for a grant good only for one MCP server
grant_type=urn:ietf:params:oauth:grant-type:token-exchange
requested_token_type=urn:ietf:params:oauth:token-type:id-jag
resource=https://mcp.example/          # the specific server this grant targets
subject_token=<the user's SSO id_token>

# 2. MCP authorization server: swap that grant for the server's access token
grant_type=urn:ietf:params:oauth:grant-type:jwt-bearer
assertion=<the ID-JAG returned by step 1>
```

Access control is governed by the organization’s existing identity provider (IdP) groups and roles. Administrators can configure permissions from a single control plane, and all access generates centralized audit trails.

This extension is additive and opt-in. The default remains per-user OAuth for consumer configurations. MCP servers advertise support for enterprise-managed authorization as a capability, and clients negotiate it during connection. The IdP only validates policy and mints the grant, meaning it never intercepts raw MCP traffic, and each access token is strictly audience-restricted to its target server.

### Version stability: release deprecation windows and SDK betas

To make the protocol viable for long-term roadmaps, MCP has introduced a formal specification lifecycle. Features now transit through `Active → Deprecated → Removed` states, with a minimum deprecation window of twelve months. Furthermore, proposed changes to the Standards Track must be validated against a formal conformance suite, and specifications are versioned by calendar date.

In the 2026–07–28 revision, several legacy features (Roots, Sampling, and Logging) are deprecated. They will be replaced by tool parameters, resource URIs, direct provider APIs, and standard error output or OpenTelemetry streams.

To allow teams to validate these changes ahead of the final specification release on July 28, the project has published beta SDKs across four languages:

```bash
# Python — opt-in pre-release
pip install "mcp[cli]==2.0.0b1"
# TypeScript v2 — new split server/client packages
npm install @modelcontextprotocol/server@beta @modelcontextprotocol/client@beta
# Go — same module path, pre-release tag
go get github.com/modelcontextprotocol/go-sdk@v1.7.0-pre.1
# C#
dotnet add package ModelContextProtocol --prerelease
```

The existing `v1` SDK lines will receive bug and security patches for at least six months following the final release. Backward compatibility is maintained: `v2` servers continue to accept legacy 2025–11–25 handshake requests, allowing clients to upgrade independently.

### What this means for teams running agents in production

MCP is now hosted by the [Agentic AI Foundation](https://aaif.io) under the Linux Foundation. This open governance model ensures neutral stewardship while retaining a focused [specification enhancement process](https://modelcontextprotocol.io/specification/versioning) led by active maintainers. Implementing a predictable release cadence, formal deprecation timelines, and conformance testing establishes MCP as a reliable infrastructure standard rather than an unstable library.

With the 2026–07–28 specification locking at the end of July and SDK betas available, you should evaluate the following points in your deployment:

1. **Identify session dependencies.** If your setup relies on sticky routing or shared session tables, migrating to the stateless core will allow you to transition to standard round-robin load balancing and simplify your infrastructure.
2. **Evaluate your onboarding flow.** If your servers currently require individual user consent redirects, verify if your IdP and client support the new enterprise token-exchange extension to enable role-based authorization.
3. **Plan your version migrations.** If your systems are pinned to the original 2025–11–25 specification, utilize the 12-month deprecation window to map out updates to your tool and resource signatures.
