# https://opentofu.org/docs/language/providers/requirements/
# OpenTofu required providers and GCS state backend settings.
#
terraform {
  # Track the OpenTofu version mise pins for this repository, so a machine with
  # an older engine fails at init instead of at apply.
  required_version = "~> 1.13"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "= 8.10.0"
    }
    google-beta = {
      source  = "hashicorp/google-beta"
      version = "= 8.10.0"
    }
    time = {
      source  = "hashicorp/time"
      version = "~> 0.14"
    }
  }

  backend "gcs" {
    bucket = "www-fmind-dev-tfstate"
    prefix = "infra/state"
  }

  # Ready-to-migrate OpenTofu state/plan encryption with Cloud KMS (two-step migration):
  # 1. Provision a dedicated KMS keyring + symmetric key in europe-west1 (outside this state).
  # 2. Add an `encryption {}` block with `key_provider "gcp_kms"`, `method "aes_gcm"`, and
  #    `method "unencrypted" "migrate" {}` as `state.fallback`, run `tofu apply -refresh-only`
  #    to re-encrypt state, verify the GCS state object is encrypted, then drop `fallback` and set `enforced = true`.
  # Ref: https://opentofu.org/docs/language/state/encryption/
}

locals {
  default_labels = {
    env         = "production"
    service     = var.service_name
    owner       = "fmind"
    cost-center = "www"
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

# The Budget API rejects user credentials without a quota project.
provider "google" {
  alias                 = "quota"
  project               = var.project_id
  region                = var.region
  billing_project       = var.project_id
  user_project_override = true
}

provider "google-beta" {
  project = var.project_id
  region  = var.region
}
