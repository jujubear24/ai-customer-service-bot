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
# Networking Configuration
# ==============================================================================

variable "vpc_cidr" {
  description = "The CIDR block for the VPC"
  type        = string
}

variable "availability_zones" {
  description = "A list of availability zones for the VPC"
  type        = list(string)
}

variable "private_subnet_cidrs" {
  description = "A list of CIDR blocks for private subnets"
  type        = list(string)
}

variable "public_subnet_cidrs" {
  description = "A list of CIDR blocks for public subnets"
  type        = list(string)
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
  description = "A map of common tags to apply to all resources"
  type        = map(string)
  default     = {}
}
