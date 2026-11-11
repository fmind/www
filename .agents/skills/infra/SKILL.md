---
name: infra
description: Change www.fmind.dev GCP resources under infra/ with OpenTofu while preserving state, cost, and WIF gates.
license: MIT
metadata:
  kind: runbook
  author: Médéric HURIER (Fmind)
  source: github.com/fmind/www
  created: "2026-08-07"
  updated: "2026-11-11"
---

# Infrastructure

`infra/` owns Cloud Run, custom domain mappings, Artifact Registry, keyless CI identities, monitoring, billing budget/export, and aggregate analytics (`gs://www-fmind-dev-tfstate/infra/state`; bootstrap bucket and the dedicated `fmind.dev` Cloud DNS zone live outside this repository). CI owns the serving image and traffic; OpenTofu ignores both. Keep resource addresses stable.

1. **Check capacity invariants**: preserve scale-to-zero and limits in [README](../../../README.md#deployment) (enforced by `infra/tests/website.tftest.hcl`) unless the owner authorizes changes.
1. **Run local checks**: pass `mise run all` (runs backend-free `check:tofu` in `tmp/tofu-check` with `tflint` and mocked plan tests; needs no cloud credentials).
1. **Pin live identity and billing**: verify the active account and pin `www-fmind-dev`, `europe-west1`, and quota project. Export `TF_VAR_billing_account` from `gcloud billing projects describe www-fmind-dev` (and preserve `TF_VAR_budget_shared_project_numbers` in `mise.local.toml` for companion projects sharing the budget); never commit or print them.
1. **Review a saved plan**: write the plan to an OS temp directory and inspect every action. Provider bumps require a no-op or explained plan; stop on unexpected replacement, deletion, IAM expansion, or spend.
1. **Resolve CI revision conflicts**: if a template change hits `409 Revision named ... with different configuration already exists`, temporarily drop `template[0].revision` from `ignore_changes`, verify the saved plan shows only the intended diff plus `revision -> null`, apply it, restore `ignore_changes`, and verify a no-op plan.
1. **Apply and verify**: apply only the reviewed plan within owner authorization, then read back state, readiness, traffic, scaling, IAM, and logs, and delete temp plan files.

```bash
tofu -chdir=infra init -input=false
tofu -chdir=infra plan -input=false -out=/tmp/www-infra.tfplan
tofu -chdir=infra show /tmp/www-infra.tfplan
tofu -chdir=infra apply /tmp/www-infra.tfplan
```

See [SECURITY.md](../../../SECURITY.md#data-and-recovery) for state-bucket recovery checks and WIF trust rules. Each SA trusts one workflow via `attribute.workflow_ref` (`deploy.yml` or `security.yml`); apply WIF updates before renaming workflows while no run is active, and never create SA keys. Template applies create no-traffic revisions until the next CI deploy promotes a verified image; registry cleanup retains ≥30 versions and 30 days for rollback. Refs: [OpenTofu CLI](https://opentofu.org/docs/cli/), [Cloud Run scaling](https://docs.cloud.google.com/run/docs/configuring/min-instances).
