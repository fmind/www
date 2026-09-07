# Docs: https://cloud.google.com/iam/docs/workload-identity-federation-with-deployment-pipelines
# Keyless CI: Workload Identity Federation for GitHub Actions.
#
# GitHub's OIDC token impersonates a dedicated service account (no long-lived
# keys) that may push to Artifact Registry and deploy the Cloud Run service.

resource "google_service_account" "github_actions_sa" {
  account_id   = "github-actions"
  display_name = "GitHub Actions Deployment Service Account"
  depends_on   = [time_sleep.wait_for_apis]
}

# Push images to Artifact Registry.
resource "google_artifact_registry_repository_iam_member" "repo_writer" {
  location   = google_artifact_registry_repository.repo.location
  repository = google_artifact_registry_repository.repo.name
  role       = "roles/artifactregistry.writer"
  member     = "serviceAccount:${google_service_account.github_actions_sa.email}"
}

# Deploy new revisions of this one service. Binding roles/run.developer on the
# service instead of the project means CI cannot create, delete, or SSH into any
# other Cloud Run service, job, or worker pool here.
resource "google_cloud_run_v2_service_iam_member" "github_actions_run_developer" {
  location = google_cloud_run_v2_service.web.location
  name     = google_cloud_run_v2_service.web.name
  role     = "roles/run.developer"
  member   = "serviceAccount:${google_service_account.github_actions_sa.email}"
}

# Each deploy returns a long-running operation, and operations are project-scoped
# resources that a service-level binding cannot reach. roles/run.viewer is
# read-only, so it restores the polling permission (run.operations.get) without
# handing back any mutating access at the project level.
resource "google_project_iam_member" "github_actions_run_viewer" {
  project = var.project_id
  role    = "roles/run.viewer"
  member  = "serviceAccount:${google_service_account.github_actions_sa.email}"
}

# Act as the Cloud Run runtime service account when deploying.
resource "google_service_account_iam_member" "github_actions_act_as_run" {
  service_account_id = google_service_account.cloudrun_sa.name
  role               = "roles/iam.serviceAccountUser"
  member             = "serviceAccount:${google_service_account.github_actions_sa.email}"
}

# Workload Identity Pool for GitHub Actions.
resource "google_iam_workload_identity_pool" "github_pool" {
  workload_identity_pool_id = "github-actions-pool"
  display_name              = "GitHub Actions Pool"
  description               = "Identity pool for GitHub Actions CI/CD"
  depends_on                = [time_sleep.wait_for_apis]
}

# Workload Identity Pool Provider for GitHub OIDC.
resource "google_iam_workload_identity_pool_provider" "github_provider" {
  workload_identity_pool_id          = google_iam_workload_identity_pool.github_pool.workload_identity_pool_id
  workload_identity_pool_provider_id = "github-provider"
  display_name                       = "GitHub OIDC Provider"
  description                        = "OIDC identity provider for GitHub Actions"

  attribute_mapping = {
    "google.subject"                = "assertion.sub"
    "attribute.actor"               = "assertion.actor"
    "attribute.ref"                 = "assertion.ref"
    "attribute.repository"          = "assertion.repository"
    "attribute.repository_id"       = "assertion.repository_id"
    "attribute.repository_owner_id" = "assertion.repository_owner_id"
  }

  # Numeric IDs prevent a reused repository or owner name inheriting cloud access.
  attribute_condition = "assertion.repository == '${var.github_repository}' && assertion.repository_id == '${var.github_repository_numeric_id}' && assertion.repository_owner_id == '${var.github_owner_numeric_id}' && assertion.ref == 'refs/heads/main'"

  oidc {
    issuer_uri = "https://token.actions.githubusercontent.com"
  }
}

# Allow only this repository's workflows to impersonate the deployer SA.
resource "google_service_account_iam_member" "wif_impersonate" {
  service_account_id = google_service_account.github_actions_sa.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "principalSet://iam.googleapis.com/${google_iam_workload_identity_pool.github_pool.name}/attribute.repository/${var.github_repository}"
}

# Scheduled scans can read the serving revisions and pull images, never deploy.
resource "google_service_account" "github_security_sa" {
  account_id   = "github-security"
  display_name = "GitHub Security Read-Only Scanner"
  depends_on   = [time_sleep.wait_for_apis]
}

resource "google_artifact_registry_repository_iam_member" "security_repo_reader" {
  location   = google_artifact_registry_repository.repo.location
  repository = google_artifact_registry_repository.repo.name
  role       = "roles/artifactregistry.reader"
  member     = "serviceAccount:${google_service_account.github_security_sa.email}"
}

resource "google_cloud_run_v2_service_iam_member" "security_run_viewer" {
  location = google_cloud_run_v2_service.web.location
  name     = google_cloud_run_v2_service.web.name
  role     = "roles/run.viewer"
  member   = "serviceAccount:${google_service_account.github_security_sa.email}"
}

resource "google_service_account_iam_member" "security_wif_impersonate" {
  service_account_id = google_service_account.github_security_sa.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "principalSet://iam.googleapis.com/${google_iam_workload_identity_pool.github_pool.name}/attribute.repository_id/${var.github_repository_numeric_id}"
}
