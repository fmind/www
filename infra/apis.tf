# Google Cloud service APIs activation and dependencies.
#
# The application image contains only public assets and holds no secrets, so Secret
# Manager is not enabled.

resource "google_project_service" "artifactregistry" {
  project            = var.project_id
  service            = "artifactregistry.googleapis.com"
  disable_on_destroy = false
}

resource "google_project_service" "bigquery" {
  project            = var.project_id
  service            = "bigquery.googleapis.com"
  disable_on_destroy = false
}

resource "google_project_service" "cloudtrace" {
  project            = var.project_id
  service            = "cloudtrace.googleapis.com"
  disable_on_destroy = false
}

resource "google_project_service" "iam" {
  project            = var.project_id
  service            = "iam.googleapis.com"
  disable_on_destroy = false
}

resource "google_project_service" "iamcredentials" {
  project            = var.project_id
  service            = "iamcredentials.googleapis.com"
  disable_on_destroy = false
}

resource "google_project_service" "logging" {
  project            = var.project_id
  service            = "logging.googleapis.com"
  disable_on_destroy = false
}

resource "google_project_service" "monitoring" {
  project            = var.project_id
  service            = "monitoring.googleapis.com"
  disable_on_destroy = false
}

resource "google_project_service" "run" {
  project            = var.project_id
  service            = "run.googleapis.com"
  disable_on_destroy = false
}

# Wait for APIs to propagate before dependent resources are created.
resource "time_sleep" "wait_for_apis" {
  create_duration = "30s"

  depends_on = [
    google_project_service.artifactregistry,
    google_project_service.bigquery,
    google_project_service.cloudtrace,
    google_project_service.iam,
    google_project_service.iamcredentials,
    google_project_service.logging,
    google_project_service.monitoring,
    google_project_service.run,
  ]
}
