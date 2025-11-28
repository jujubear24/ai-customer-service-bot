output "table_name" {
  description = "Name of the DynamoDB table"
  value       = aws_dynamodb_table.conversations.name
}

output "table_arn" {
  description = "ARN of the DynamoDB table"
  value       = aws_dynamodb_table.conversations.arn
}

output "table_stream_arn" {
  description = "ARN of the DynamoDB stream"
  value       = aws_dynamodb_table.conversations.stream_arn
}

output "table_stream_label" {
  description = "Label of the DynamoDB stream"
  value       = aws_dynamodb_table.conversations.stream_label
}

output "iam_policy_arn" {
  description = "ARN of the IAM policy for DynamoDB access"
  value       = aws_iam_policy.dynamodb_access.arn
}

output "gsi1_name" {
  description = "Name of GSI1 (user queries)"
  value       = "GSI1"
}

output "gsi2_name" {
  description = "Name of GSI2 (status queries)"
  value       = "GSI2"
}
