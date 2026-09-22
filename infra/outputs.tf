# Terraform outputs for resource access and verification.

output "analytics_dataset_id" {
  description = "The BigQuery dataset receiving privacy-preserving pageview logs"
  value       = google_bigquery_dataset.analytics.dataset_id
}

output "apex_dns_records" {
  description = "Records to publish at the DNS host so the apex reaches Cloud Run"
  value       = try(google_cloud_run_domain_mapping.apex.status[0].resource_records, [])
}

output "github_actions_service_account_email" {
  description = "The service account email for GitHub Actions"
  value       = google_service_account.github_actions_sa.email
}

output "repository_url" {
  description = "The URL of the Artifact Registry repository"
  value       = "${var.region}-docker.pkg.dev/${var.project_id}/${var.repository_id}"
}

output "service_url" {
  description = "The URL of the deployed Cloud Run service"
  value       = google_cloud_run_v2_service.web.uri
}

output "wif_provider_name" {
  description = "The Workload Identity Provider name for GitHub Actions"
  value       = google_iam_workload_identity_pool_provider.github_provider.name
}
