# Changelog

All notable changes to this project are documented in this file.

## [2.11.0] - 2026-11-11

### 🚀 Features

- _(sites)_ Streamline LLM hosting workloads and refresh frontier model catalogs

### 🐛 Bug Fixes

- _(www)_ Drop OTLP tracing, tighten analytics, and sync MCP UI
- _(security)_ Enforce TLS 1.2 in news fetches and clear CodeQL shell sink
- _(www)_ Harden news SSRF checks, canonical redirects, metadata snapshots, and links

### 🧪 Testing

- _(browser)_ Unroute consent contexts and skip same-origin proxy
- _(browser)_ Wait for distinct volume override URL before reload

### ⚙️ Build & CI

- _(quality)_ Prefer HTTPS apt mirrors and bound timeouts for browser deps

## [2.10.1] - 2026-11-11

### 🐛 Bug Fixes

- _(www)_ Harden security boundaries, MCP metadata, and web LCP

### 📚 Documentation

- Scope MIT license and document public repository posture
- _(agents)_ Note mise.local.toml copy for temporary worktrees
- Trim repository docs and maintenance skills

### ⚙️ Build & CI

- _(tasks)_ Harden Lighthouse process test and broaden checks

### 🧹 Miscellaneous

- _(highlighting)_ Align Chroma code blocks with fmind/theme v10

## [2.10.0] - 2026-11-10

### 🚀 Features

- _(news)_ Add 2026-11-09 edition
- _(agents)_ Allow cross-origin reads of llms.txt and llms-full.txt
- _(sites)_ Refresh the GitHub MCP catalog to v2.0.2 and re-verify sources
- _(sites)_ Remove the quality lab from the LLM hosting tool
- _(news)_ Keep the 30 latest editions in full in the Markdown index and link older ones
- _(sites)_ Default batch workloads to Flex-start nodes and batch API rates, and re-verify prices
- _(news)_ Add 2026-11-10 edition
- _(seo)_ Enrich JSON-LD, OG metadata, mobile targets, and range headers

### 🐛 Bug Fixes

- _(deploy)_ Print the safe message of own verification errors
- _(scripts)_ Bound deploy, scan, and news subprocess calls with timeouts
- _(news)_ Report a wrongly typed API field per link instead of aborting the batch
- _(sites)_ Never echo an unknown billing plan in the validation message
- _(sites)_ Read the usage window like every other query value
- _(seo)_ Claim only active credentials in JSON-LD and drop the graph from noindex news editions
- _(home)_ Match the section toolbar breakpoints at fractional widths
- _(mcp)_ Serve the site 404 for unknown /mcp-prefixed paths
- _(assets)_ Keep the hashed image dimensions when no build manifest exists
- _(mcp)_ Drop the apex host and origin that production always redirects
- _(mcp)_ Remove the test-only host from the production allow-list
- _(articles)_ Replace the removed AWS Strands guide link
- _(infra)_ Accept followed 2xx on apex uptime check
- _(sites,mcp)_ Enforce valid Cloud TPU slice topologies and boundary validation
- _(security,ci)_ Harden HTTP boundary, telemetry, workflows, and locks

### ⚡ Performance

- _(feeds)_ Point the Atom icon at the 26 KB favicon instead of the 830 KB logo
- _(highlighting)_ Emit spans only for token classes with their own style
- _(news)_ Tokenize editions once at load instead of on every search
- _(telemetry)_ Import the OpenTelemetry SDK only when tracing is configured
- _(http)_ Hash the stylesheet and build the constant security headers once

### ♻️ Refactor

