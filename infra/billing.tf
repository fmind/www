# https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery-setup
# OpenTofu owns the destination; activate only Standard usage cost in Billing
# > Billing export. Google owns the export table and its evolving schema.
resource "google_bigquery_dataset" "billing" {
  project                    = var.project_id
  dataset_id                 = "billing_export"
  friendly_name              = "Cloud Billing export"
  description                = "Account-wide standard usage costs; filter project.id for website reports"
  location                   = "EU"
  delete_contents_on_destroy = false

  # Leave expiration unset: deleted billing history cannot be backfilled.
  # Access is deliberately narrower than the default project reader/editor ACL.
  access {
    role          = "OWNER"
    special_group = "projectOwners"
  }

  # Google grants this dataset-scoped role when activating the export.
  # Declare it here so subsequent applies preserve the export writer.
  access {
    role          = "OWNER"
    user_by_email = "billing-export-bigquery@system.gserviceaccount.com"
  }

  labels = {
    purpose = "finops"
  }

  lifecycle {
    prevent_destroy = true
  }

  depends_on = [time_sleep.wait_for_apis]
}

data "google_project" "current" {}

# The 5-instance cap bounds compute, not logging or BigQuery ingestion under
# abusive traffic. Alert on gross cost so expiring credits cannot hide growth.
# Budgets notify only; they never stop the service.
resource "google_billing_budget" "website" {
  provider        = google.quota
  billing_account = var.billing_account
  display_name    = "${var.project_id} gross (EUR${var.monthly_budget_eur})"

  budget_filter {
    projects               = [for number in concat([data.google_project.current.number], var.budget_shared_project_numbers) : "projects/${number}"]
    calendar_period        = "MONTH"
    credit_types_treatment = "EXCLUDE_ALL_CREDITS"
  }

  amount {
    specified_amount {
      currency_code = "EUR"
      units         = tostring(var.monthly_budget_eur)
      nanos         = 0
    }
  }

  threshold_rules {
    threshold_percent = 0.5
  }
  threshold_rules {
    threshold_percent = 0.9
  }
  threshold_rules {
    threshold_percent = 1.0
  }
  threshold_rules {
    threshold_percent = 1.0
    spend_basis       = "FORECASTED_SPEND"
  }

  # Billing administrators keep the default email; the alert channel adds the owner.
  all_updates_rule {
    monitoring_notification_channels = [google_monitoring_notification_channel.email.id]
  }

  depends_on = [
    google_project_service.billingbudgets,
    google_project_service.cloudbilling,
  ]
}
