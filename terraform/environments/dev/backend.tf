# The S3 bucket and DynamoDB table must be created first
# by running the /terraform/backend_bootstrap project.

terraform {
  backend "s3" {
    # This bucket name must match the one created by backend_bootstrap
    bucket = "ai-customer-service-bot-terraform-state-288232812020"

    key    = "dev/terraform.tfstate"
    region = "us-east-1"

    # This table name must match the one created by backend_bootstrap
    dynamodb_table = "ai-customer-service-bot-terraform-locks"
    encrypt        = true
  }
}
