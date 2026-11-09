---
name: infra
description: Change www.fmind.dev cloud resources with OpenTofu while preserving state, cost, identity, and apply gates. Use for changes under infra/.
license: MIT
metadata:
  author: Médéric HURIER (Fmind)
---

# Infrastructure

The flat `infra/` root owns Cloud Run, Artifact Registry, keyless CI identities, monitoring, and aggregate analytics. CI owns the image digest; OpenTofu ignores image changes. Keep existing resource identifiers stable.

1. **Check capacity invariants**: inspect the source diff and runtime contract. Keep the capacity stated in [README](../../../README.md#deployment), which `infra/tests/website.tftest.hcl` enforces, unless the owner authorizes a capacity change.
1. **Run local checks**: run `mise run all` (formats first; includes `check:tofu`, which uses a separate backend-free data directory and mocked plan tests; needs provider downloads, no cloud credentials).
1. **Pin live identity and billing**: verify the account and pin project `www-fmind-dev`, region `europe-west1`, and quota project without starting interactive login if existing credentials work. Export `TF_VAR_billing_account` from `gcloud billing projects describe www-fmind-dev` for the project budget; never commit it or print it in reports.
1. **Review a saved plan**: initialize OpenTofu, save a plan in an OS temporary directory, and inspect every action. Provider upgrades require a no-op or fully explained live plan. Stop on unexpected replacement, deletion, IAM expansion, or added spend.
1. **Resolve CI revision conflicts**: a service-template change after a CI deploy fails with `409 Revision named ... with different configuration already exists` because OpenTofu resends the ignored CI revision name. Plan once with `template[0].revision` removed from `ignore_changes` (must show only the intended change and `revision -> null`), apply that saved plan, restore the file, and confirm a clean plan.
1. **Apply and verify delivery**: apply only the reviewed saved plan within existing owner authorization, then read back state, readiness, traffic, scaling, IAM, and relevant logs; an accepted apply alone does not prove application delivery.

```bash
tofu -chdir=infra init -input=false
tofu -chdir=infra plan -input=false -out=/absolute/temporary/plan.tfplan
tofu -chdir=infra show /absolute/temporary/plan.tfplan
tofu -chdir=infra apply /absolute/temporary/plan.tfplan
```

State uses `gs://www-fmind-dev-tfstate/infra/state`; the bootstrap bucket is outside this state. [SECURITY.md](../../../SECURITY.md#data-and-recovery) owns the bucket settings to verify after recovery or migration and the Workload Identity Federation trust rules. Never commit state, plans, credentials, or tfvars. Remove task-owned scratch files after verification.

Each service account trusts exactly one workflow file through `attribute.workflow_ref`: renaming `deploy.yml` or `security.yml`, or adding a federating workflow, needs a reviewed apply first, when no deploy or security run is in flight. Never create service-account keys.

CI pins traffic to the verified revision, so a service-template apply creates a revision without traffic that serves after the next deploy promotes a verified revision. Registry cleanup keeps at least the 30 most recent versions plus the last 30 days so the rollback digest survives failed candidates.

See [OpenTofu](https://opentofu.org/docs/cli/) and [Cloud Run scaling](https://docs.cloud.google.com/run/docs/configuring/min-instances) for current provider/platform behavior.
