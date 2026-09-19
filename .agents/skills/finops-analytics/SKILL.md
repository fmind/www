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

1. Resolve the existing gcloud configuration/account and credential overrides. Pin `--configuration`, `--account`, `--project=www-fmind-dev`, and `--billing-project=www-fmind-dev` on calls; keep tokens in memory. Do not switch identities or broaden IAM to bypass a failure.
1. Discover linkage with `gcloud billing projects describe www-fmind-dev`; inspect the linked account and its budgets. Check project/service filters, period, currency, credits, actual/forecast thresholds, and recipients. Exhaust pagination. Account-wide budgets include other projects; alert thresholds are neither actual spend nor hard caps.
1. Inspect `www-fmind-dev.billing_export` (EU), managed by `infra/billing.tf`, for the Google-created `gcp_billing_export_v1_…` table; never create the table yourself. Dataset existence alone does not prove export activation. If absent, check Cloud Console → Billing → Billing export: only Standard usage cost should target this dataset. Reuse an existing account export rather than redirecting it and losing continuity. Billing and Budget APIs provide configuration, not a spending ledger. Without an export, report that limitation or use an owner-provided, project-filtered Billing Reports CSV; never infer costs from budgets or missing rows.
1. For an authorized BigQuery query, inspect the schema and location, filter `project.id = 'www-fmind-dev'`, bound usage dates and the actual partition field, dry-run first, and set `maximumBytesBilled = 104857600` (100 MiB). Requested reports may use this per-query allowance; stop if the estimate exceeds it rather than splitting queries or raising the cap. Queries are on demand, without reservations or schedules; the cap does not guarantee free execution. Do not provision resources or broaden this allowance just to finish a report.
1. Read Cloud Run settings, registry cleanup/storage, and BigQuery/log retention. Use accessible Monitoring aggregates without enabling extra APIs. Changes go through the [infra skill](../infra/SKILL.md) within owner authorization.

## Analyze and report

Lead with measured net cost and its change, or explicitly state that spend data is unavailable. Include source, currency, exact windows, latest export timestamp, gaps, and billing lag. Group by day and service/SKU; flag absolute changes alongside percentages. Keep usage-date analysis separate from invoice-month reconciliation and explain unallocated tax/adjustments. Confirm the partition field from table metadata: ingestion/export-time bounds must include late arrivals and backfill through the report run date, not stop at the usage-window end.

For standard/detailed exports, net cost is cost plus signed credit amounts. Aggregate credits per billing row before summing to avoid multiplying cost through `UNNEST`; use decimal arithmetic. Never mix currencies, double-count standard and detailed exports, or treat a missing day as proven zero. Label forecasts as estimates and state their method and coverage limits.

Give up to three prioritized recommendations with evidence, expected monthly benefit when defensible, trade-offs, and the next action. Preserve service/revision **minimum instances 0**, maximum 5, and request-based CPU. Check registry cleanup before proposing deletion, and retain recovery/state history. Recommend commitments or always-on capacity only with sustained usage evidence and explicit owner authority. An account-wide alert can justify proposing a project-specific budget, not inventing its amount.

Use [website-analytics](../website-analytics/SKILL.md) only for a clearly labelled cost-per-pageview comparison with matching windows; pageviews exclude API/MCP/static requests and are not total requests or visitors. Do not claim realized savings without comparable before/after billing data.

Sources: [Billing API](https://docs.cloud.google.com/billing/docs/reference/rest), [budgets](https://docs.cloud.google.com/billing/docs/how-to/budgets), [billing exports](https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery), and [standard export schema](https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery-tables/standard-usage). Recheck current documentation for version-sensitive behavior.
