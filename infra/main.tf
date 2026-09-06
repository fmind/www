# ==============================================================================
# www Infrastructure
# ==============================================================================
# OpenTofu-managed Google Cloud resources for the portfolio site on Cloud Run.
# Split by concern:
#
# - apis.tf        : GCP service APIs enabling and propagation timer
# - registry.tf    : Artifact Registry repository (+ retention policies)
# - iam.tf         : Cloud Run runtime service account and project IAM roles
# - cloud_run.tf   : Cloud Run service and its public-access IAM
# - analytics.tf   : Privacy-preserving pageview export to BigQuery
# - monitoring.tf  : Notification channel and error alert policies
# - wif.tf         : Keyless GitHub Actions CI (Workload Identity Federation)
# - providers.tf   : Provider + GCS remote state backend
# - variables.tf   : Input variables and defaults
# - outputs.tf     : Service URL, registry URL, WIF provider, deployer SA
#
# The site is served publicly at https://www.fmind.dev/ via a Cloud Run domain
# mapping (managed outside this state); deploying new revisions keeps it intact.
# A domain mapping is not a trusted geography boundary, so the application does
# not derive analytics dimensions from caller-controlled request headers.
# ==============================================================================
