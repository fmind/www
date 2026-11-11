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
mock_provider "google" {
  alias = "quota"
}
mock_provider "google-beta" {}
mock_provider "time" {}

variables {
  billing_account = "000000-AAAAAA-000000"
}

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

  # Distinct identities, so a binding granted to the wrong account fails below.
  override_resource {
    target = google_service_account.github_actions_sa
    values = {
      name  = "projects/www-fmind-dev/serviceAccounts/github-actions@www-fmind-dev.iam.gserviceaccount.com"
      email = "github-actions@www-fmind-dev.iam.gserviceaccount.com"
    }
  }
  override_resource {
    target = google_service_account.github_security_sa
    values = {
      name  = "projects/www-fmind-dev/serviceAccounts/github-security@www-fmind-dev.iam.gserviceaccount.com"
      email = "github-security@www-fmind-dev.iam.gserviceaccount.com"
    }
  }
  override_resource {
    target = google_service_account.cloudrun_sa
    values = {
      name  = "projects/www-fmind-dev/serviceAccounts/www-fmind-dev-run@www-fmind-dev.iam.gserviceaccount.com"
      email = "www-fmind-dev-run@www-fmind-dev.iam.gserviceaccount.com"
    }
  }

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
      "assertion.runner_environment == 'github-hosted'",
      "(assertion.workflow_ref == 'fmind/www/.github/workflows/deploy.yml@refs/heads/main' || assertion.workflow_ref == 'fmind/www/.github/workflows/security.yml@refs/heads/main')",
    ])
    error_message = "Federation must require main, numeric repository/owner IDs, GitHub-hosted runners, and one of the two federating workflows."
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

  # SECURITY.md keeps the deployer and scanner roles separate and least-privilege.
  assert {
    condition = (
      google_artifact_registry_repository_iam_member.repo_writer.role == "roles/artifactregistry.writer" &&
      google_artifact_registry_repository_iam_member.repo_writer.member == "serviceAccount:github-actions@www-fmind-dev.iam.gserviceaccount.com" &&
      google_cloud_run_v2_service_iam_member.github_actions_run_developer.role == "roles/run.developer" &&
      google_cloud_run_v2_service_iam_member.github_actions_run_developer.member == "serviceAccount:github-actions@www-fmind-dev.iam.gserviceaccount.com" &&
      google_project_iam_member.github_actions_run_viewer.role == "roles/run.viewer" &&
      google_project_iam_member.github_actions_run_viewer.member == "serviceAccount:github-actions@www-fmind-dev.iam.gserviceaccount.com" &&
      google_service_account_iam_member.github_actions_act_as_run.role == "roles/iam.serviceAccountUser" &&
      google_service_account_iam_member.github_actions_act_as_run.service_account_id == "projects/www-fmind-dev/serviceAccounts/www-fmind-dev-run@www-fmind-dev.iam.gserviceaccount.com" &&
      google_service_account_iam_member.github_actions_act_as_run.member == "serviceAccount:github-actions@www-fmind-dev.iam.gserviceaccount.com"
    )
    error_message = "The deployer may only push images, deploy this one service, read Cloud Run, and act as the runtime account."
  }

  assert {
    condition = (
      google_artifact_registry_repository_iam_member.security_repo_reader.role == "roles/artifactregistry.reader" &&
      google_artifact_registry_repository_iam_member.security_repo_reader.member == "serviceAccount:github-security@www-fmind-dev.iam.gserviceaccount.com" &&
      google_cloud_run_v2_service_iam_member.security_run_viewer.role == "roles/run.viewer" &&
      google_cloud_run_v2_service_iam_member.security_run_viewer.member == "serviceAccount:github-security@www-fmind-dev.iam.gserviceaccount.com"
    )
    error_message = "The scanner may only pull images and read this one service."
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

run "budget_alert_contract" {
  command = plan

  variables {
    budget_shared_project_numbers = ["123456789012"]
  }

  assert {
    condition = (
      google_billing_budget.website.billing_account == "000000-AAAAAA-000000" &&
      contains(google_billing_budget.website.budget_filter[0].projects, "projects/123456789012") &&
      google_billing_budget.website.budget_filter[0].calendar_period == "MONTH" &&
      google_billing_budget.website.budget_filter[0].credit_types_treatment == "EXCLUDE_ALL_CREDITS" &&
      google_billing_budget.website.amount[0].specified_amount[0].currency_code == "EUR" &&
      google_billing_budget.website.amount[0].specified_amount[0].units == "10" &&
      [for rule in google_billing_budget.website.threshold_rules : rule.threshold_percent] == [0.5, 0.9, 1.0, 1.0] &&
      google_billing_budget.website.threshold_rules[3].spend_basis == "FORECASTED_SPEND"
    )
    error_message = "The project needs a monthly gross-cost budget with shared-project support and 50/90/100% actual and 100% forecast alerts."
  }
}

# README: Deployment names this the qualified runtime; changing it needs a new qualification.
run "runtime_contract" {
  command = plan

  assert {
    condition = (
      google_cloud_run_v2_service.web.template[0].timeout == "30s" &&
      google_cloud_run_v2_service.web.template[0].max_instance_request_concurrency == 32 &&
      google_cloud_run_v2_service.web.template[0].containers[0].resources[0].limits["cpu"] == "1" &&
      google_cloud_run_v2_service.web.template[0].containers[0].resources[0].limits["memory"] == "512Mi" &&
      google_cloud_run_v2_service.web.template[0].containers[0].liveness_probe[0].http_get[0].path == "/health"
    )
    error_message = "The qualified runtime is 1 CPU, 512 MiB, concurrency 32, a 30-second timeout, and a /health liveness probe."
  }

  assert {
    condition = contains([for env in google_cloud_run_v2_service.web.template[0].containers[0].env :
      "${env.name}=${env.value}"
    ], "GOOGLE_CLOUD_PROJECT=www-fmind-dev")
    error_message = "Logs need GOOGLE_CLOUD_PROJECT to name their trace for request correlation."
  }
}

run "alerting_contract" {
  command = plan

  override_resource {
    target = google_monitoring_uptime_check_config.health
    values = { uptime_check_id = "www-check" }
  }
  override_resource {
    target = google_monitoring_uptime_check_config.apex
    values = { uptime_check_id = "apex-check" }
  }

  assert {
    condition = (
      google_monitoring_uptime_check_config.health.monitored_resource[0].labels["host"] == "www.fmind.dev" &&
      google_monitoring_uptime_check_config.health.http_check[0].validate_ssl &&
      length(google_monitoring_uptime_check_config.health.http_check[0].accepted_response_status_codes) == 0 &&
      google_monitoring_uptime_check_config.apex.monitored_resource[0].labels["host"] == "fmind.dev" &&
      google_monitoring_uptime_check_config.apex.http_check[0].validate_ssl &&
      google_monitoring_uptime_check_config.apex.http_check[0].path == "/health" &&
      length(google_monitoring_uptime_check_config.apex.http_check[0].accepted_response_status_codes) == 0
    )
    error_message = "Both hosts need a TLS-validating /health uptime check accepting the final 2xx response after redirects."
  }

  assert {
    condition = alltrue([for policy in [google_monitoring_alert_policy.uptime_health, google_monitoring_alert_policy.tls_expiry] :
      strcontains(policy.conditions[0].condition_threshold[0].filter, "metric.label.check_id = one_of(\"www-check\", \"apex-check\")") &&
      policy.conditions[0].condition_threshold[0].aggregations[0].group_by_fields == tolist(["resource.label.host"])
    ])
    error_message = "Uptime and certificate alerts must cover both hosts and alert per host."
  }

  assert {
    condition = (
      google_monitoring_alert_policy.uptime_health.conditions[0].condition_threshold[0].comparison == "COMPARISON_GT" &&
      google_monitoring_alert_policy.uptime_health.conditions[0].condition_threshold[0].threshold_value == 1 &&
      google_monitoring_alert_policy.uptime_health.conditions[0].condition_threshold[0].aggregations[0].cross_series_reducer == "REDUCE_COUNT_FALSE"
    )
    error_message = "The uptime alert must page only when two or more probe locations fail."
  }

  assert {
    condition = (
      endswith(google_monitoring_alert_policy.tls_expiry.conditions[0].condition_threshold[0].filter, "metric.type = \"monitoring.googleapis.com/uptime_check/time_until_ssl_cert_expires\"") &&
      google_monitoring_alert_policy.tls_expiry.conditions[0].condition_threshold[0].comparison == "COMPARISON_LT" &&
      google_monitoring_alert_policy.tls_expiry.conditions[0].condition_threshold[0].threshold_value == 21 &&
      google_monitoring_alert_policy.tls_expiry.conditions[0].condition_threshold[0].aggregations[0].cross_series_reducer == "REDUCE_MIN"
    )
    error_message = "A managed certificate with fewer than 21 days left must alert before it expires."
  }

  assert {
    condition     = strcontains(google_monitoring_alert_policy.error_logs.conditions[0].condition_matched_log[0].filter, "(severity>=ERROR OR httpRequest.status=429)")
    error_message = "Cloud Run logs capacity aborts (429) at WARNING; the log alert must still match them."
  }

  assert {
    condition = alltrue([for policy in [
      google_monitoring_alert_policy.uptime_health,
      google_monitoring_alert_policy.tls_expiry,
      google_monitoring_alert_policy.cloudrun_5xx_errors,
      google_monitoring_alert_policy.error_logs,
      ] : policy.severity != null && length(policy.documentation) == 1 && length(policy.documentation[0].content) > 0
    ])
    error_message = "Every alert policy needs a severity and a runbook."
  }
}
