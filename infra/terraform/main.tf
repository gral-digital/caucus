provider "google" {
  project = var.project
  region  = var.region
}

provider "google-beta" {
  project = var.project
  region  = var.region
}

locals {
  name_prefix = "avvocato-${var.env}"
  labels = {
    app         = "avvocato"
    environment = var.env
    managed-by  = "terraform"
  }
}

# -------------------- API services --------------------

resource "google_project_service" "services" {
  for_each = toset([
    "run.googleapis.com",
    "sqladmin.googleapis.com",
    "artifactregistry.googleapis.com",
    "secretmanager.googleapis.com",
    "aiplatform.googleapis.com",
    "cloudtrace.googleapis.com",
    "logging.googleapis.com",
    "monitoring.googleapis.com",
    "redis.googleapis.com",
    "cloudscheduler.googleapis.com",
    "cloudtasks.googleapis.com",
    "vpcaccess.googleapis.com",
  ])
  service            = each.value
  disable_on_destroy = false
}

# -------------------- Network --------------------

resource "google_compute_network" "vpc" {
  name                    = "${local.name_prefix}-vpc"
  auto_create_subnetworks = false
}

resource "google_compute_subnetwork" "subnet" {
  name                     = "${local.name_prefix}-subnet"
  ip_cidr_range            = "10.20.0.0/20"
  region                   = var.region
  network                  = google_compute_network.vpc.id
  private_ip_google_access = true
}

resource "google_vpc_access_connector" "connector" {
  name          = "${local.name_prefix}-vpcac"
  region        = var.region
  ip_cidr_range = "10.8.0.0/28"
  network       = google_compute_network.vpc.name
  depends_on    = [google_project_service.services]
}

# -------------------- Storage --------------------

resource "google_storage_bucket" "documents" {
  name                        = "${local.name_prefix}-documents"
  location                    = var.region
  force_destroy               = false
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"
  versioning { enabled = true }
  labels                      = local.labels
}

resource "google_storage_bucket" "sources" {
  name                        = "${local.name_prefix}-sources"
  location                    = var.region
  force_destroy               = false
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"
  labels                      = local.labels
}

# -------------------- Cloud SQL (Postgres + pgvector) --------------------

resource "google_sql_database_instance" "postgres" {
  name             = "${local.name_prefix}-pg"
  database_version = "POSTGRES_16"
  region           = var.region
  depends_on       = [google_project_service.services]

  settings {
    tier              = var.sql_tier
    availability_type = var.env == "prod" ? "REGIONAL" : "ZONAL"
    disk_autoresize   = true
    disk_type         = "PD_SSD"

    backup_configuration {
      enabled                        = true
      point_in_time_recovery_enabled = true
      start_time                     = "02:00"
      location                       = var.region
      transaction_log_retention_days = 7
    }

    database_flags {
      name  = "cloudsql.enable_pgvector"
      value = "on"
    }

    ip_configuration {
      ipv4_enabled    = false
      private_network = google_compute_network.vpc.id
    }

    user_labels = local.labels
  }

  deletion_protection = var.env == "prod"
}

resource "google_sql_database" "avvocato" {
  name     = "avvocato"
  instance = google_sql_database_instance.postgres.name
}

# -------------------- Redis (Memorystore) --------------------

resource "google_redis_instance" "cache" {
  name               = "${local.name_prefix}-redis"
  tier               = var.env == "prod" ? "STANDARD_HA" : "BASIC"
  memory_size_gb     = 1
  region             = var.region
  authorized_network = google_compute_network.vpc.id
  redis_version      = "REDIS_7_2"
  depends_on         = [google_project_service.services]
}

# -------------------- Artifact Registry --------------------

resource "google_artifact_registry_repository" "docker" {
  location      = var.region
  repository_id = "${local.name_prefix}-docker"
  format        = "DOCKER"
  depends_on    = [google_project_service.services]
}

# -------------------- Cloud Run: API --------------------

resource "google_cloud_run_v2_service" "api" {
  name     = "${local.name_prefix}-api"
  location = var.region
  ingress  = "INGRESS_TRAFFIC_ALL"

  template {
    service_account = google_service_account.api.email
    scaling {
      min_instance_count = var.env == "prod" ? 1 : 0
      max_instance_count = var.env == "prod" ? 10 : 3
    }
    vpc_access {
      connector = google_vpc_access_connector.connector.id
      egress    = "ALL_TRAFFIC"
    }
    containers {
      image = var.api_image
      ports { container_port = 8000 }
      resources {
        limits = {
          cpu    = "2"
          memory = "2Gi"
        }
      }
      env {
        name  = "APP_ENV"
        value = var.env
      }
      env {
        name  = "GCP_PROJECT"
        value = var.project
      }
      env {
        name  = "GCP_REGION"
        value = var.region
      }
      env {
        name  = "DATABASE_URL"
        value = "postgresql+asyncpg://avvocato@/avvocato?host=/cloudsql/${google_sql_database_instance.postgres.connection_name}"
      }
      # Secrets sensibili caricati da Secret Manager (definire le secret resource altrove).
    }
    annotations = {
      "run.googleapis.com/cloudsql-instances" = google_sql_database_instance.postgres.connection_name
    }
  }
  labels = local.labels
}

resource "google_service_account" "api" {
  account_id   = "${local.name_prefix}-api"
  display_name = "Avvocato API (${var.env})"
}

resource "google_project_iam_member" "api_roles" {
  for_each = toset([
    "roles/cloudsql.client",
    "roles/secretmanager.secretAccessor",
    "roles/aiplatform.user",
    "roles/storage.objectAdmin",
    "roles/logging.logWriter",
    "roles/cloudtrace.agent",
  ])
  project = var.project
  role    = each.value
  member  = "serviceAccount:${google_service_account.api.email}"
}

# -------------------- Cloud Run: Web --------------------

resource "google_cloud_run_v2_service" "web" {
  name     = "${local.name_prefix}-web"
  location = var.region
  ingress  = "INGRESS_TRAFFIC_ALL"

  template {
    scaling {
      min_instance_count = 0
      max_instance_count = var.env == "prod" ? 10 : 3
    }
    containers {
      image = var.web_image
      ports { container_port = 3000 }
      env {
        name  = "NEXT_PUBLIC_API_URL"
        value = google_cloud_run_v2_service.api.uri
      }
    }
  }
  labels = local.labels
}

# Output utili
output "api_url" { value = google_cloud_run_v2_service.api.uri }
output "web_url" { value = google_cloud_run_v2_service.web.uri }
output "sql_connection" { value = google_sql_database_instance.postgres.connection_name }
output "redis_host" { value = google_redis_instance.cache.host }
output "documents_bucket" { value = google_storage_bucket.documents.name }
