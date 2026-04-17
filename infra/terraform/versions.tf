terraform {
  required_version = ">= 1.9"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 6.10"
    }
    google-beta = {
      source  = "hashicorp/google-beta"
      version = "~> 6.10"
    }
  }

  # Per dev: local state. In prod configurare un backend GCS con versioning + locking.
  # backend "gcs" {
  #   bucket = "avvocato-tfstate-<env>"
  #   prefix = "state"
  # }
}
