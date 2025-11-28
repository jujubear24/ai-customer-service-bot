# ==============================================================================
# Project Configuration
# ==============================================================================

variable "project_name" {
  description = "The name of the project"
  type        = string
}

variable "environment" {
  description = "The name of the environment (e.g., dev, staging, prod)"
  type        = string
}

variable "aws_region" {
  description = "The AWS region for this environment"
  type        = string
}

# ==============================================================================
# Lambda Configuration
# ==============================================================================

variable "log_level" {
  description = "Log level for Lambda functions"
  type        = string
  default     = "INFO"
}

# ==============================================================================
# Alerting Configuration
# ==============================================================================

variable "alert_email" {
  description = "Email address for budget and operational alerts"
  type        = string
}

# ==============================================================================
# Tagging
# ==============================================================================

variable "common_tags" {
  description = "Common tags for all resources"
  type        = map(string)
  default = {
    ManagedBy = "Terraform"
    Owner     = "DevOps"
  }
}

# ==============================================================================
# Name Spaces
# ==============================================================================
variable "metrics_namespace" {
  description = "CloudWatch metrics namespace"
  type        = string
  default     = "CustomerServiceBot"
}
