#!/usr/bin/env bash
# =============================================================================
# Knowledge Base Sync Script
# =============================================================================
# Uploads documents to S3 and triggers knowledge base sync
#
# Usage:
#   ./sync-knowledge-base.sh [--upload-only] [--sync-only]
#
# Environment variables:
#   ENVIRONMENT - Target environment (default: dev)
#   DOCS_PATH   - Path to documents directory (default: ./knowledge-base-docs)
# =============================================================================

set -euo pipefail

# Configuration
ENVIRONMENT="${ENVIRONMENT:-dev}"
DOCS_PATH="${DOCS_PATH:-./knowledge-base-docs}"
TERRAFORM_DIR="./terraform/environments/${ENVIRONMENT}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Parse arguments
UPLOAD_ONLY=false
SYNC_ONLY=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --upload-only)
            UPLOAD_ONLY=true
            shift
            ;;
        --sync-only)
            SYNC_ONLY=true
            shift
            ;;
        *)
            log_error "Unknown option: $1"
            exit 1
            ;;
    esac
done

# Get Terraform outputs
log_info "Getting Terraform outputs from ${TERRAFORM_DIR}..."

if ! cd "${TERRAFORM_DIR}"; then
    log_error "Terraform directory not found: ${TERRAFORM_DIR}"
    exit 1
fi

BUCKET_NAME=$(terraform output -raw s3_bucket_name 2>/dev/null || echo "")
KB_ID=$(terraform output -raw knowledge_base_id 2>/dev/null || echo "")
DS_ID=$(terraform output -raw data_source_id 2>/dev/null || echo "")

cd - > /dev/null

if [[ -z "${BUCKET_NAME}" ]]; then
    log_error "Could not get S3 bucket name from Terraform outputs"
    exit 1
fi

if [[ -z "${KB_ID}" ]]; then
    log_error "Could not get Knowledge Base ID from Terraform outputs"
    exit 1
fi

log_info "S3 Bucket: ${BUCKET_NAME}"
log_info "Knowledge Base ID: ${KB_ID}"
log_info "Data Source ID: ${DS_ID}"

# Upload documents
if [[ "${SYNC_ONLY}" != "true" ]]; then
    if [[ ! -d "${DOCS_PATH}" ]]; then
        log_error "Documents directory not found: ${DOCS_PATH}"
        exit 1
    fi

    log_info "Uploading documents from ${DOCS_PATH}..."

    # Upload FAQs
    if [[ -d "${DOCS_PATH}/faqs" ]]; then
        log_info "Uploading FAQs..."
        aws s3 sync "${DOCS_PATH}/faqs/" "s3://${BUCKET_NAME}/faqs/" \
            --delete \
            --exclude ".*" \
            --exclude "*.pyc"
    fi

    # Upload docs
    if [[ -d "${DOCS_PATH}/docs" ]]; then
        log_info "Uploading documentation..."
        aws s3 sync "${DOCS_PATH}/docs/" "s3://${BUCKET_NAME}/docs/" \
            --delete \
            --exclude ".*" \
            --exclude "*.pyc"
    fi

    log_info "Upload complete!"
fi

# Trigger sync
if [[ "${UPLOAD_ONLY}" != "true" ]]; then
    log_info "Starting knowledge base ingestion job..."

    JOB_RESPONSE=$(aws bedrock-agent start-ingestion-job \
        --knowledge-base-id "${KB_ID}" \
        --data-source-id "${DS_ID}" \
        --output json)

    JOB_ID=$(echo "${JOB_RESPONSE}" | jq -r '.ingestionJob.ingestionJobId')
    log_info "Ingestion job started: ${JOB_ID}"

    # Wait for job completion
    log_info "Waiting for ingestion to complete..."

    while true; do
        JOB_STATUS=$(aws bedrock-agent get-ingestion-job \
            --knowledge-base-id "${KB_ID}" \
            --data-source-id "${DS_ID}" \
            --ingestion-job-id "${JOB_ID}" \
            --query 'ingestionJob.status' \
            --output text)

        case "${JOB_STATUS}" in
            "COMPLETE")
                log_info "Ingestion completed successfully!"
                break
                ;;
            "FAILED")
                log_error "Ingestion failed!"
                aws bedrock-agent get-ingestion-job \
                    --knowledge-base-id "${KB_ID}" \
                    --data-source-id "${DS_ID}" \
                    --ingestion-job-id "${JOB_ID}" \
                    --query 'ingestionJob.failureReasons' \
                    --output text
                exit 1
                ;;
            "IN_PROGRESS"|"STARTING")
                echo -n "."
                sleep 5
                ;;
            *)
                log_warn "Unknown status: ${JOB_STATUS}"
                sleep 5
                ;;
        esac
    done

    # Show statistics
    log_info "Ingestion statistics:"
    aws bedrock-agent get-ingestion-job \
        --knowledge-base-id "${KB_ID}" \
        --data-source-id "${DS_ID}" \
        --ingestion-job-id "${JOB_ID}" \
        --query 'ingestionJob.statistics' \
        --output table
fi

log_info "Done!"
