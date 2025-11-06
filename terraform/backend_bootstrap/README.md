# Terraform Backend Bootstrap

This standalone Terraform project is for a one-time setup to create the
remote backend resources (S3 bucket and DynamoDB table) required by all
other environments.

## Purpose

This project solves the "chicken-and-egg" problem of wanting to store
Terraform state in an S3 bucket, which itself must be created by Terraform.

This configuration uses a **local backend** (the default) just once
to create:

1. **S3 Bucket**: To store the `terraform.tfstate` files for `dev`,
   `staging`, and `prod`.

1. **DynamoDB Table**: To be used for state locking, preventing multiple
   engineers from running `terraform apply` at the same time.

1. **KMS Key**: To encrypt the state bucket and lock table.

## How to Use

1. Navigate to this directory:

```bash
   cd terraform/backend_bootstrap
```

1. Create your variables file:

```bash
   cp terraform.tfvars.example terraform.tfvars
```

1. Edit `terraform.tfvars` and add your 12-digit AWS Account ID.

1. Initialize and Apply:

```bash
   terraform init
   terraform apply
```

After running this once, you should not need to run it again. All other
environments (like `/terraform/environments/dev`) will now be configured to
point to the resources you just created.

<!-- markdownlint-disable -->
<!-- BEGINNING OF PRE-COMMIT-TERRAFORM DOCS HOOK -->
## Requirements

| Name | Version |
|------|---------|
| <a name="requirement_terraform"></a> [terraform](#requirement\_terraform) | >= 1.6.0 |
| <a name="requirement_aws"></a> [aws](#requirement\_aws) | ~> 5.0 |

## Providers

| Name | Version |
|------|---------|
| <a name="provider_aws"></a> [aws](#provider\_aws) | 5.100.0 |

## Modules

No modules.

## Resources

| Name | Type |
|------|------|
| [aws_dynamodb_table.terraform_locks](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/dynamodb_table) | resource |
| [aws_kms_key.terraform_backend](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/kms_key) | resource |
| [aws_s3_bucket.terraform_state](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/s3_bucket) | resource |
| [aws_s3_bucket_public_access_block.terraform_state](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/s3_bucket_public_access_block) | resource |
| [aws_s3_bucket_server_side_encryption_configuration.terraform_state](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/s3_bucket_server_side_encryption_configuration) | resource |
| [aws_s3_bucket_versioning.terraform_state](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/s3_bucket_versioning) | resource |

## Inputs

| Name | Description | Type | Default | Required |
|------|-------------|------|---------|:--------:|
| <a name="input_aws_account_id"></a> [aws\_account\_id](#input\_aws\_account\_id) | The AWS Account ID. This is needed to ensure a globally unique bucket name. | `string` | n/a | yes |
| <a name="input_aws_region"></a> [aws\_region](#input\_aws\_region) | The AWS region to deploy resources in. | `string` | n/a | yes |
| <a name="input_common_tags"></a> [common\_tags](#input\_common\_tags) | A map of common tags to apply to all resources. | `map(string)` | `{}` | no |
| <a name="input_project_name"></a> [project\_name](#input\_project\_name) | The unique name for this project. | `string` | n/a | yes |

## Outputs

No outputs.
<!-- END OF PRE-COMMIT-TERRAFORM DOCS HOOK -->
<!-- markdownlint-enable -->
