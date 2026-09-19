---
name: release
description: Cut and verify a www.fmind.dev semver release from local gates through live Cloud Run proof. Use only when the owner explicitly authorizes release.
license: MIT
metadata:
  author: Médéric HURIER (Fmind)
---

# Release

Use only for an explicitly authorized release. Reuse existing authorization; a green gate alone never authorizes publication. A deploy-only request follows [README deployment](../../../README.md#deployment) without creating a tag.

1. Inspect `main`, upstream, staged and unstaged changes, accounts, and local/remote tags. Include only reviewed work; never move an existing release tag.
1. Reconcile any infrastructure changes through the [infra skill](../infra/SKILL.md) before application rollout. Preserve `min_instance_count = 0` at both service and revision levels.
1. Run `mise run all` and `mise run check:links`. Resolve failures and review warnings without suppressing them. Add `mise run check:tofu` for infrastructure changes, and browser/Lighthouse qualification appropriate to the changed pages.
1. Commit reviewed implementation paths with Conventional Commits. Use the owner's requested version; otherwise derive the next semver with `git-cliff --config ~/.config/git-cliff/cliff.toml --bumped-version`.
1. Set the same version in `pyproject.toml`, `uv.lock`, and `server.json` (`uv version <version>` updates the first two). Generate `CHANGELOG.md` with `git-cliff --config ~/.config/git-cliff/cliff.toml --tag v<version> -o CHANGELOG.md`.
1. Run `mise run all` on the final release candidate, inspect the diff, and commit the release metadata as `chore(release): vX.Y.Z`. Create an annotated tag and push `main` and that tag without force.
1. Generate release notes in an OS temporary file, publish with `gh release create ... --notes-file ...`, then remove the file. Bind workflow monitoring to `git rev-parse HEAD`: `gh run list --workflow deploy.yml --commit <sha>` and `gh run watch <run-id> --exit-status`.
1. Independently verify the ready Cloud Run revision, 100% traffic, image digest, release SHA, scale-to-zero, and recent error logs. CI must scan and smoke-test the pushed immutable digest before deployment.
1. Verify apex redirect, `/health`, `/api/profile`, `/agents`, MCP discovery, `/llms.txt`, sitemap, feed, and archive indexes. Run `BROWSER_BASE_URL=https://www.fmind.dev mise run test:browser` and the relevant `test:lighthouse -- --base-url https://www.fmind.dev --mode portfolio` matrix. Report exact outcomes and any external limits.

Keep the preceding qualified digest available for rollback through `mise run deploy <digest-ref>`. Local archive proof, exact-commit CI, publication, and live runtime are separate evidence. MCP Registry publication (`mcp-publisher publish`) remains a separate owner action.
