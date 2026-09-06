---
name: infra
description: Change www.fmind.dev cloud resources with OpenTofu while preserving state, cost, identity, and apply gates. Use for changes under infra/.
license: MIT
metadata:
  author: Médéric HURIER (Fmind)
---

# Change the Infrastructure

Change the flat `infra/` OpenTofu root while preserving live-state, cost, identity, deployment, and privacy boundaries.

The module owns Cloud Run, Artifact Registry, runtime and CI identities, Workload Identity Federation, alerting, and aggregate BigQuery analytics. State is versioned in `www-fmind-dev-tfstate` under `infra/state`. Local validation is not authority to plan against live state or apply; obtain explicit owner approval before either consequential step.

## Workflow

1. Inspect the current application/runtime contract and the complete proposed OpenTofu diff. Keep existing GCP identifiers stable unless the task explicitly authorizes a resource migration.
1. Validate source without cloud credentials:

   ```bash
   mise run format
   mise run check          # includes Trivy configuration scanning
   mise run check:tofu     # backend-free init, validate, and tflint
   ```

   `check:tofu` downloads provider schemas, so it is network-dependent and separate from `check`. It uses a scratch `TF_DATA_DIR` and must not read a prior real backend cache.

1. After explicit approval to read live state, authenticate to the intended account and pin the project context:

   ```bash
   gcloud auth application-default login
   gcloud config get-value account
   gcloud config get-value project
   ```

1. Initialize, save a plan, and read every action:

   ```bash
   tofu -chdir=infra init
   tofu -chdir=infra plan -out=../tmp/plan.tfplan
   tofu -chdir=infra show ../tmp/plan.tfplan
   ```

1. Stop on replacement, deletion, unexplained drift, provider migration, or cost-sensitive expansion. Apply only the exact reviewed plan and only after explicit owner authorization:

   ```bash
   tofu -chdir=infra apply ../tmp/plan.tfplan
   ```

1. Verify the resulting state, Cloud Run readiness/traffic, IAM boundary, and relevant logs. An accepted apply is not application release proof.

## Division of Ownership

- CI owns the deployed immutable image digest on `main` pushes.
- OpenTofu owns CPU, memory, scaling, environment, probes, IAM, routing, monitoring, and analytics resources.
- `infra/cloud_run.tf` ignores image changes, so a plan must not roll back CI's deployed digest.
- The manual `mise run deploy <digest-ref>` task changes only the image and does not authorize infrastructure drift.

## Querying Analytics

The first pageview creates `www-fmind-dev.website_analytics.run_googleapis_com_stderr`, partitioned by `timestamp` with a 180-day expiry. Always bound `timestamp` and exclude bots:

```sql
SELECT jsonPayload.utm_source, jsonPayload.utm_medium, jsonPayload.path, COUNT(*) AS views
FROM `www-fmind-dev.website_analytics.run_googleapis_com_stderr`
WHERE timestamp >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 30 DAY)
  AND jsonPayload.bot = false
GROUP BY 1, 2, 3
ORDER BY views DESC
```

Use `path`, `referer`, or `TIMESTAMP_TRUNC(timestamp, DAY)` for other aggregates. `src/www/middleware.py` defines the emitted field set; adding a dimension is a privacy decision. `country` remains empty until infrastructure establishes a non-bypassable, trusted geography boundary.

## Gotchas

- State stores attributes in plaintext. Never commit `*.tfstate*` or `*.tfvars`; keep state only in the versioned bucket.
- Google providers are pinned to `= 7.43.0`. Upgrade deliberately and require an empty or fully explained live plan after provider changes.
- A Cloud Run domain mapping does not authenticate geography headers. Keep `country` empty unless a non-bypassable managed edge overwrites one dedicated header and the application trusts only that header.
- CI remains keyless through branch-restricted Workload Identity Federation. Never create a service-account key.
- Never run `tofu destroy`, apply a speculative plan, or infer production authority from a green local or CI validation.

## Official Skills

- Use [terraform](~/.agents/skills/terraform/SKILL.md) for OpenTofu conventions.
- Use [gcloud](~/.agents/skills/gcloud/SKILL.md) for pinned-account Google Cloud operations.

## Documentation

- [OpenTofu CLI](https://opentofu.org/docs/cli/)
- [Cloud Run](https://cloud.google.com/run/docs)
