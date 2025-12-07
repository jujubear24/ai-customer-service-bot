# =============================================================================
# Knowledge Base Module - Input Variables
# =============================================================================

# -----------------------------------------------------------------------------
# Required Variables
# -----------------------------------------------------------------------------

variable "project_name" {
  description = "Name of the project (used in resource naming)"
  type        = string

  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{2,20}$", var.project_name))
    error_message = "Project name must be 3-21 lowercase alphanumeric characters, starting with a letter."
  }
}

variable "environment" {
  description = "Deployment environment (dev, staging, prod)"
  type        = string

  validation {
    condition     = contains(["dev", "staging", "prod"], var.environment)
    error_message = "Environment must be one of: dev, staging, prod."
  }
}

# -----------------------------------------------------------------------------
# Embedding Model Configuration
# -----------------------------------------------------------------------------

variable "embedding_model_id" {
  description = "Bedrock embedding model ID"
  type        = string
  default     = "amazon.titan-embed-text-v2:0"

  validation {
    condition = contains([
      "amazon.titan-embed-text-v1",
      "amazon.titan-embed-text-v2:0",
      "cohere.embed-english-v3",
      "cohere.embed-multilingual-v3"
    ], var.embedding_model_id)
    error_message = "Must be a valid Bedrock embedding model ID."
  }
}

# -----------------------------------------------------------------------------
# S3 Configuration
# -----------------------------------------------------------------------------

variable "s3_version_retention_days" {
  description = "Number of days to retain non-current S3 object versions"
  type        = number
  default     = 30

  validation {
    condition     = var.s3_version_retention_days >= 1 && var.s3_version_retention_days <= 365
    error_message = "S3 version retention must be between 1 and 365 days."
  }
}

# -----------------------------------------------------------------------------
# Tags
# -----------------------------------------------------------------------------

variable "tags" {
  description = "Additional tags to apply to all resources"
  type        = map(string)
  default     = {}
}
