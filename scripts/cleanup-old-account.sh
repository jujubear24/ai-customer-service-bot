#!/bin/bash
# Cleanup script for old AWS account

set -e

echo "=========================================="
echo "AWS Resource Cleanup Script"
echo "=========================================="
echo ""
echo "Current account: $(aws sts get-caller-identity --query Account --output text)"
echo ""
echo "⚠️  WARNING: This will delete ALL ai-customer-service-bot resources"
echo ""
read -p "Type 'DELETE' to confirm: " confirm

if [ "$confirm" != "DELETE" ]; then
    echo "❌ Aborted"
    exit 1
fi

echo ""
echo "🗑️  Starting cleanup..."
echo ""

# Function to handle errors gracefully
run_cmd() {
    local desc=$1
    shift
    echo "▶ $desc"
    if "$@" 2>/dev/null; then
        echo "  ✓ Success"
    else
        echo "  ⚠ Skipped (not found or already deleted)"
    fi
}

# Delete Synthetics Canary
run_cmd "Deleting canary" \
    aws synthetics delete-canary --name api-heartbeat-dev

# Delete CloudWatch Dashboard
run_cmd "Deleting CloudWatch dashboard" \
    aws cloudwatch delete-dashboards --dashboard-names ai-customer-service-bot-dashboard-dev

# Delete CloudWatch Alarms
run_cmd "Deleting CloudWatch alarm" \
    aws cloudwatch delete-alarms --alarm-names ai-customer-service-bot-aggregate-lambda-errors-dev

# Delete CloudWatch Log Groups
echo "▶ Deleting CloudWatch log groups"
LOG_GROUPS=$(aws logs describe-log-groups --log-group-name-prefix "/aws/lambda/ai-customer-service-bot" --query 'logGroups[*].logGroupName' --output text 2>/dev/null || echo "")
if [ -n "$LOG_GROUPS" ]; then
    for log_group in $LOG_GROUPS; do
        aws logs delete-log-group --log-group-name "$log_group" 2>/dev/null && echo "  ✓ Deleted $log_group" || true
    done
else
    echo "  ⚠ No log groups found"
fi

# Delete SNS Topic
run_cmd "Deleting SNS topic" \
    aws sns delete-topic --topic-arn "arn:aws:sns:us-east-1:288232812020:ai-customer-service-bot-alerts-dev"

# Delete Budget
run_cmd "Deleting budget" \
    aws budgets delete-budget --account-id 288232812020 --budget-name ai-customer-service-bot-monthly-budget-dev

# Delete IAM Role
echo "▶ Deleting IAM role"
aws iam delete-role-policy --role-name ai-customer-service-bot-canary-role-dev --policy-name ai-customer-service-bot-canary-policy-dev 2>/dev/null && echo "  ✓ Deleted role policy" || true
aws iam delete-role --role-name ai-customer-service-bot-canary-role-dev 2>/dev/null && echo "  ✓ Deleted role" || echo "  ⚠ Role not found"

# Find VPC
echo "▶ Finding VPC"
VPC_ID=$(aws ec2 describe-vpcs --filters "Name=tag:Project,Values=ai-customer-service-bot" --query 'Vpcs[0].VpcId' --output text 2>/dev/null || echo "None")

