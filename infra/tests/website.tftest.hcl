# https://opentofu.org/docs/cli/commands/test/
mock_provider "google" {
  mock_resource "google_service_account" {
    defaults = {
      name  = "projects/www-fmind-dev/serviceAccounts/mock-account@www-fmind-dev.iam.gserviceaccount.com"
      email = "mock-account@www-fmind-dev.iam.gserviceaccount.com"
    }
  }
  mock_resource "google_logging_project_sink" {
    defaults = {
      writer_identity = "serviceAccount:mock-logging@www-fmind-dev.iam.gserviceaccount.com"
    }
  }
}
mock_provider "google-beta" {}
mock_provider "time" {}

run "website_cost_and_recovery_contract" {
  command = plan

  assert {
    condition = (
      google_cloud_run_v2_service.web.scaling[0].min_instance_count == 0 &&
      google_cloud_run_v2_service.web.template[0].scaling[0].min_instance_count == 0 &&
      google_cloud_run_v2_service.web.scaling[0].max_instance_count == 5 &&
      google_cloud_run_v2_service.web.template[0].scaling[0].max_instance_count == 5 &&
      google_cloud_run_v2_service.web.template[0].containers[0].resources[0].cpu_idle
    )
    error_message = "The website must scale to zero, use request-based CPU, and cap service/revision scaling at five."
  }

  assert {
    condition = (
      google_cloud_run_v2_service.web.deletion_protection &&
      !google_bigquery_dataset.analytics.delete_contents_on_destroy &&
      google_logging_project_sink.analytics.deletion_policy == "PREVENT"
    )
    error_message = "Service and analytics recovery protections must remain enabled."
  }

  assert {
    condition     = google_bigquery_dataset.analytics.default_partition_expiration_ms == 15552000000
    error_message = "Analytics partitions must expire after 180 days."
  }
}
