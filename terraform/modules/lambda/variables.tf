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

# =============================================================================
# Layer Configuration
# =============================================================================

variable "create_layer" {
  description = "Whether to create a Lambda layer in this module instance"
  type        = bool
  default     = false
}

variable "layer_name" {
  description = "Name suffix for the Lambda layer (full name: {project}-{env}-{layer_name})"
  type        = string
  default     = null
}

variable "layer_zip_path" {
  description = "Path to the pre-built layer zip file (defaults to builds/{layer_name}.zip)"
  type        = string
  default     = null
}

variable "layer_compatible_runtimes" {
  description = "List of compatible runtimes for the layer"
  type        = list(string)
  default     = ["python3.12"]
}

variable "layer_description" {
  description = "Description for the Lambda layer"
  type        = string
  default     = "Shared dependencies layer"
}

# =============================================================================
# Function Configuration
# =============================================================================

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
