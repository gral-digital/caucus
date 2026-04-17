variable "project" {
  description = "ID del progetto GCP."
  type        = string
}

variable "region" {
  description = "Regione EU principale (GDPR + sovranità)."
  type        = string
  default     = "europe-west1"
}

variable "env" {
  description = "Nome environment (dev | prod)."
  type        = string
  validation {
    condition     = contains(["dev", "prod"], var.env)
    error_message = "env deve essere 'dev' o 'prod'."
  }
}

variable "api_image" {
  description = "Immagine Docker dell'API (Artifact Registry)."
  type        = string
}

variable "web_image" {
  description = "Immagine Docker del frontend Next.js."
  type        = string
}

variable "sql_tier" {
  description = "Tier Cloud SQL."
  type        = string
  default     = "db-custom-2-8192"
}

variable "vertex_region" {
  description = "Regione Vertex AI per LLM inference."
  type        = string
  default     = "europe-west1"
}
