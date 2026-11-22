<!-- BEGIN_TF_DOCS -->
## Requirements

| Name | Version |
| ---- | ------- |
| <a name="requirement_terraform"></a> [terraform](#requirement\_terraform) | ~> 1.13 |
| <a name="requirement_google"></a> [google](#requirement\_google) | = 8.10.0 |
| <a name="requirement_google-beta"></a> [google-beta](#requirement\_google-beta) | = 8.10.0 |
| <a name="requirement_time"></a> [time](#requirement\_time) | ~> 0.14 |

## Providers

| Name | Version |
| ---- | ------- |
| <a name="provider_google"></a> [google](#provider\_google) | = 8.10.0 |
| <a name="provider_google.quota"></a> [google.quota](#provider\_google.quota) | = 8.10.0 |
| <a name="provider_google-beta"></a> [google-beta](#provider\_google-beta) | = 8.10.0 |
| <a name="provider_time"></a> [time](#provider\_time) | ~> 0.14 |

## Resources

| Name | Type |
| ---- | ---- |
| [google-beta_google_project_service_identity.logging](https://registry.terraform.io/providers/hashicorp/google-beta/8.10.0/docs/resources/google_project_service_identity) | resource |
| [google_artifact_registry_repository.repo](https://registry.terraform.io/providers/hashicorp/google/8.10.0/docs/resources/artifact_registry_repository) | resource |
| [google_artifact_registry_repository_iam_member.repo_writer](https://registry.terraform.io/providers/hashicorp/google/8.10.0/docs/resources/artifact_registry_repository_iam_member) | resource |
| [google_artifact_registry_repository_iam_member.security_repo_reader](https://registry.terraform.io/providers/hashicorp/google/8.10.0/docs/resources/artifact_registry_repository_iam_member) | resource |
| [google_bigquery_dataset.analytics](https://registry.terraform.io/providers/hashicorp/google/8.10.0/docs/resources/bigquery_dataset) | resource |
| [google_bigquery_dataset.billing](https://registry.terraform.io/providers/hashicorp/google/8.10.0/docs/resources/bigquery_dataset) | resource |
| [google_bigquery_dataset_iam_member.analytics_writer](https://registry.terraform.io/providers/hashicorp/google/8.10.0/docs/resources/bigquery_dataset_iam_member) | resource |
| [google_billing_budget.website](https://registry.terraform.io/providers/hashicorp/google/8.10.0/docs/resources/billing_budget) | resource |
| [google_cloud_run_domain_mapping.apex](https://registry.terraform.io/providers/hashicorp/google/8.10.0/docs/resources/cloud_run_domain_mapping) | resource |
| [google_cloud_run_domain_mapping.www](https://registry.terraform.io/providers/hashicorp/google/8.10.0/docs/resources/cloud_run_domain_mapping) | resource |
| [google_cloud_run_v2_service.web](https://registry.terraform.io/providers/hashicorp/google/8.10.0/docs/resources/cloud_run_v2_service) | resource |
| [google_cloud_run_v2_service_iam_member.github_actions_run_developer](https://registry.terraform.io/providers/hashicorp/google/8.10.0/docs/resources/cloud_run_v2_service_iam_member) | resource |
| [google_cloud_run_v2_service_iam_member.noauth](https://registry.terraform.io/providers/hashicorp/google/8.10.0/docs/resources/cloud_run_v2_service_iam_member) | resource |
| [google_cloud_run_v2_service_iam_member.security_run_viewer](https://registry.terraform.io/providers/hashicorp/google/8.10.0/docs/resources/cloud_run_v2_service_iam_member) | resource |
| [google_iam_workload_identity_pool.github_pool](https://registry.terraform.io/providers/hashicorp/google/8.10.0/docs/resources/iam_workload_identity_pool) | resource |
| [google_iam_workload_identity_pool_provider.github_provider](https://registry.terraform.io/providers/hashicorp/google/8.10.0/docs/resources/iam_workload_identity_pool_provider) | resource |
| [google_logging_project_bucket_config.default](https://registry.terraform.io/providers/hashicorp/google/8.10.0/docs/resources/logging_project_bucket_config) | resource |
| [google_logging_project_exclusion.analytics_default](https://registry.terraform.io/providers/hashicorp/google/8.10.0/docs/resources/logging_project_exclusion) | resource |
| [google_logging_project_sink.analytics](https://registry.terraform.io/providers/hashicorp/google/8.10.0/docs/resources/logging_project_sink) | resource |
| [google_monitoring_alert_policy.cloudrun_5xx_errors](https://registry.terraform.io/providers/hashicorp/google/8.10.0/docs/resources/monitoring_alert_policy) | resource |
| [google_monitoring_alert_policy.error_logs](https://registry.terraform.io/providers/hashicorp/google/8.10.0/docs/resources/monitoring_alert_policy) | resource |
| [google_monitoring_alert_policy.instance_saturation](https://registry.terraform.io/providers/hashicorp/google/8.10.0/docs/resources/monitoring_alert_policy) | resource |
| [google_monitoring_alert_policy.request_latency](https://registry.terraform.io/providers/hashicorp/google/8.10.0/docs/resources/monitoring_alert_policy) | resource |
| [google_monitoring_alert_policy.tls_expiry](https://registry.terraform.io/providers/hashicorp/google/8.10.0/docs/resources/monitoring_alert_policy) | resource |
| [google_monitoring_alert_policy.uptime_health](https://registry.terraform.io/providers/hashicorp/google/8.10.0/docs/resources/monitoring_alert_policy) | resource |
| [google_monitoring_notification_channel.email](https://registry.terraform.io/providers/hashicorp/google/8.10.0/docs/resources/monitoring_notification_channel) | resource |
| [google_monitoring_uptime_check_config.apex](https://registry.terraform.io/providers/hashicorp/google/8.10.0/docs/resources/monitoring_uptime_check_config) | resource |
| [google_monitoring_uptime_check_config.health](https://registry.terraform.io/providers/hashicorp/google/8.10.0/docs/resources/monitoring_uptime_check_config) | resource |
| [google_project_iam_member.github_actions_run_viewer](https://registry.terraform.io/providers/hashicorp/google/8.10.0/docs/resources/project_iam_member) | resource |
| [google_project_service.artifactregistry](https://registry.terraform.io/providers/hashicorp/google/8.10.0/docs/resources/project_service) | resource |
| [google_project_service.bigquery](https://registry.terraform.io/providers/hashicorp/google/8.10.0/docs/resources/project_service) | resource |
| [google_project_service.billingbudgets](https://registry.terraform.io/providers/hashicorp/google/8.10.0/docs/resources/project_service) | resource |
| [google_project_service.cloudbilling](https://registry.terraform.io/providers/hashicorp/google/8.10.0/docs/resources/project_service) | resource |
| [google_project_service.iam](https://registry.terraform.io/providers/hashicorp/google/8.10.0/docs/resources/project_service) | resource |
| [google_project_service.iamcredentials](https://registry.terraform.io/providers/hashicorp/google/8.10.0/docs/resources/project_service) | resource |
| [google_project_service.logging](https://registry.terraform.io/providers/hashicorp/google/8.10.0/docs/resources/project_service) | resource |
| [google_project_service.monitoring](https://registry.terraform.io/providers/hashicorp/google/8.10.0/docs/resources/project_service) | resource |
| [google_project_service.run](https://registry.terraform.io/providers/hashicorp/google/8.10.0/docs/resources/project_service) | resource |
| [google_project_service.sts](https://registry.terraform.io/providers/hashicorp/google/8.10.0/docs/resources/project_service) | resource |
| [google_service_account.cloudrun_sa](https://registry.terraform.io/providers/hashicorp/google/8.10.0/docs/resources/service_account) | resource |
| [google_service_account.github_actions_sa](https://registry.terraform.io/providers/hashicorp/google/8.10.0/docs/resources/service_account) | resource |
| [google_service_account.github_security_sa](https://registry.terraform.io/providers/hashicorp/google/8.10.0/docs/resources/service_account) | resource |
| [google_service_account_iam_member.github_actions_act_as_run](https://registry.terraform.io/providers/hashicorp/google/8.10.0/docs/resources/service_account_iam_member) | resource |
| [google_service_account_iam_member.security_wif_impersonate](https://registry.terraform.io/providers/hashicorp/google/8.10.0/docs/resources/service_account_iam_member) | resource |
| [google_service_account_iam_member.wif_impersonate](https://registry.terraform.io/providers/hashicorp/google/8.10.0/docs/resources/service_account_iam_member) | resource |
| [time_sleep.wait_for_apis](https://registry.terraform.io/providers/hashicorp/time/latest/docs/resources/sleep) | resource |
| [google_project.current](https://registry.terraform.io/providers/hashicorp/google/8.10.0/docs/data-sources/project) | data source |

## Inputs

| Name | Description | Type | Default | Required |
| ---- | ----------- | ---- | ------- | :------: |
| <a name="input_analytics_location"></a> [analytics\_location](#input\_analytics\_location) | The BigQuery location for privacy-preserving pageview analytics | `string` | `"EU"` | no |
| <a name="input_apex_domain"></a> [apex\_domain](#input\_apex\_domain) | The registered domain; Cloud Run serves it and its www host | `string` | `"fmind.dev"` | no |
| <a name="input_billing_account"></a> [billing\_account](#input\_billing\_account) | Cloud Billing account ID that pays for the project (supplied at plan/apply via TF\_VAR\_billing\_account, never committed) | `string` | n/a | yes |
| <a name="input_budget_shared_project_numbers"></a> [budget\_shared\_project\_numbers](#input\_budget\_shared\_project\_numbers) | Numeric project IDs of companion projects sharing this gross-cost budget (supplied at plan/apply via TF\_VAR\_budget\_shared\_project\_numbers, never committed) | `list(string)` | n/a | yes |
| <a name="input_github_owner_numeric_id"></a> [github\_owner\_numeric\_id](#input\_github\_owner\_numeric\_id) | Immutable GitHub owner ID used by Workload Identity Federation | `string` | `"3929438"` | no |
| <a name="input_github_repository"></a> [github\_repository](#input\_github\_repository) | The GitHub repository in the format owner/repo | `string` | `"fmind/www"` | no |
| <a name="input_github_repository_numeric_id"></a> [github\_repository\_numeric\_id](#input\_github\_repository\_numeric\_id) | Immutable GitHub repository ID used by Workload Identity Federation | `string` | `"1261133438"` | no |
| <a name="input_image_uri"></a> [image\_uri](#input\_image\_uri) | The Docker image URI to deploy. Defaults to a hello-world image for the initial create; the live image is managed out-of-band by CI (see cloud\_run.tf lifecycle.ignore\_changes). | `string` | `"us-docker.pkg.dev/cloudrun/container/hello"` | no |
| <a name="input_monthly_budget_eur"></a> [monthly\_budget\_eur](#input\_monthly\_budget\_eur) | Monthly gross-cost alert threshold for this project in EUR | `number` | `10` | no |
| <a name="input_notification_email"></a> [notification\_email](#input\_notification\_email) | The email address for alert notifications | `string` | `"contact@fmind.dev"` | no |
| <a name="input_project_id"></a> [project\_id](#input\_project\_id) | The GCP project ID to deploy resources to | `string` | `"www-fmind-dev"` | no |
| <a name="input_region"></a> [region](#input\_region) | The GCP region to deploy resources to | `string` | `"europe-west1"` | no |
| <a name="input_repository_id"></a> [repository\_id](#input\_repository\_id) | The name of the Artifact Registry repository | `string` | `"app"` | no |
| <a name="input_service_name"></a> [service\_name](#input\_service\_name) | The name of the Cloud Run service | `string` | `"www-fmind-dev"` | no |

## Outputs

| Name | Description |
| ---- | ----------- |
| <a name="output_apex_dns_records"></a> [apex\_dns\_records](#output\_apex\_dns\_records) | Records to publish in the authoritative Cloud DNS zone so the apex reaches Cloud Run |
<!-- END_TF_DOCS -->