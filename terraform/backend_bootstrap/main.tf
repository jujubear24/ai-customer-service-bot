#
# This is a one-time-run project to create the resources for
# our Terraform remote state backend.
#
# DO NOT destroy these resources unless you are migrating state.
#

terraform {
  # This project will use a local backend (a file) to create
  # the remote backend resources.
  backend "local" {
    path = "terraform.tfstate"
  }
}

# --- S3 Bucket for Terraform State ---
resource "aws_s3_bucket" "terraform_state" {
  bucket = "${var.project_name}-terraform-state-${var.aws_account_id}"

  tags = {
    Name        = "${var.project_name}-terraform-state"
    Project     = var.project_name
    ManagedBy   = "terraform"
    Description = "S3 bucket for storing remote Terraform state"
  }
}

# Block all public access to the state bucket
resource "aws_s3_bucket_public_access_block" "terraform_state" {
  bucket = aws_s3_bucket.terraform_state.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# Enable versioning on the state bucket
resource "aws_s3_bucket_versioning" "terraform_state" {
  bucket = aws_s3_bucket.terraform_state.id
  versioning_configuration {
    status = "Enabled"
  }
}

# Enable server-side encryption on the state bucket
resource "aws_s3_bucket_server_side_encryption_configuration" "terraform_state" {
  bucket = aws_s3_bucket.terraform_state.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

# --- KMS Key for Encryption ---
resource "aws_kms_key" "terraform_backend" {
  description             = "KMS key for encrypting Terraform backend resources (S3/DynamoDB)"
  deletion_window_in_days = 7
  enable_key_rotation     = true

  tags = merge(var.common_tags, {
    Name = "${var.project_name}-backend-key"
  })
}

# --- DynamoDB Table for State Locking ---
resource "aws_dynamodb_table" "terraform_locks" {
  name         = "${var.project_name}-terraform-locks"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "LockID"

  attribute {
    name = "LockID"
    type = "S"
  }

  server_side_encryption {
    enabled     = true
    kms_key_arn = aws_kms_key.terraform_backend.arn
  }

  tags = {
    Name        = "${var.project_name}-terraform-locks"
    Project     = var.project_name
    ManagedBy   = "terraform"
    Description = "DynamoDB table for Terraform state locking"
  }
}
