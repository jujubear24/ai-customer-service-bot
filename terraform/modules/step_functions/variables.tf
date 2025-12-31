# ==============================================================================
# Required Variables
# ==============================================================================

variable "project_name" {
  description = "Name of the project (used for resource naming)"
  type        = string
}

variable "environment" {
  description = "Environment name (dev, staging, prod)"
  type        = string
}

variable "region" {
  description = "AWS region"
  type        = string
}

variable "account_id" {
  description = "AWS account ID"
  type        = string
}

# ==============================================================================
# Lambda Function ARNs
# ==============================================================================

variable "intent_classifier_arn" {
  description = "ARN of the Intent Classifier Lambda function"
  type        = string
}

variable "context_builder_arn" {
  description = "ARN of the Context Builder Lambda function"
  type        = string
}

variable "rag_retriever_arn" {
  description = "ARN of the RAG Retriever Lambda function"
  type        = string
}

variable "bedrock_handler_arn" {
  description = "ARN of the Bedrock Handler Lambda function"
  type        = string
}

variable "response_validator_arn" {
  description = "ARN of the Response Validator Lambda function"
  type        = string
}

variable "escalation_router_arn" {
  description = "ARN of the Escalation Router Lambda function"
  type        = string
}

# ==============================================================================
# Optional Configuration
# ==============================================================================

variable "log_retention_days" {
  description = "Number of days to retain Step Functions logs"
  type        = number
  default     = 7
}

variable "log_level" {
  description = "Logging level for Step Functions (ALL, ERROR, FATAL, OFF)"
  type        = string
  default     = "ALL"

  validation {
    condition     = contains(["ALL", "ERROR", "FATAL", "OFF"], var.log_level)
    error_message = "log_level must be one of: ALL, ERROR, FATAL, OFF"
  }
}

variable "enable_xray_tracing" {
  description = "Enable X-Ray tracing for Step Functions"
  type        = bool
  default     = true
}

variable "include_execution_data" {
  description = "Include execution data in CloudWatch logs"
  type        = bool
  default     = true
}

# ==============================================================================
# Tags
# ==============================================================================

variable "tags" {
  description = "Tags to apply to all resources"
  type        = map(string)
  default     = {}
}
