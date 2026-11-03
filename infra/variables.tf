variable "project" {
  type        = string
  description = "GCP project id"
}

variable "region" {
  type    = string
  default = "europe-west3" # Frankfurt
}

variable "env" {
  type    = string
  default = "dev"
  validation {
    condition     = contains(["dev", "prod"], var.env)
    error_message = "env is dev or prod"
  }
}

variable "image" {
  type        = string
  description = "Container image with the aae CLI"
}

variable "production_agent" {
  type    = string
  default = "baseline"
}

# Keep these equal to config/traces.yaml (tests/test_infra.py checks).
variable "hot_days" {
  type    = number
  default = 90
}

variable "archive_keep_days" {
  type    = number
  default = 400
}

variable "evidence_retention_days" {
  type    = number
  default = 3650 # ten years, like the audit file it supports
}
