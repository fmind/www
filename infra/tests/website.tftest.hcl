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
  mock_resource "google_iam_workload_identity_pool" {
    defaults = {
      name = "projects/997496187785/locations/global/workloadIdentityPools/github-actions-pool"
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
      google_cloud_run_v2_service.web.template[0].containers[0].startup_probe[0].failure_threshold *
      google_cloud_run_v2_service.web.template[0].containers[0].startup_probe[0].period_seconds >= 60 &&
      google_cloud_run_v2_service.web.template[0].containers[0].startup_probe[0].http_get[0].path == "/health"
    )
    error_message = "Cold starts need at least a 60-second HTTP readiness budget without raising minimum instances."
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

  assert {
    condition = (
      google_bigquery_dataset.billing.location == "EU" &&
      !google_bigquery_dataset.billing.delete_contents_on_destroy &&
      google_bigquery_dataset.billing.default_table_expiration_ms == null &&
      google_bigquery_dataset.billing.default_partition_expiration_ms == null
    )
    error_message = "Billing history must stay in the EU without automatic expiration or destructive cleanup."
  }

  assert {
    condition = (
      length(google_bigquery_dataset.billing.access) == 2 &&
      alltrue([for entry in google_bigquery_dataset.billing.access :
        entry.role == "OWNER" && (
          entry.special_group == "projectOwners" ||
          entry.user_by_email == "billing-export-bigquery@system.gserviceaccount.com"
        )
      ])
    )
    error_message = "Only project owners and the Google billing exporter may receive dataset access."
  }
}

run "keyless_ci_identity_contract" {
  command = plan

  assert {
    condition = (
      google_iam_workload_identity_pool_provider.github_provider.attribute_mapping["attribute.workflow_ref"] == "assertion.workflow_ref" &&
      !contains(keys(google_iam_workload_identity_pool_provider.github_provider.attribute_mapping), "attribute.actor") &&
      !contains(keys(google_iam_workload_identity_pool_provider.github_provider.attribute_mapping), "attribute.ref")
    )
    error_message = "The provider must map the signed workflow_ref claim and no unused actor/ref attributes."
  }

  assert {
    condition = google_iam_workload_identity_pool_provider.github_provider.attribute_condition == join(" && ", [
      "assertion.repository == 'fmind/www'",
      "assertion.repository_id == '1261133438'",
      "assertion.repository_owner_id == '3929438'",
      "assertion.ref == 'refs/heads/main'",
      "(assertion.workflow_ref == 'fmind/www/.github/workflows/deploy.yml@refs/heads/main' || assertion.workflow_ref == 'fmind/www/.github/workflows/security.yml@refs/heads/main')",
    ])
    error_message = "Federation must require main, numeric repository/owner IDs, and one of the two federating workflows."
  }

  assert {
    condition = (
      google_service_account_iam_member.wif_impersonate.role == "roles/iam.workloadIdentityUser" &&
      google_service_account_iam_member.wif_impersonate.member == "principalSet://iam.googleapis.com/projects/997496187785/locations/global/workloadIdentityPools/github-actions-pool/attribute.workflow_ref/fmind/www/.github/workflows/deploy.yml@refs/heads/main"
    )
    error_message = "Only the main-branch deploy workflow may impersonate the deployer."
  }

  assert {
    condition = (
      google_service_account_iam_member.security_wif_impersonate.role == "roles/iam.workloadIdentityUser" &&
      google_service_account_iam_member.security_wif_impersonate.member == "principalSet://iam.googleapis.com/projects/997496187785/locations/global/workloadIdentityPools/github-actions-pool/attribute.workflow_ref/fmind/www/.github/workflows/security.yml@refs/heads/main"
    )
    error_message = "Only the main-branch security workflow may impersonate the read-only scanner."
  }
}

run "registry_rollback_retention_contract" {
  command = plan

  assert {
    condition = (
      !google_artifact_registry_repository.repo.cleanup_policy_dry_run &&
      anytrue([for policy in google_artifact_registry_repository.repo.cleanup_policies :
        policy.action == "KEEP" && try(policy.most_recent_versions[0].keep_count, 0) >= 30
      ])
    )
    error_message = "Registry cleanup must keep at least 30 recent versions so failed pushes cannot evict the rollback digest."
  }
}

run "custom_domain_contract" {
  command = plan

  assert {
    condition = (
      google_cloud_run_domain_mapping.apex.name == "fmind.dev" &&
      google_cloud_run_domain_mapping.www.name == "www.fmind.dev" &&
      google_cloud_run_domain_mapping.apex.spec[0].route_name == google_cloud_run_v2_service.web.name &&
      google_cloud_run_domain_mapping.www.spec[0].route_name == google_cloud_run_v2_service.web.name
    )
    error_message = "Both the apex and www hosts must route to the website service, which redirects the apex to www."
  }
}
