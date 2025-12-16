# ==============================================================================
# API Gateway Module Variables
# ==============================================================================

variable "project_name" {
  description = "The name of the project"
  type        = string
}

variable "environment" {
  description = "The name of the environment (e.g., dev, staging, prod)"
  type        = string
}

# ==============================================================================
# Function Integration - Intent Classifier
# ==============================================================================

variable "intent_classifier_invoke_arn" {
  description = "The invocation ARN of the intent classifier Lambda function"
  type        = string
}

variable "intent_classifier_function_name" {
  description = "The name of the intent classifier Lambda function"
  type        = string
}

# ==============================================================================
# Function Integration - Chat Orchestrator
# ==============================================================================

variable "chat_orchestrator_invoke_arn" {
  description = "The invocation ARN of the chat orchestrator Lambda function"
  type        = string
}

variable "chat_orchestrator_function_name" {
  description = "The name of the chat orchestrator Lambda function"
  type        = string
}

# ==============================================================================
# Logging & Monitoring
# ==============================================================================

variable "log_retention_days" {
  description = "Number of days to retain CloudWatch logs"
  type        = number
  default     = 14
}

variable "api_logging_level" {
  description = "API Gateway logging level (INFO, ERROR, OFF)"
  type        = string
  default     = "INFO"

  validation {
    condition     = contains(["INFO", "ERROR", "OFF"], var.api_logging_level)
    error_message = "API logging level must be one of: INFO, ERROR, OFF"
  }
}

variable "cloudwatch_kms_key_arn" {
  description = "ARN of KMS key for CloudWatch log encryption (optional)"
  type        = string
  default     = null
}

# ==============================================================================
# Throttling
# ==============================================================================

variable "throttle_burst_limit" {
  description = "API Gateway throttle burst limit"
  type        = number
  default     = 100
}

variable "throttle_rate_limit" {
  description = "API Gateway throttle rate limit (requests per second)"
  type        = number
  default     = 50
}

# ==============================================================================
# Tagging
# ==============================================================================

variable "common_tags" {
  description = "Common tags for all resources"
  type        = map(string)
  default     = {}
}
