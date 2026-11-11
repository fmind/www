# Service accounts and project-level IAM bindings for the run-time identity.

# Service Account for Cloud Run.
resource "google_service_account" "cloudrun_sa" {
  account_id   = "${var.service_name}-run"
  display_name = "Cloud Run Service Account for ${var.service_name}"
  depends_on   = [time_sleep.wait_for_apis]
}

# No project roles: the runtime identity writes only stdout/stderr logs and holds no Cloud API permissions.