- _(lighthouse)_ Check sitemap locations and the tmp output path with plain rules
- _(scan)_ Fail closed on missing target names and reuse the image gate task
- _(images)_ Share one safe file read and one image opener
- _(deploy)_ Drop unset head-check fallbacks and share the public probes
- _(news)_ Let the GitHub API fallback handle site pages
- _(sites)_ Share automatic_setup with the GPU and TPU comparison
- _(sites)_ Type whole hosting quantities as integers
- _(sites)_ Drop the cost frame field that only tests read
- _(sites)_ Render monthly hours from the server constant
- _(content)_ Name the article once per rejection and share the UTC-midnight builder
- _(templates)_ Share the section rail, footer link class, and card image markup
- _(ranges)_ Answer range lists with the full response and drop multipart
- _(app)_ Build the snapshot routes from one table
- _(app)_ Drop unused create_app directories and the /static redirect to a 404
- _(sites)_ Dispatch site pages from a view map checked at startup
- _(mcp)_ Require every server factory argument

### 📚 Documentation

- _(agents)_ Include the news API in the CLI contract
- Align guides with the pipeline and keep one owner per rule
- _(security)_ Require uniform bucket-level access on state bucket
- _(articles)_ Drop purged Google Drive example links

### 🧪 Testing

- _(news)_ Count closer searches instead of timing the page parser
- _(sites)_ Derive MCP context totals from the measured catalog
- _(sites)_ Remove hosting tests that repeat other tests
- _(app)_ Assert the article search filters by query and drop redundant string checks
- _(telemetry)_ Cover the opt-in OTLP provider path
- _(ranges)_ Cover ignored empty range sets
- _(browser)_ Drop clock-dependent price assertions, guard own contexts, and follow removed controls
- Share the logger, ASGI scope, and MCP request helpers
- Build the shared client and MCP server once per session
- _(mcp)_ Drop assertions other checks already make

### ⚙️ Build & CI

- Re-check main head in the deploy job and share one locked mise setup
- Allowlist the Docker build context and state the base image once
- Trim gate tasks and state the Trivy policy once
- Pin dprint plugins by tarball checksum

### 🧹 Miscellaneous

- _(infra)_ Drop OpenTofu outputs nobody reads
- Remove no-op classes, rules, and the import-time tag validation
- _(static)_ Delete the unlinked web manifest and its route
- Ignore agent worktrees and align scan notes with the merged cleanup

## [2.9.0] - 2026-11-08

### 🚀 Features

- _(news)_ Add news API, MCP tools, and single-list edition format

### 🐛 Bug Fixes

- _(server)_ Bind loopback by default and let the image set HOST=0.0.0.0
- _(branding)_ Use the theme master logo unchanged

### ⚡ Performance

- Speed up image checks, container build, and test suite

### ⚙️ Build & CI

- Unify deploy rollout, fold infra checks, and trim docs

## [2.8.1] - 2026-11-08

### ⚡ Performance

- _(articles)_ Stop archive cards from transitioning out of default colors
- _(home)_ Render portfolio sections without content-visibility
- _(assets)_ Record raster dimensions in the build manifest

### 📚 Documentation

- _(release)_ Watch every main push through promotion
- _(articles)_ Point the CLI guidance link at its moved path

### 🧪 Testing

- _(browser)_ Forbid scroll-time default-style transitions on every page layout

### ⚙️ Build & CI

- _(deploy)_ Deploy only the current head of main

## [2.8.0] - 2026-11-08

### 🚀 Features

- _(sites)_ Size each catalog model on its own machine
- _(news)_ Import 166 daily news editions
- _(news)_ Serve daily editions at /news with an Atom feed and curation skill
- _(news)_ Markdown editions with highlights and noindex edition pages
- _(news)_ Move a corrected edition's feed update time with updated front matter
- _(news)_ Show the past week as highlight cards and older editions as links
- _(news)_ Reject long descriptions, label archive days, and align past-week cards
- _(news)_ Show editions as ranked cards, list the archive one day per line, and open past-week cards whole
- _(news)_ Add 2026-11-04 edition
- _(news)_ Add 2026-11-05 edition
- _(feeds)_ Indent XML and add the logo icon and article thumbnails
- _(news)_ State manual curation in index description
- _(news)_ Add 2026-11-06 edition
- _(news)_ Draft and publish Chat editions without agent Git access
- _(articles)_ Describe every cover image for social cards
- _(web)_ Cache fonts immutably and tighten SEO and accessibility
- _(app)_ Correlate logs with request traces and time startup phases
- _(privacy)_ Disclose the 30-day server request logs
- _(infra)_ Monitor the apex domain, TLS expiry, and capacity aborts

