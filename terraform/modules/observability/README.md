# observability

<!-- BEGINNING OF PRE-COMMIT-TERRAFORM DOCS HOOK -->
## Requirements

| Name | Version |
|------|---------|
| <a name="requirement_terraform"></a> [terraform](#requirement\_terraform) | >= 1.6.0 |
| <a name="requirement_archive"></a> [archive](#requirement\_archive) | ~> 2.0 |
| <a name="requirement_aws"></a> [aws](#requirement\_aws) | ~> 5.0 |

## Providers

| Name | Version |
|------|---------|
| <a name="provider_archive"></a> [archive](#provider\_archive) | 2.7.1 |
| <a name="provider_aws"></a> [aws](#provider\_aws) | 5.100.0 |

## Modules

No modules.

## Resources

| Name | Type |
|------|------|
| [aws_budgets_budget.cost](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/budgets_budget) | resource |
| [aws_cloudwatch_dashboard.main](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/cloudwatch_dashboard) | resource |
| [aws_cloudwatch_log_group.lambda_logs](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/cloudwatch_log_group) | resource |
| [aws_cloudwatch_metric_alarm.aggregate_lambda_errors](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/cloudwatch_metric_alarm) | resource |
| [aws_iam_role.canary](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/iam_role) | resource |
| [aws_iam_role_policy.canary](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/iam_role_policy) | resource |
| [aws_kms_alias.cloudwatch](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/kms_alias) | resource |
| [aws_kms_key.cloudwatch](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/kms_key) | resource |
| [aws_s3_bucket.canary_artifacts](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/s3_bucket) | resource |
| [aws_s3_bucket_lifecycle_configuration.canary_artifacts](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/s3_bucket_lifecycle_configuration) | resource |
| [aws_sns_topic.alerts](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/sns_topic) | resource |
| [aws_synthetics_canary.heartbeat](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/synthetics_canary) | resource |
| [archive_file.canary_zip](https://registry.terraform.io/providers/hashicorp/archive/latest/docs/data-sources/file) | data source |
| [aws_caller_identity.current](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/data-sources/caller_identity) | data source |
| [aws_region.current](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/data-sources/region) | data source |

## Inputs

| Name | Description | Type | Default | Required |
|------|-------------|------|---------|:--------:|
| <a name="input_alert_emails"></a> [alert\_emails](#input\_alert\_emails) | List of email addresses to receive budget alerts | `list(string)` | n/a | yes |
| <a name="input_budget_amount"></a> [budget\_amount](#input\_budget\_amount) | The monthly budget limit in USD | `string` | n/a | yes |
| <a name="input_common_tags"></a> [common\_tags](#input\_common\_tags) | Common tags for all resources | `map(string)` | `{}` | no |
| <a name="input_environment"></a> [environment](#input\_environment) | The name of the environment | `string` | n/a | yes |
| <a name="input_lambda_functions"></a> [lambda\_functions](#input\_lambda\_functions) | List of Lambda function names to pre-create log groups for | `list(string)` | `[]` | no |
| <a name="input_log_retention_days"></a> [log\_retention\_days](#input\_log\_retention\_days) | Number of days to retain CloudWatch logs | `number` | `14` | no |
| <a name="input_project_name"></a> [project\_name](#input\_project\_name) | The name of the project | `string` | n/a | yes |

## Outputs

| Name | Description |
|------|-------------|
| <a name="output_canary_name"></a> [canary\_name](#output\_canary\_name) | Name of the heartbeat canary |
| <a name="output_cloudwatch_kms_key_arn"></a> [cloudwatch\_kms\_key\_arn](#output\_cloudwatch\_kms\_key\_arn) | The ARN of the KMS key used for CloudWatch logs |
| <a name="output_sns_topic_arn"></a> [sns\_topic\_arn](#output\_sns\_topic\_arn) | The ARN of the SNS alerting topic |
<!-- END OF PRE-COMMIT-TERRAFORM DOCS HOOK -->
