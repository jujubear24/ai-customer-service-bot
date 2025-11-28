variable "project_name" {
  description = "The name of the project"
  type        = string
}

variable "environment" {
  description = "The name of the environment"
  type        = string
}

variable "log_level" {
  description = "Log level for Lambda functions"
  type        = string
  default     = "INFO"
}

variable "metrics_namespace" {
  description = "CloudWatch metrics namespace"
  type        = string
  default     = "CustomerServiceBot"
}

variable "common_tags" {
  description = "Common tags for all resources"
  type        = map(string)
  default     = {}
}

variable "functions" {
  description = "Map of Lambda functions to deploy"
  type = map(object({
    handler                      = string
    runtime                      = string
    timeout                      = number
    memory_size                  = number
    environment_variables        = map(string)
    enable_xray                  = bool
    additional_layers            = list(string)
    additional_policy_arns       = list(string)
    additional_policy_statements = list(any)
  }))
  default = {}

  validation {
    condition     = alltrue([for k, v in var.functions : can(regex("^[a-z0-9-]+$", k))])
    error_message = "Function names must contain only lowercase letters, numbers, and hyphens."
  }
}
