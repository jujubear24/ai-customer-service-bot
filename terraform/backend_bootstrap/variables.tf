variable "aws_region" {
  description = "The AWS region to deploy resources in."
  type        = string
}

variable "project_name" {
  description = "The unique name for this project."
  type        = string
}

variable "aws_account_id" {
  description = "The AWS Account ID. This is needed to ensure a globally unique bucket name."
  type        = string
}

variable "common_tags" {
  description = "A map of common tags to apply to all resources."
  type        = map(string)
  default     = {}
}
