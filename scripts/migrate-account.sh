#!/bin/bash
# migrate-account.sh

set -e

NEW_ACCOUNT_ID="$1"
NEW_AWS_PROFILE="$2"

if [ -z "$NEW_ACCOUNT_ID" ] || [ -z "$NEW_AWS_PROFILE" ]; then
    echo "Usage: ./migrate-account.sh <new-account-id> <aws-profile-name>"
    exit 1
fi

echo "Migrating to account: $NEW_ACCOUNT_ID"
echo "Using AWS profile: $NEW_AWS_PROFILE"

# Set the AWS profile
export AWS_PROFILE="$NEW_AWS_PROFILE"

# Verify account
CURRENT_ACCOUNT=$(aws sts get-caller-identity --query Account --output text)
if [ "$CURRENT_ACCOUNT" != "$NEW_ACCOUNT_ID" ]; then
    echo "Error: Current AWS account ($CURRENT_ACCOUNT) doesn't match target ($NEW_ACCOUNT_ID)"
    exit 1
fi

echo "✓ Verified AWS account: $CURRENT_ACCOUNT"

# Update backend bootstrap tfvars
echo "Updating backend_bootstrap/terraform.tfvars..."
if [[ "$OSTYPE" == "darwin"* ]]; then
    # macOS
    sed -i '' "s/aws_account_id = \"[0-9]*\"/aws_account_id = \"$NEW_ACCOUNT_ID\"/" \
        terraform/backend_bootstrap/terraform.tfvars
else
    # Linux
    sed -i "s/aws_account_id = \"[0-9]*\"/aws_account_id = \"$NEW_ACCOUNT_ID\"/" \
        terraform/backend_bootstrap/terraform.tfvars
fi

# Update dev backend.tf
echo "Updating environments/dev/backend.tf..."
if [[ "$OSTYPE" == "darwin"* ]]; then
    # macOS
    sed -i '' "s/-state-[0-9]*\"/-state-$NEW_ACCOUNT_ID\"/" \
        terraform/environments/dev/backend.tf
else
    # Linux
    sed -i "s/-state-[0-9]*\"/-state-$NEW_ACCOUNT_ID\"/" \
        terraform/environments/dev/backend.tf
fi

# Clean up any existing terraform state in backend_bootstrap
echo "Cleaning up old Terraform state..."
cd terraform/backend_bootstrap
rm -rf .terraform
rm -f .terraform.lock.hcl
rm -f terraform.tfstate
rm -f terraform.tfstate.backup

echo "✓ Cleaned up old state files"

# Bootstrap backend
echo "Bootstrapping backend resources..."
terraform init
echo ""
echo "Running terraform apply..."
echo "Please review the plan and type 'yes' to proceed"
terraform apply

# Clean up dev environment state
echo "Cleaning up dev environment state..."
cd ../environments/dev
rm -rf .terraform
rm -f .terraform.lock.hcl

# Initialize dev environment
echo "Initializing dev environment..."
terraform init -reconfigure

echo ""
echo "✓ Migration setup complete!"
echo ""
echo "Next steps:"
echo "1. Review terraform/environments/dev/terraform.tfvars (especially alert_email)"
echo "2. Run: cd terraform/environments/dev && terraform plan"
echo "3. Run: terraform apply"
