# Infrastructure variables defining default settings and parameters.

variable "analytics_location" {
  description = "The BigQuery location for privacy-preserving pageview analytics"
  type        = string
  default     = "EU"
}

variable "apex_domain" {
  description = "The registered domain; Cloud Run serves it and its www host"
  type        = string
  default     = "fmind.dev"
}

variable "billing_account" {
  description = "Cloud Billing account ID that pays for the project (supplied at plan/apply via TF_VAR_billing_account, never committed)"
  type        = string

  validation {
    condition     = can(regex("^[A-Z0-9]{6}-[A-Z0-9]{6}-[A-Z0-9]{6}$", var.billing_account))
    error_message = "billing_account must look like XXXXXX-XXXXXX-XXXXXX."
  }
}

variable "budget_shared_project_numbers" {
  description = "Numeric project IDs of companion projects sharing this gross-cost budget (supplied at plan/apply via TF_VAR_budget_shared_project_numbers, never committed)"
  type        = list(string)
  default     = []

  validation {
    condition     = alltrue([for number in var.budget_shared_project_numbers : can(regex("^[0-9]{6,20}$", number))])
    error_message = "budget_shared_project_numbers must contain numeric project numbers only."
  }
}

variable "github_repository" {
  description = "The GitHub repository in the format owner/repo"
  type        = string
  default     = "fmind/www"
}

variable "github_repository_numeric_id" {
  description = "Immutable GitHub repository ID used by Workload Identity Federation"
  type        = string
  default     = "1261133438"
}

variable "github_owner_numeric_id" {
  description = "Immutable GitHub owner ID used by Workload Identity Federation"
  type        = string
  default     = "3929438"
}

variable "image_uri" {
  description = "The Docker image URI to deploy. Defaults to a hello-world image for the initial create; the live image is managed out-of-band by CI (see cloud_run.tf lifecycle.ignore_changes)."
  type        = string
  default     = "us-docker.pkg.dev/cloudrun/container/hello"
}

variable "monthly_budget_eur" {
  description = "Monthly gross-cost alert threshold for this project in EUR"
  type        = number
  default     = 10

  validation {
    condition     = var.monthly_budget_eur > 0 && floor(var.monthly_budget_eur) == var.monthly_budget_eur
    error_message = "monthly_budget_eur must be a positive whole number."
  }
}

variable "notification_email" {
  description = "The email address for alert notifications"
  type        = string
  default     = "contact@fmind.dev"
}

variable "project_id" {
  description = "The GCP project ID to deploy resources to"
  type        = string
  default     = "www-fmind-dev"
}

variable "region" {
  description = "The GCP region to deploy resources to"
  type        = string
  default     = "europe-west1"
}

variable "repository_id" {
  description = "The name of the Artifact Registry repository"
  type        = string
  default     = "app"
}

variable "service_name" {
  description = "The name of the Cloud Run service"
  type        = string
  default     = "www-fmind-dev"
}