### 🐛 Bug Fixes

- _(content)_ Replace teaser descriptions and duplicated opening headings
- _(content)_ Keep article links on fmind.dev and drop Medium leftovers
- _(news)_ Drop a link-shared Drive guide of unverified provenance
- _(news)_ Shorten 45 archive descriptions to the 30-word limit
- _(news)_ Shorten the remaining 102 descriptions to the 30-word limit
- _(news)_ Keep drafted links exact and reach readers with same-day additions
- _(mcp)_ Reject unknown tools as invalid params and bound arguments
- _(scripts)_ Read only needed analytics partitions and bound news fetches

### ⚡ Performance

- _(content)_ Parse each article once and index only visible text
- _(assets)_ Hash static files at image build instead of every cold start

### ♻️ Refactor

- Rely on Python 3.14 lazy annotations
- Move article image derivatives out of the runtime package
- _(content)_ Remove Hugo-era Goldmark and Chroma emulation
- _(app)_ Serve every unknown path from one not-found route
- _(lighthouse)_ Audit only the portfolio set
- _(articles)_ Reuse the body cover alt for social cards
- _(sites)_ Dedupe calculator logic and slim the MCP hosting result

### 📚 Documentation

- _(news)_ Preview editions as a single ranked list
- _(security)_ Renew the advisory review for the 2026-11-07 serving image
- Sync README, AGENTS, SECURITY, and skills with the review fixes
- _(articles)_ Match search intent in the Poetry vs uv and agent platform snippets

### 🧪 Testing

- _(browser)_ Wait longer for production images in cross-browser journeys
- _(lighthouse)_ Audit the news index on desktop and mobile
- _(cross-browser)_ Give remote runs 60 s for WebKit startup
- _(browser)_ Deflake resize assertion and double CI test concurrency
- Isolate tests from the Git environment a hook exports
- _(cross-browser)_ Keep two workers on CI runners

### ⚙️ Build & CI

- _(deploy)_ Parallelize verification jobs and add content path gating
- _(image)_ Make the local image platform configurable
- _(deploy)_ Compare content-only pushes with the last verified deployment
- Upgrade mise, mise-action, login-action, BuildKit, and Cloud SDK pins
- _(image)_ Refresh Python base, uv, and Tailwind pins
- Fix WebKit image wait, PR content detection, and build waste
- Key mise tool caches on lockfiles instead of mise.toml

### 🧹 Miscellaneous

- _(deps)_ Upgrade mise, its action, the Python base image, and locked tools
- Remove syndication leftovers and tidy scripts and docs
- _(mise)_ Lock tools for linux-arm64
- _(deps)_ Upgrade mise tools to latest
- _(deps)_ Upgrade Python dependencies to latest
- _(deps)_ Upgrade watchdog to 7.1.0
- _(infra)_ Upgrade Google providers to 8.10.0 and declare the STS API

## [2.7.1] - 2026-11-02

### 🚀 Features

- _(infra)_ Add a project budget and require GitHub-hosted runners

### 🐛 Bug Fixes

- _(content)_ Drop Medium syndication links and the HackerNoon profile
- _(mcp)_ Reject out-of-range search limits and over-long queries
- _(sites)_ Keep pilot measurements entered with a configuration change

### ⚡ Performance

- Validate the article index JSON-LD once and compress the MCP server card

### ♻️ Refactor

- _(content)_ Retire canonical and syndicated article frontmatter

### 📚 Documentation

- _(articles)_ Correct facts in eleven articles
- Renew the advisory review, trim duplicated instructions, and pin git-cliff

### ⚙️ Build & CI

- Clear cancelled candidates and keep weekly scans independent

## [2.7.0] - 2026-11-01

### 🚀 Features

