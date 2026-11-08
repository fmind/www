---
name: finops-analytics
description: Report www.fmind.dev cloud costs, budget coverage, trends, and evidence-backed optimization opportunities using billing exports and live GCP configuration.
license: MIT
metadata:
  author: Médéric HURIER (Fmind)
---

# FinOps Analytics

Report on project `www-fmind-dev`, Cloud Run service `www-fmind-dev`, region `europe-west1`. Default to the last seven complete UTC days versus the preceding seven; show month-to-date separately. Keep financial data, billing account IDs, credentials, and reports out of Git. Return findings in chat unless a private destination is requested.

## Collect evidence

1. **Pin identity and project**: resolve the active gcloud configuration, account, and credential overrides; pin `--configuration`, `--account`, `--project=www-fmind-dev`, and `--billing-project=www-fmind-dev`, keep tokens in memory, and never switch identities or broaden IAM.
1. **Check billing and budgets**: run `gcloud billing projects describe www-fmind-dev`; inspect the linked account and its budgets (project/service filters, period, currency, credits, actual/forecast thresholds, recipients) with full pagination. Account-wide budgets include other projects; alert thresholds are neither actual spend nor hard caps.
1. **Inspect the billing export**: check `www-fmind-dev.billing_export` (EU), managed by `infra/billing.tf`, for the Google-created `gcp_billing_export_v1_…` table; never create the table yourself. Dataset existence alone does not prove export activation. If absent, check Cloud Console → Billing → Billing export (only Standard usage cost from project `www-fmind-dev`; initial backfill can take five days) and reuse any existing account export rather than redirecting it. Without an export, report that limitation or use an owner-provided, project-filtered Billing Reports CSV; never infer costs from budgets or missing rows.
1. **Bound BigQuery queries**: inspect the schema and location, filter `project.id = 'www-fmind-dev'`, bound usage dates and the actual partition field, dry-run first, and set `maximumBytesBilled = 104857600` (100 MiB). Stop if the estimate exceeds this on-demand cap rather than splitting queries, raising the cap, or provisioning reservations/schedules; the cap does not guarantee free execution.
1. **Read service settings**: inspect Cloud Run settings, registry cleanup/storage, BigQuery/log retention, and accessible Monitoring aggregates without enabling extra APIs. Changes go through the [infra skill](../infra/SKILL.md) within owner authorization.

## Analyze and report

- **Lead with measured net cost**: report net cost and its change (or state that spend data is unavailable) with source, currency, exact windows, latest export timestamp, gaps, and billing lag. Group by day and service/SKU with absolute and percentage changes; separate usage-date analysis from invoice-month reconciliation and unallocated tax/adjustments. Bound the table's partition field through the report run date to include late arrivals and backfill.
- **Aggregate credits per row**: net cost is cost plus signed credit amounts. Aggregate credits per billing row before summing to avoid multiplying cost through `UNNEST`; use decimal arithmetic. Never mix currencies, double-count standard and detailed exports, or treat a missing day as proven zero. Label forecasts as estimates with their method and coverage limits.
- **Recommend up to three actions**: include evidence, expected monthly benefit when defensible, trade-offs, and the next action. Check registry cleanup before proposing deletion, retain recovery/state history, and recommend commitments or always-on capacity only with sustained usage evidence and explicit owner authority. An account-wide alert can justify proposing a project-specific budget, not inventing its amount.
- **Label cost per pageview**: use [website-analytics](../website-analytics/SKILL.md) only with matching windows; pageviews exclude API/MCP/static requests and are not total requests or visitors. Do not claim realized savings without comparable before/after billing data.

Sources: [Billing API](https://docs.cloud.google.com/billing/docs/reference/rest), [budgets](https://docs.cloud.google.com/billing/docs/how-to/budgets), [billing exports](https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery), and [standard export schema](https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery-tables/standard-usage). Recheck current documentation for version-sensitive behavior.
