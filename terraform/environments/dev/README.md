# Dev Environment

This is the development environment configuration for the AI Customer Service Bot project.

## Overview

This environment includes:

- VPC with public and private subnets across 2 availability zones
- NAT Gateway for private subnet internet access
- CloudWatch logging and monitoring
- Budget alerts and cost tracking
- Synthetics canary for health checks

## Usage

### Initialize

```bash
cd terraform/environments/dev
terraform init
```

### Plan Changes

```bash
terraform plan
```

### Apply Changes

```bash
terraform apply
```

### View Outputs

```bash
terraform output
```

## Configuration

Edit `terraform.tfvars` to customize:

- VPC CIDR blocks
- Subnet configurations
- Budget limits
- Alert email addresses
- Tags

## Resources

This environment creates the following resources:

- **Networking Module**: VPC, subnets, NAT gateway, internet gateway, route tables, security groups
- **Observability Module**: CloudWatch log groups, dashboards, alarms, SNS topics, budgets, synthetics canary

For detailed module documentation, see:

- [Networking Module](../../modules/networking/README.md)
- [Observability Module](../../modules/observability/README.md)

## Outputs

After deployment, you can view outputs with:

```bash
terraform output
```

Available outputs:

- `vpc_id` - The ID of the VPC
- `private_subnet_ids` - List of private subnet IDs
- `public_subnet_ids` - List of public subnet IDs
- `default_security_group_id` - The ID of the default security group
- `sns_topic_arn` - The ARN of the SNS alerting topic
- `cloudwatch_kms_key_arn` - The ARN of the KMS key used for CloudWatch logs
- `canary_name` - Name of the heartbeat canary
