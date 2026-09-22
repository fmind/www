---
name: infra
description: Change www.fmind.dev cloud resources with OpenTofu while preserving state, cost, identity, and apply gates. Use for changes under infra/.
license: MIT
metadata:
  author: Médéric HURIER (Fmind)
---

# Infrastructure

The flat `infra/` root owns Cloud Run, Artifact Registry, keyless CI identities, monitoring, and aggregate analytics. CI owns the image digest; OpenTofu ignores image changes. Keep existing resource identifiers stable.

1. Inspect the source diff and runtime contract. Keep service and revision `min_instance_count = 0`, service/revision maximum 5, request-based CPU, and current memory/concurrency unless the owner authorizes a capacity change.
1. Run `mise run format`, `mise run check`, and `mise run check:tofu`. The last task uses a separate backend-free data directory and mocked plan tests; it needs provider downloads but no cloud credentials.
1. For an authorized live review, verify the account and pin project `www-fmind-dev`, region `europe-west1`, and quota project. Do not start interactive login if existing credentials work.
1. Initialize OpenTofu, save a plan in an OS temporary directory, and inspect every action. Provider upgrades require a no-op or fully explained live plan. Stop on unexpected replacement, deletion, IAM expansion, or added spend.
1. Apply only the reviewed saved plan within existing owner authorization. Read back state, readiness, traffic, scaling, IAM, and relevant logs; an accepted apply alone does not prove application delivery.

```bash
tofu -chdir=infra init -input=false
tofu -chdir=infra plan -input=false -out=/absolute/temporary/plan.tfplan
tofu -chdir=infra show /absolute/temporary/plan.tfplan
tofu -chdir=infra apply /absolute/temporary/plan.tfplan
```

State uses `gs://www-fmind-dev-tfstate/infra/state`. The bootstrap bucket is outside this state: verify object versioning and enforced public-access prevention after recovery or migration. Never commit state, plans, credentials, or tfvars. Remove task-owned scratch files after verification.

Workload Identity Federation is restricted to `main`, numeric GitHub owner/repository IDs, and the `deploy.yml`/`security.yml` workflow files; each service account trusts exactly one of them through `attribute.workflow_ref`. Renaming either workflow or adding a federating one needs a reviewed apply first. Apply identity changes when no deploy or security run is in flight. The scheduled scanner has read-only service/registry access; never create service-account keys.

CI pins traffic to the verified revision, and OpenTofu keeps that traffic. A service-template apply therefore creates a revision without traffic; it serves after the next deploy promotes a verified revision. Registry cleanup keeps the 30 most recent versions (about ten pushes) so the rollback digest survives failed candidates. Keep analytics cookieless with 180-day partition expiry and `country` empty until a non-bypassable trusted geography source exists. Use [website-analytics](../website-analytics/SKILL.md) for reports.

See [OpenTofu](https://opentofu.org/docs/cli/) and [Cloud Run scaling](https://docs.cloud.google.com/run/docs/configuring/min-instances) for current provider/platform behavior.
