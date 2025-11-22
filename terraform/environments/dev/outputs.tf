# ==============================================================================
# Networking Outputs
# ==============================================================================

output "vpc_id" {
  description = "The ID of the VPC"
  value       = module.networking.vpc_id
}

output "private_subnet_ids" {
  description = "List of private subnet IDs"
  value       = module.networking.private_subnet_ids
}

output "public_subnet_ids" {
  description = "List of public subnet IDs"
  value       = module.networking.public_subnet_ids
}

output "default_security_group_id" {
  description = "The ID of the default security group"
  value       = module.networking.default_security_group_id
}

# ==============================================================================
# Observability Outputs
# ==============================================================================

output "sns_topic_arn" {
  description = "The ARN of the SNS alerting topic"
  value       = module.observability.sns_topic_arn
}

output "cloudwatch_kms_key_arn" {
  description = "The ARN of the KMS key used for CloudWatch logs"
  value       = module.observability.cloudwatch_kms_key_arn
}

output "canary_name" {
  description = "Name of the heartbeat canary"
  value       = module.observability.canary_name
}