- _(profile)_ Align public profiles and channels
- _(sites)_ Refresh the LLM hosting catalog with Mistral Large 4

### 🐛 Bug Fixes

- Harden the CSP and MCP inputs and keep keyboard focus visible

### 📚 Documentation

- _(articles)_ Fix typos, dead links, and image alt text

### ⚙️ Build & CI

- Clear failed candidate tags and tighten delivery and IAM

## [2.6.1] - 2026-10-31

### 🐛 Bug Fixes

- Harden MCP, privacy, and deployment after a full review
- _(deploy)_ Read no shared cache in the id-token job and gate manual deploys

### 📚 Documentation

- Document non-interactive MCP Registry auth and normalize MLOps repo link
- _(agents)_ Record the approved visual style and the tmp/ rule

### ⚙️ Build & CI

- Switch to BetterLeaks and jactionlint and split offline and network checks

### 🧹 Miscellaneous

- Update MLOps course and skills GitHub links to fmind

## [2.6.0] - 2026-10-29

### 🚀 Features

- _(api)_ [**breaking**] Drop the unused social header flag
- _(sites)_ Add Cloud TPU and refresh the October 29 LLM hosting snapshot

### 🐛 Bug Fixes

- Harden website behavior and optimize page loading
- _(deps)_ Bump pillow, brotli and certifi and regenerate image derivatives (#37)
- _(deploy)_ Drop the manual-candidate tag on promotion
- _(deps)_ Pin Node.js 26.12.1 for the October security release (#38)
- _(articles)_ Pin the retired gh-dash config link
- _(sites)_ Fall back to a usable billing plan and show real inputs
- _(mcp)_ Reject non-positive search limits
- _(log)_ Record pathsend response sizes while the span is current
- _(data)_ Render biography autolinks and type structured data
- _(a11y)_ Nest home page headings in order
- _(articles)_ Archive the retired TechTarget 3Vs link
- _(lighthouse)_ Retry once on transient NO_NAVSTART trace errors

### ♻️ Refactor

- Remove unused icons, styles, and calculator code
- _(images)_ Require the derivative lock

### 📚 Documentation

- _(articles)_ Drop links to the retired MLOps Coding Assistant
- _(privacy)_ Drop the retired AgentOps course site
- _(articles)_ Link fmind.dev copies instead of Medium
- _(skills)_ Update article publishing workflow
- Correct module ownership and analytics partitioning
- _(security)_ Record the October 29 advisory review
- _(security)_ Document private repository posture

### 🧪 Testing

- Share startup snapshots and consolidate calculator tests
- Drop the unused integration marker filter

### ⚙️ Build & CI

- _(dependabot)_ Run security updates only
- Pin mise and Cloud SDK versions and correct workflow notes

### 🧹 Miscellaneous

- _(deps)_ Upgrade mise tools to latest
- _(deps)_ Upgrade Python dependencies to latest
- _(deps)_ Upgrade container base images to latest
- _(deps)_ Upgrade OpenTofu providers to latest
- _(deps)_ Upgrade GitHub Actions to latest
- _(deps)_ Upgrade dprint plugins to latest

## [2.5.0] - 2026-10-14

### 🚀 Features

- _(sites)_ Add MCP context-cost calculator
- _(analytics)_ Add Google Analytics 4 behind explicit consent
- _(sites)_ Simplify the MCP calculator and open every hosting section

### 🐛 Bug Fixes

- _(sites)_ Address MCP context calculator review findings
- _(seo)_ Complete article descriptions and canonical exports
- _(contact)_ Split the consent notice and drop RSS from /connect

## [2.4.0] - 2026-10-12

### 🚀 Features

- _(sites)_ Simplify and correct LLM self-hosting estimates

### 🐛 Bug Fixes

- _(sites)_ Improve calculator table heading contrast

### 📚 Documentation

- Reference the fmind/theme DESIGN.md palette source

## [2.3.0] - 2026-10-06

### 🚀 Features

- _(seo)_ Publish the full sameAs profile list in the identity graph

### 🐛 Bug Fixes

- _(static)_ Answer HEAD for unknown assets with 404
- _(image)_ Apply Debian security updates in the runtime stage
- _(mcp)_ Stop serving unbounded subscription streams
- _(feed)_ Make srcset image candidates absolute
- _(css)_ Style daisyUI links and checkboxes
- _(sites)_ Reject non-ASCII numbers and report MCP rejections plainly
- _(analytics)_ Stop counting HEAD requests as pageviews
- _(security)_ Scan tagged Cloud Run revisions
- _(fonts)_ Verify font archives against pinned digests
- _(content)_ Repoint the dot mise configuration link

### ⚡ Performance

- _(markdown)_ Reuse one inline parser per document
- _(infra)_ Raise Cloud Run request concurrency from 8 to 32
- _(portrait)_ Bound the public portrait to 2048px
- _(fonts)_ Preload the code font on monospace pages

### ♻️ Refactor

- Remove unused rendering and search helpers

### 📚 Documentation

- _(infra)_ Record concurrency 32 and the revision-name apply workaround
- Refresh advisory review, document manual rollback, and trim duplication

### 🧪 Testing

- _(browser)_ Escape dots in the calendar hostname pattern
- Cover draft exclusion, page CSP, and exact archive totals

### ⚙️ Build & CI

- _(links)_ Skip cloud.google.com links that GitHub runners cannot reach
- _(deploy)_ Rebuild the runtime stage so security updates apply

### 🧹 Miscellaneous

- _(deps)_ Upgrade mise tools to latest
- _(deps)_ Upgrade Python dependencies to latest
- _(deps)_ Upgrade OpenTofu providers to latest
- _(deps)_ Upgrade GitHub Actions to latest
- _(deps)_ Upgrade dprint plugins to latest
- Drop the CLAUDE.md bridge and widen ignore files

## [2.2.3] - 2026-09-27

### 🐛 Bug Fixes

- _(agents)_ Clarify article reading fallbacks and bulk exports

## [2.2.2] - 2026-09-25

### 🐛 Bug Fixes

- Harden startup, deployment, calculator evidence, and caching
- Keep generated Cloud Run revision names out of infrastructure drift plans

### 🧹 Miscellaneous

- _(deps)_ Upgrade Python dependencies
- _(deps)_ Upgrade pinned build tools

## [2.2.1] - 2026-09-23

### 🐛 Bug Fixes

- _(mcp)_ Reject unused notification streams and refresh release guidance

## [2.2.0] - 2026-09-23

### 🚀 Features

- _(articles)_ Add section navigation and feed discovery
- _(articles)_ Publish agents-md-speaks-unix (#31)
- _(delivery)_ Promote verified candidates and scope CI identities
- _(site)_ Link a cached stylesheet and describe pages accurately

### 🐛 Bug Fixes

- _(sites)_ Keep calculator scenarios exact and accessible

### 🧪 Testing

- _(browser)_ Wait for article rail resize layout

## [2.1.0] - 2026-09-19

### 🚀 Features

- _(finops)_ Add billing export configuration and analytics guidance

### 🐛 Bug Fixes

- _(ci)_ Qualify production browser and Lighthouse journeys on clean runners
- _(contact)_ Show Luxembourg location on contact and QR pages
- _(delivery)_ Verify ready releases and parallelize browser journeys

### 📚 Documentation

- _(release)_ Preserve published changelogs during generation

## [2.0.1] - 2026-09-19

### 🐛 Bug Fixes

- _(discovery)_ Clarify identity location services and article attribution

## [2.0.0] - 2026-09-19

### 🐛 Bug Fixes

- Polish portfolio and harden v2 release operations
- _(ci)_ Allow sandboxed Lighthouse Chromium on Ubuntu

### 📚 Documentation

- _(release)_ Require CI and live proof before tagging

## Earlier releases

Versions 0.1.0 to 1.8.1 are documented in the GitHub releases of this repository (`gh release view v<version>`) and in this file's Git history.
