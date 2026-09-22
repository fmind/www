# Artifact Registry Docker repository with automated retention policies.

resource "google_artifact_registry_repository" "repo" {
  location      = var.region
  repository_id = var.repository_id
  description   = "Docker repository for the www portfolio application"
  format        = "DOCKER"

  cleanup_policy_dry_run = false

  # Every CI push, including candidates later rejected by scan or smoke tests,
  # stores an image index plus separate platform-image and attestation
  # versions. Thirty versions therefore retain roughly the last ten pushes, so
  # the preceding qualified rollback digest survives a run of failed pushes and
  # a quiet month. Worst case ~1.5 GiB at $0.10/GiB-month: cents per month.
  cleanup_policies {
    id     = "keep-recent-versions"
    action = "KEEP"
    most_recent_versions {
      keep_count = 30
    }
  }

  cleanup_policies {
    id     = "delete-old-images"
    action = "DELETE"
    condition {
      tag_state  = "ANY"
      older_than = "2592000s" # 30 days
    }
  }

  depends_on = [time_sleep.wait_for_apis]
}
