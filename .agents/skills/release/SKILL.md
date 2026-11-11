---
name: release
description: Cut and verify an authorized www.fmind.dev semver release through Cloud Run, GitHub, and MCP Registry.
license: MIT
metadata:
  kind: runbook
  author: Médéric HURIER (Fmind)
  source: github.com/fmind/www
  created: "2026-08-02"
  updated: "2026-11-11"
---

# Release

Run only with explicit owner release authorization; deploy-only requests follow [README deployment](../../../README.md#deployment) without tagging.

1. **Inspect state**: verify `main`, upstream, working tree, accounts, and tags; never move an existing release tag.
1. **Reconcile infra**: apply any `infra/` changes via [infra](../infra/SKILL.md) first.
1. **Run local gates**: pass `mise run all` and `mise run check:links` without suppressing warnings, plus relevant browser/Lighthouse checks.
1. **Commit and derive version**: commit reviewed code with Conventional Commits; use the owner's version or `mise exec -- git-cliff --config ~/.config/git-cliff/cliff.toml --unreleased --bumped-version`.
1. **Update release metadata**: bump `pyproject.toml` + `uv.lock` (`uv version <version>`) and `server.json`; prepend `CHANGELOG.md` once via `mise exec -- git-cliff --config ~/.config/git-cliff/cliff.toml --unreleased --tag v<version> --prepend CHANGELOG.md` (UTC date; replace only the new section on retry—never regenerate the whole file with `-o CHANGELOG.md`, which restores redacted historical subjects).
1. **Push and watch CI**: pass `mise run all`, commit `chore(release): vX.Y.Z`, push `main`, and watch `gh run list --workflow deploy.yml --commit <sha>` + `gh run watch <run-id> --exit-status` (rerun `--failed` only after transient GitHub 5xx download errors; watch the newest commit if superseded).
1. **Review logs**: CI runs image smoke and `test:deployed`; inspect Cloud Run error logs separately with the owner identity.
1. **Qualify live production**: probe apex DNS/TLS/redirect, `/agents`, `/llms.txt`, `/sitemap.xml`, feeds, and archive indexes, then dispatch `gh workflow run quality.yml -f target=production` ([README](../../../README.md#tasks)); any failure blocks tagging—fix forward on a new commit.
1. **Tag and publish GitHub release**: push an annotated tag without `--force`, run `gh release create v<version> --verify-tag --notes-file <temp-file>`, verify target, and delete `<temp-file>`.
1. **Publish to MCP Registry**: run `mise install --locked github:modelcontextprotocol/registry`, `mise exec -- mcp-publisher validate server.json`, `MCP_GITHUB_TOKEN="$(gh auth token)" mise exec -- mcp-publisher login github` (`fmind` account), and `mise exec -- mcp-publisher publish server.json` (never pass tokens in args or edit token files). Confirm the [latest registry entry](https://registry.modelcontextprotocol.io/v0.1/servers/io.github.fmind%2Fportfolio/versions/latest) and skill index digest match live output.

CI never auto-rolls back after promotion: roll back via `mise run deploy <digest-ref> <commit-sha>` + `test:deployed`, or if a newly published advisory blocks the prior digest's scan, run `gcloud run services update-traffic www-fmind-dev --project www-fmind-dev --region europe-west1 --to-revisions <revision>=100` and ship a patched release.
