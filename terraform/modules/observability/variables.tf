# ==============================================================================
# Project Configuration
# ==============================================================================

variable "project_name" {
  description = "The name of the project"
  type        = string
}

variable "environment" {
  description = "The name of the environment"
  type        = string
}

# ==============================================================================
# Lambda Configuration
# ==============================================================================

variable "lambda_functions" {
  description = "List of Lambda function names to pre-create log groups for"
  type        = list(string)
  default     = []
}

# ==============================================================================
# CloudWatch Configuration
# ==============================================================================

variable "log_retention_days" {
  description = "Number of days to retain CloudWatch logs"
  type        = number
  default     = 14
}

# ==============================================================================
# Budget Configuration
# ==============================================================================

variable "budget_amount" {
  description = "The monthly budget limit in USD"
  type        = string
}

variable "alert_emails" {
  description = "List of email addresses to receive budget alerts"
  type        = list(string)
}

# ==============================================================================
# Tagging
# ==============================================================================

variable "common_tags" {
  description = "Common tags for all resources"
  type        = map(string)
  default     = {}
}
