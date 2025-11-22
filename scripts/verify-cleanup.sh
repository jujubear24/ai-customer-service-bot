#!/bin/bash

echo "=========================================="
echo "Verification Report"
echo "=========================================="
echo ""
echo "Account: $(aws sts get-caller-identity --query Account --output text)"
echo ""

verify_resource() {
    local name=$1
    local command=$2

    echo "$name:"
    result=$(eval "$command" 2>/dev/null)
    if [ -z "$result" ] || [ "$result" = "[]" ] || [ "$result" = "None" ]; then
        echo "   ✓ None found"
    else
        echo "$result"
    fi
    echo ""
}

verify_resource "1. VPCs" \
    "aws ec2 describe-vpcs --filters 'Name=tag:Project,Values=ai-customer-service-bot' --query 'Vpcs[*].VpcId' --output text"

verify_resource "2. S3 Buckets" \
    "aws s3 ls | grep 'ai-customer-service-bot'"

verify_resource "3. DynamoDB Tables" \
    "aws dynamodb list-tables --query 'TableNames[?contains(@, \`ai-customer-service-bot\`)]' --output text"

verify_resource "4. CloudWatch Log Groups" \
    "aws logs describe-log-groups --log-group-name-prefix '/aws/lambda/ai-customer-service-bot' --query 'logGroups[*].logGroupName' --output text"

verify_resource "5. CloudWatch Dashboards" \
    "aws cloudwatch list-dashboards --query 'DashboardEntries[?contains(DashboardName, \`ai-customer-service-bot\`)].DashboardName' --output text"

verify_resource "6. SNS Topics" \
    "aws sns list-topics --query 'Topics[?contains(TopicArn, \`ai-customer-service-bot\`)].TopicArn' --output text"

verify_resource "7. IAM Roles" \
    "aws iam list-roles --query 'Roles[?contains(RoleName, \`ai-customer-service-bot\`)].RoleName' --output text"

verify_resource "8. Synthetics Canaries" \
    "aws synthetics describe-canaries --query 'Canaries[?contains(Name, \`heartbeat\`)].Name' --output text"

verify_resource "9. NAT Gateways" \
    "aws ec2 describe-nat-gateways --filter 'Name=tag:Project,Values=ai-customer-service-bot' --query 'NatGateways[*].NatGatewayId' --output text"

verify_resource "10. Elastic IPs" \
    "aws ec2 describe-addresses --filters 'Name=tag:Project,Values=ai-customer-service-bot' --query 'Addresses[*].AllocationId' --output text"

verify_resource "11. Budgets" \
    "aws budgets describe-budgets --account-id $(aws sts get-caller-identity --query Account --output text) --query 'Budgets[?contains(BudgetName, \`ai-customer-service-bot\`)].BudgetName' --output text"

echo "=========================================="
echo "Verification Complete"
echo "=========================================="
