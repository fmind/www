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

  depends_on = [google_project_service.bigquery]
}
