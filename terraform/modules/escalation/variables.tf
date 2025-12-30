# =============================================================================
# Escalation Module Variables
# =============================================================================

# -----------------------------------------------------------------------------
# Required Variables
# -----------------------------------------------------------------------------
variable "project_name" {
  description = "Name of the project (used for resource naming)"
  type        = string
}

variable "environment" {
  description = "Environment name (dev, staging, prod)"
  type        = string
}

variable "dynamodb_table_arn" {
  description = "ARN of the DynamoDB conversations table"
  type        = string
}

# -----------------------------------------------------------------------------
# SQS Configuration
# -----------------------------------------------------------------------------
variable "message_retention_seconds" {
  description = "SQS message retention period in seconds (default: 1 day)"
  type        = number
  default     = 86400
}

variable "visibility_timeout_seconds" {
  description = "SQS visibility timeout in seconds"
  type        = number
  default     = 60
}

variable "enable_dlq" {
  description = "Enable dead letter queue for failed messages"
  type        = bool
  default     = true
}

variable "max_receive_count" {
  description = "Number of times a message can be received before going to DLQ"
  type        = number
  default     = 3
}

# -----------------------------------------------------------------------------
# SNS Configuration
# -----------------------------------------------------------------------------
variable "enable_sns_notifications" {
  description = "Enable SNS notifications for real-time alerts"
  type        = bool
  default     = false
}

# -----------------------------------------------------------------------------
# CloudWatch Alarms
# -----------------------------------------------------------------------------
variable "enable_alarms" {
  description = "Enable CloudWatch alarms for monitoring"
  type        = bool
  default     = false
}

variable "queue_depth_alarm_threshold" {
  description = "Queue depth threshold for alarm"
  type        = number
  default     = 100
}

variable "alarm_actions" {
  description = "List of ARNs to notify when alarm triggers"
  type        = list(string)
  default     = []
}

variable "ok_actions" {
  description = "List of ARNs to notify when alarm returns to OK"
  type        = list(string)
  default     = []
}

# -----------------------------------------------------------------------------
# Tags
# -----------------------------------------------------------------------------
variable "tags" {
  description = "Additional tags for all resources"
  type        = map(string)
  default     = {}
}
