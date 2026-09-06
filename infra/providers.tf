# OpenTofu required providers and GCS state backend settings.
#
terraform {
  # Track the OpenTofu version mise pins for this repository, so a machine with
  # an older engine fails at init instead of at apply.
  required_version = "~> 1.12"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "8.0.0"
    }
    google-beta = {
      source  = "hashicorp/google-beta"
      version = "= 7.43.0"
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
}

provider "google" {
  project = var.project_id
  region  = var.region
}

provider "google-beta" {
  project = var.project_id
  region  = var.region
}
