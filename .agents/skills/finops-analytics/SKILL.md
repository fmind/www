---
name: finops-analytics
description: Report www.fmind.dev GCP costs, budgets, trends, and optimizations from billing exports and live config.
license: MIT
metadata:
  kind: task
  author: Médéric HURIER (Fmind)
  source: github.com/fmind/www
  created: "2026-09-19"
  updated: "2026-11-11"
---

# FinOps Analytics

Report on project `www-fmind-dev` (`europe-west1`, Cloud Run `www-fmind-dev`), comparing the last 7 complete UTC days against the prior 7 plus month-to-date separately. Keep billing data, account IDs, credentials, and reports out of Git; reply in chat unless a private path is requested.

## Collect evidence

1. **Pin identity and project**: resolve active `gcloud` configuration/account/overrides; pin `--configuration`, `--account`, `--project=www-fmind-dev`, and `--billing-project=www-fmind-dev`, keep tokens in memory, and never switch identities or widen IAM.
1. **Check billing and budgets**: run `gcloud billing projects describe www-fmind-dev` and paginate linked budgets (filters, period, currency, credits, actual/forecast thresholds, recipients). Account-wide budgets span other projects; thresholds are neither spend nor hard caps.
1. **Inspect billing export**: check `www-fmind-dev.billing_export` (EU, `infra/billing.tf`) for Google-created `gcp_billing_export_v1_…`; never create it manually. If absent, check Console → Billing → Billing export (Standard usage cost; initial backfill takes up to 5 days) and reuse any existing account export. Without export data, state the gap or use an owner-supplied project-filtered CSV—never infer spend from budgets or missing rows.
1. **Bound BigQuery queries**: verify schema/location, filter `project.id = 'www-fmind-dev'`, bound usage dates and the partition column (through report date to capture late arrivals/backfill), dry-run first, and enforce `maximumBytesBilled = 104857600` (100 MiB). Stop if exceeded rather than splitting queries, raising the cap, or adding reservations.
1. **Read service config**: inspect Cloud Run, Artifact Registry cleanup/storage, BigQuery/log retention, and Monitoring aggregates without enabling APIs. Route changes through [infra](../infra/SKILL.md) under owner authorization.

## Analyze and report

- **Lead with measured net cost**: state net cost and delta (or unavailability), source, currency, windows, latest export timestamp, gaps, and lag. Break down by day and service/SKU (absolute + `%`), separating usage-date spend from invoice-month reconciliation and unallocated tax/adjustments.
- **Aggregate credits per row**: compute `cost + SUM(credits.amount)` per billing row before summing across rows so `UNNEST` never multiplies `cost`; use decimal math, never mix currencies or standard/detailed tables, never treat missing days as zero, and label forecasts as estimates with method/limits.
- **Recommend ≤3 actions**: give evidence, expected monthly impact, trade-offs, and next step. Check registry cleanup before proposing deletions, preserve recovery/state history, and suggest commitments or always-on instances only with sustained demand evidence and owner authority.
- **Label cost per pageview**: pair with [website-analytics](../website-analytics/SKILL.md) only on matching windows (pageviews exclude API/MCP/static traffic), and claim realized savings only from comparable before/after billing rows.

Sources: [Billing API](https://docs.cloud.google.com/billing/docs/reference/rest), [budgets](https://docs.cloud.google.com/billing/docs/how-to/budgets), [billing exports](https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery), [standard schema](https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery-tables/standard-usage).
