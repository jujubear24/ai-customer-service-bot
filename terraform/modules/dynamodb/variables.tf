variable "environment" {
  description = "Environment name (dev, staging, prod)"
  type        = string
}

variable "table_name" {
  description = "DynamoDB table name"
  type        = string
  default     = "conversations"
}

variable "billing_mode" {
  description = "DynamoDB billing mode (PROVISIONED or PAY_PER_REQUEST)"
  type        = string
  default     = "PAY_PER_REQUEST"

  validation {
    condition     = contains(["PROVISIONED", "PAY_PER_REQUEST"], var.billing_mode)
    error_message = "billing_mode must be PROVISIONED or PAY_PER_REQUEST"
  }
}

variable "read_capacity" {
  description = "Read capacity units (only used with PROVISIONED billing)"
  type        = number
  default     = 5
}

variable "write_capacity" {
  description = "Write capacity units (only used with PROVISIONED billing)"
  type        = number
  default     = 5
}

variable "gsi_read_capacity" {
  description = "GSI read capacity units (only used with PROVISIONED billing)"
  type        = number
  default     = 5
}

variable "gsi_write_capacity" {
  description = "GSI write capacity units (only used with PROVISIONED billing)"
  type        = number
  default     = 5
}

variable "stream_enabled" {
  description = "Enable DynamoDB Streams"
  type        = bool
  default     = true
}

variable "enable_point_in_time_recovery" {
  description = "Enable point-in-time recovery"
  type        = bool
  default     = false
}

variable "kms_key_arn" {
  description = "KMS key ARN for encryption (uses AWS managed key if not provided)"
  type        = string
  default     = null
}

variable "enable_alarms" {
  description = "Enable CloudWatch alarms"
  type        = bool
  default     = true
}

variable "alarm_sns_topic_arn" {
  description = "SNS topic ARN for alarm notifications"
  type        = string
  default     = null
}

variable "tags" {
  description = "Tags to apply to resources"
  type        = map(string)
  default     = {}
}
