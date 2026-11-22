# Infrastructure variables defining default settings and parameters.

variable "analytics_location" {
  description = "The BigQuery location for privacy-preserving pageview analytics"
  type        = string
  default     = "EU"

  validation {
    condition     = can(regex("^[A-Za-z0-9-]+$", var.analytics_location))
    error_message = "analytics_location must be a valid BigQuery region or multi-region identifier."
  }
}

variable "apex_domain" {
  description = "The registered domain; Cloud Run serves it and its www host"
  type        = string
  default     = "fmind.dev"

  validation {
    condition     = can(regex("^[a-z0-9-]+(\\.[a-z0-9-]+)+$", var.apex_domain))
    error_message = "apex_domain must be a lowercase DNS domain name."
  }
}

variable "billing_account" {
  description = "Cloud Billing account ID that pays for the project (supplied at plan/apply via TF_VAR_billing_account, never committed)"
  type        = string
  sensitive   = true

  validation {
    condition     = can(regex("^[A-Z0-9]{6}-[A-Z0-9]{6}-[A-Z0-9]{6}$", var.billing_account))
    error_message = "billing_account must look like XXXXXX-XXXXXX-XXXXXX."
  }
}

variable "budget_shared_project_numbers" {
  description = "Numeric project IDs of companion projects sharing this gross-cost budget (supplied at plan/apply via TF_VAR_budget_shared_project_numbers, never committed)"
  type        = list(string)
  sensitive   = true

  validation {
    condition     = alltrue([for number in var.budget_shared_project_numbers : can(regex("^[0-9]{6,20}$", number))])
    error_message = "budget_shared_project_numbers must contain numeric project numbers only."
  }
}

variable "github_repository" {
  description = "The GitHub repository in the format owner/repo"
  type        = string
  default     = "fmind/www"

  validation {
    condition     = can(regex("^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$", var.github_repository))
    error_message = "github_repository must use owner/repo format."
  }
}

variable "github_repository_numeric_id" {
  description = "Immutable GitHub repository ID used by Workload Identity Federation"
  type        = string
  default     = "1261133438"

  validation {
    condition     = can(regex("^[0-9]{1,20}$", var.github_repository_numeric_id))
    error_message = "github_repository_numeric_id must be a numeric GitHub ID."
  }
}

variable "github_owner_numeric_id" {
  description = "Immutable GitHub owner ID used by Workload Identity Federation"
  type        = string
  default     = "3929438"

  validation {
    condition     = can(regex("^[0-9]{1,20}$", var.github_owner_numeric_id))
    error_message = "github_owner_numeric_id must be a numeric GitHub ID."
  }
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

  validation {
    condition     = can(regex("^[^@\\s]+@[^@\\s]+\\.[^@\\s]+$", var.notification_email))
    error_message = "notification_email must be a valid email address."
  }
}

variable "project_id" {
  description = "The GCP project ID to deploy resources to"
  type        = string
  default     = "www-fmind-dev"

  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{4,28}[a-z0-9]$", var.project_id))
    error_message = "project_id must be a valid 6-30 character GCP project ID."
  }
}

variable "region" {
  description = "The GCP region to deploy resources to"
  type        = string
  default     = "europe-west1"

  validation {
    condition     = can(regex("^[a-z]+-[a-z]+[0-9]+$", var.region))
    error_message = "region must be a valid GCP region name (for example europe-west1)."
  }
}

variable "repository_id" {
  description = "The name of the Artifact Registry repository"
  type        = string
  default     = "app"

  validation {
    condition     = can(regex("^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$", var.repository_id))
    error_message = "repository_id must contain lowercase letters, digits, and hyphens."
  }
}

variable "service_name" {
  description = "The name of the Cloud Run service"
  type        = string
  default     = "www-fmind-dev"

  validation {
    condition     = can(regex("^[a-z]([a-z0-9-]{0,47}[a-z0-9])?$", var.service_name))
    error_message = "service_name must be a valid lowercase Cloud Run service name."
  }
}
