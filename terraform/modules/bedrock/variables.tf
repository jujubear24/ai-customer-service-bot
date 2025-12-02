# Variables for Bedrock module

# ==============================================================================
# Required Variables
# ==============================================================================

variable "project_name" {
  description = "Name of the project, used for resource naming"
  type        = string
}

variable "environment" {
  description = "Environment name (dev, staging, prod)"
  type        = string
}

# ==============================================================================
# Model Configuration
# ==============================================================================

variable "allowed_model_ids" {
  description = "List of Bedrock model IDs that can be invoked (use regional prefix for newer models)"
  type        = list(string)
  default     = ["us.anthropic.claude-haiku-4-5-20251001-v1:0"]

  validation {
    condition     = length(var.allowed_model_ids) > 0
    error_message = "At least one model ID must be specified."
  }
}

variable "enable_streaming" {
  description = "Whether to enable streaming response capabilities"
  type        = bool
  default     = false
}

# ==============================================================================
# Observability Configuration
# ==============================================================================

variable "metrics_namespace" {
  description = "CloudWatch metrics namespace for Bedrock metrics"
  type        = string
  default     = "AICustomerService"
}

variable "enable_alarms" {
  description = "Whether to create CloudWatch alarms for Bedrock usage"
  type        = bool
  default     = false
}

variable "alarm_sns_topic_arn" {
  description = "SNS topic ARN for alarm notifications"
  type        = string
  default     = null
}

variable "throttling_alarm_threshold" {
  description = "Number of throttling events to trigger alarm"
  type        = number
  default     = 5
}

variable "error_alarm_threshold" {
  description = "Number of errors to trigger alarm"
  type        = number
  default     = 10
}

# ==============================================================================
# Tags
# ==============================================================================

variable "tags" {
  description = "Additional tags to apply to resources"
  type        = map(string)
  default     = {}
}
