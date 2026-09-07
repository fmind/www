---
name: release
description: Cut and verify a www.fmind.dev semver release from local gates through live Cloud Run proof. Use only when the owner explicitly authorizes release.
license: MIT
metadata:
  author: Médéric HURIER (Fmind)
---

# Release

This workflow contains commits, pushes, a GitHub release, and a production deployment. Run it only after explicit owner authorization. Local readiness never grants publication authority, and already published tags are immutable.

## Preconditions

- Work from `main`; inspect `git status --short --branch`, HEAD, and upstream. Separate unrelated changes and never broad-stage, reset, clean, force-push, or rewrite history.
- Confirm the release tools target the intended accounts and project. If `infra/` changed, complete the `infra` skill and its explicitly authorized live plan first.

## Workflow

1. Run the full local delivery gate and the separate network link check:

   ```bash
   mise run all
   mise run check:links
   git status --short
   ```

   `all` includes format, check, offline pytest with coverage, distribution and OCI builds, image scanning and smoke testing, and browser journeys. Resolve every warning, failure, and unexpected generated diff.

1. Stage only reviewed implementation paths and commit them with Conventional Commits:

   ```bash
   git add -- <reviewed-path>...
   git diff --cached --check
   git diff --cached
   git commit -m "<type>(<scope>): <change>"
   ```

1. Compute the next semver, synchronize package and MCP Registry metadata, and generate the changelog:

   ```bash
   NEXT_TAG=$(git-cliff --config ~/.config/git-cliff/cliff.toml --bumped-version)
   uv version "${NEXT_TAG#v}" --no-sync
   # Set server.json version to ${NEXT_TAG#v} with a reviewed edit.
   git-cliff --config ~/.config/git-cliff/cliff.toml --bump -o CHANGELOG.md
   ```

   The `pyproject.toml`, `uv.lock`, and `server.json` versions must equal the tag without `v`.

1. Re-run `mise run all`, inspect the exact release diff, then create and tag the release commit:

   ```bash
   git add -- pyproject.toml uv.lock server.json CHANGELOG.md
   git diff --cached --check
   git diff --cached
   git commit -m "chore(release): ${NEXT_TAG}"
   git tag -a "${NEXT_TAG}" -m "${NEXT_TAG}"
   git push origin main "${NEXT_TAG}"
   ```

1. Publish release notes and bind monitoring to the release commit rather than the newest unrelated run:

   ```bash
   mkdir -p .agents/tmp
   git-cliff --config ~/.config/git-cliff/cliff.toml --latest --strip all > .agents/tmp/release-notes.md
   gh release create "${NEXT_TAG}" --title "${NEXT_TAG}" --notes-file .agents/tmp/release-notes.md
   RELEASE_SHA=$(git rev-parse HEAD)
   RUN_ID=$(gh run list --workflow deploy.yml --commit "${RELEASE_SHA}" --limit 1 --json databaseId --jq '.[0].databaseId')
   gh run watch "${RUN_ID}" --exit-status
   ```

1. Verify production independently of CI. Tie the ready revision, 100% traffic, and deployed digest to the released SHA; inspect health, discovery, browser journeys, representative Lighthouse modes, and recent error logs:

   ```bash
   gcloud run services describe www-fmind-dev --project=www-fmind-dev --region=europe-west1
   xh --headers --follow https://fmind.dev
   xh --headers https://www.fmind.dev/health
   BROWSER_BASE_URL=https://www.fmind.dev mise run test:browser
   mise run test:lighthouse -- --base-url https://www.fmind.dev
   ```

   Check `/articles/`, `/sites/`, `/articles/feed.xml`, `/llms.txt`, `/sitemap.xml`, `/api/profile`, and `/.well-known/mcp/server-card.json`. Preserve exact per-page/per-mode Lighthouse results; one green page is not proof of 100 everywhere. Remove only the release-notes temporary directory after preserving evidence, then report every proof boundary separately.

## Gotchas

- Preserve the `vX.Y.Z` tag prefix; never delete, overwrite, or force-move a published tag.
- The runtime is a locked, non-root Python image containing the virtual environment plus the repository's `content/` and `static/` trees; verify both through live journeys.
- GitHub success does not prove the expected revision has traffic. A healthy endpoint does not prove the expected digest or discovery contract.
- MCP Registry publication remains a separate owner action; a site release does not authorize `mcp-publisher publish`.

## Official Skills

- Use [release](~/.agents/skills/release/SKILL.md) for semver and git-cliff mechanics.
- Use [production-readiness](~/.agents/skills/production-readiness/SKILL.md) when the release changes runtime risk.

## Documentation

- [GitHub CLI releases](https://cli.github.com/manual/gh_release_create)