if [ "$VPC_ID" != "None" ] && [ -n "$VPC_ID" ]; then
    echo "  ✓ Found VPC: $VPC_ID"

    # Delete NAT Gateway
    echo "▶ Deleting NAT Gateway"
    NAT_ID=$(aws ec2 describe-nat-gateways --filter "Name=vpc-id,Values=$VPC_ID" "Name=state,Values=available" --query 'NatGateways[0].NatGatewayId' --output text 2>/dev/null || echo "None")

    if [ "$NAT_ID" != "None" ] && [ -n "$NAT_ID" ]; then
        aws ec2 delete-nat-gateway --nat-gateway-id $NAT_ID
        echo "  ⏳ Waiting for NAT Gateway to delete (this takes ~2 minutes)..."
        aws ec2 wait nat-gateway-deleted --nat-gateway-ids $NAT_ID 2>/dev/null || sleep 120
        echo "  ✓ NAT Gateway deleted"
    else
        echo "  ⚠ No NAT Gateway found"
    fi

    # Release Elastic IP
    echo "▶ Releasing Elastic IP"
    EIP_ALLOC_ID=$(aws ec2 describe-addresses --filters "Name=tag:Project,Values=ai-customer-service-bot" --query 'Addresses[0].AllocationId' --output text 2>/dev/null || echo "None")

    if [ "$EIP_ALLOC_ID" != "None" ] && [ -n "$EIP_ALLOC_ID" ]; then
        aws ec2 release-address --allocation-id $EIP_ALLOC_ID 2>/dev/null && echo "  ✓ Released EIP" || echo "  ⚠ EIP already released"
    else
        echo "  ⚠ No EIP found"
    fi

    # Delete Internet Gateway
    echo "▶ Deleting Internet Gateway"
    IGW_ID=$(aws ec2 describe-internet-gateways --filters "Name=attachment.vpc-id,Values=$VPC_ID" --query 'InternetGateways[0].InternetGatewayId' --output text 2>/dev/null || echo "None")

    if [ "$IGW_ID" != "None" ] && [ -n "$IGW_ID" ]; then
        aws ec2 detach-internet-gateway --internet-gateway-id $IGW_ID --vpc-id $VPC_ID 2>/dev/null || true
        aws ec2 delete-internet-gateway --internet-gateway-id $IGW_ID 2>/dev/null && echo "  ✓ Deleted IGW" || true
    fi

    # Delete Subnets
    echo "▶ Deleting Subnets"
    SUBNET_IDS=$(aws ec2 describe-subnets --filters "Name=vpc-id,Values=$VPC_ID" --query 'Subnets[*].SubnetId' --output text 2>/dev/null || echo "")
    if [ -n "$SUBNET_IDS" ]; then
        for subnet in $SUBNET_IDS; do
            aws ec2 delete-subnet --subnet-id $subnet 2>/dev/null && echo "  ✓ Deleted $subnet" || true
        done
    fi

    # Delete Route Tables
    echo "▶ Deleting Route Tables"
    RT_IDS=$(aws ec2 describe-route-tables --filters "Name=vpc-id,Values=$VPC_ID" --query 'RouteTables[?Associations[0].Main!=`true`].RouteTableId' --output text 2>/dev/null || echo "")
    if [ -n "$RT_IDS" ]; then
        for rt in $RT_IDS; do
            aws ec2 delete-route-table --route-table-id $rt 2>/dev/null && echo "  ✓ Deleted $rt" || true
        done
    fi

    # Delete Security Groups
    echo "▶ Deleting Security Groups"
    SG_IDS=$(aws ec2 describe-security-groups --filters "Name=vpc-id,Values=$VPC_ID" --query 'SecurityGroups[?GroupName!=`default`].GroupId' --output text 2>/dev/null || echo "")
    if [ -n "$SG_IDS" ]; then
        for sg in $SG_IDS; do
            aws ec2 delete-security-group --group-id $sg 2>/dev/null && echo "  ✓ Deleted $sg" || true
        done
    fi

    # Delete VPC
    echo "▶ Deleting VPC"
    aws ec2 delete-vpc --vpc-id $VPC_ID && echo "  ✓ VPC deleted" || echo "  ⚠ Failed to delete VPC (may have dependencies)"
else
    echo "  ⚠ No VPC found"
fi

# Delete S3 Buckets
echo "▶ Deleting S3 buckets"
BUCKETS=$(aws s3 ls | grep "ai-customer-service-bot" | awk '{print $3}' || echo "")

if [ -n "$BUCKETS" ]; then
    for bucket in $BUCKETS; do
        echo "  📦 Processing $bucket"
        aws s3 rm "s3://$bucket" --recursive 2>/dev/null || true
        aws s3 rb "s3://$bucket" 2>/dev/null && echo "  ✓ Deleted $bucket" || echo "  ⚠ Failed to delete $bucket"
    done
else
    echo "  ⚠ No buckets found"
fi

# Delete DynamoDB Table
run_cmd "Deleting DynamoDB table" \
    aws dynamodb delete-table --table-name ai-customer-service-bot-terraform-locks

# Schedule KMS Key Deletion
echo "▶ Scheduling KMS key deletion"
KEY_ID=$(aws kms list-aliases --query "Aliases[?AliasName=='alias/ai-customer-service-bot-cloudwatch-key-dev'].TargetKeyId" --output text 2>/dev/null || echo "")

if [ -n "$KEY_ID" ] && [ "$KEY_ID" != "None" ]; then
    aws kms schedule-key-deletion --key-id "$KEY_ID" --pending-window-in-days 7 2>/dev/null && echo "  ✓ KMS key scheduled for deletion in 7 days" || echo "  ⚠ Failed to schedule key deletion"
else
    echo "  ⚠ No KMS key found"
fi

echo ""
echo "=========================================="
echo "✅ Cleanup Complete!"
echo "=========================================="
echo ""
echo "Summary:"
echo "  • VPC and networking resources deleted"
echo "  • CloudWatch resources deleted"
echo "  • S3 buckets emptied and deleted"
echo "  • DynamoDB table deleted"
echo "  • IAM roles deleted"
echo "  • KMS key scheduled for deletion (7 days)"
echo ""
echo "Note: Some resources may take a few minutes to fully delete."
