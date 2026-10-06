# Privacy-preserving pageview analytics. The application emits one structured
# record per HTML GET response; this sink routes only those records to BigQuery.

locals {
  analytics_event = "analytics_pageview"
  analytics_filter = join(" AND ", [
    "resource.type=\"cloud_run_revision\"",
    "resource.labels.service_name=\"${var.service_name}\"",
    "jsonPayload.msg=\"${local.analytics_event}\"",
  ])
}

# Some Google APIs do not provision their managed service identity when the API
# is enabled. Create it explicitly so the first sink apply can grant access.
resource "google_project_service_identity" "logging" {
  provider = google-beta
  project  = var.project_id
  service  = google_project_service.logging.service

  depends_on = [time_sleep.wait_for_apis]
}

resource "google_bigquery_dataset" "analytics" {
  project                         = var.project_id
  dataset_id                      = "website_analytics"
  friendly_name                   = "Website analytics"
  description                     = "Cookieless, aggregate HTML pageview events for www.fmind.dev"
  location                        = var.analytics_location
  default_partition_expiration_ms = 180 * 24 * 60 * 60 * 1000
  delete_contents_on_destroy      = false

  labels = {
    privacy = "cookieless"
    service = var.service_name
  }

  depends_on = [time_sleep.wait_for_apis]
}

resource "google_logging_project_sink" "analytics" {
  project                = var.project_id
  name                   = "${var.service_name}-analytics"
  description            = "Route privacy-preserving HTML pageview events to BigQuery"
  destination            = "bigquery.googleapis.com/projects/${var.project_id}/datasets/${google_bigquery_dataset.analytics.dataset_id}"
  filter                 = local.analytics_filter
  unique_writer_identity = true
  deletion_policy        = "PREVENT"

  # Logging creates the table from the first matching record. This option makes
  # it ingestion-time partitioned; the dataset default expires each partition
  # after 180 days so dashboard queries and storage remain bounded.
  bigquery_options {
    use_partitioned_tables = true
  }

  depends_on = [google_project_service_identity.logging]
}

resource "google_bigquery_dataset_iam_member" "analytics_writer" {
  project    = var.project_id
  dataset_id = google_bigquery_dataset.analytics.dataset_id
  role       = "roles/bigquery.dataEditor"
  member     = google_logging_project_sink.analytics.writer_identity
}

# Project exclusions are attached to the automatically managed _Default sink.
# The dedicated sink above still receives the record, while Cloud Logging does
# not retain a second copy after routing it to BigQuery.
resource "google_logging_project_exclusion" "analytics_default" {
  project     = var.project_id
  name        = "${var.service_name}-analytics-routed"
  description = "Avoid duplicate retention of pageview events in the _Default log bucket"
  filter      = local.analytics_filter

  # Do not stop _Default retention until the dedicated writer can persist the
  # event, avoiding a loss window during the first infrastructure apply.
  depends_on = [google_bigquery_dataset_iam_member.analytics_writer]
}
