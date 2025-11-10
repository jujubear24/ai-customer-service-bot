output "vpc_id" {
  description = "The ID of the created VPC."
  value       = aws_vpc.main.id
}

output "public_subnet_ids" {
  description = "A list of IDs for the public subnets."
  value       = [for subnet in aws_subnet.public : subnet.id]
}

output "private_subnet_ids" {
  description = "A list of IDs for the private subnets."
  value       = [for subnet in aws_subnet.private : subnet.id]
}

output "default_security_group_id" {
  description = "The ID of the default security group for the VPC."
  value       = aws_security_group.default.id
}
