#!/bin/bash
#
# Setup Aurora PostgreSQL for Bedrock Knowledge Base
# Creates pgvector extension, table, and indexes required by Bedrock KB
#
# Usage:
#   ./scripts/setup-aurora-pgvector.sh
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  Aurora pgvector Setup${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""

# Configuration
CLUSTER_IDENTIFIER="ai-customer-service-bot-dev-kb-cluster"
DB_NAME="knowledgebase"
TABLE_NAME="bedrock_knowledge_base"
VECTOR_DIMENSIONS=512

# Get cluster ARN
echo -e "${YELLOW}Getting cluster ARN...${NC}"
CLUSTER_ARN=$(aws rds describe-db-clusters \
  --db-cluster-identifier "$CLUSTER_IDENTIFIER" \
  --query 'DBClusters[0].DBClusterArn' \
  --output text 2>/dev/null)

if [ -z "$CLUSTER_ARN" ] || [ "$CLUSTER_ARN" == "None" ]; then
  echo -e "${RED}Error: Could not find cluster '$CLUSTER_IDENTIFIER'${NC}"
  echo "Make sure terraform apply has created the Aurora cluster first."
  exit 1
fi
echo "  Cluster ARN: $CLUSTER_ARN"

# Get secret ARN
echo -e "${YELLOW}Getting secret ARN...${NC}"
SECRET_ARN=$(aws secretsmanager list-secrets \
  --query "SecretList[?contains(Name, 'kb-aurora-credentials')].ARN | [0]" \
  --output text 2>/dev/null)

if [ -z "$SECRET_ARN" ] || [ "$SECRET_ARN" == "None" ]; then
  echo -e "${RED}Error: Could not find Aurora credentials secret${NC}"
  exit 1
fi
echo "  Secret ARN: $SECRET_ARN"

echo ""

# Create pgvector extension
echo -e "${YELLOW}[1/4] Creating pgvector extension...${NC}"
aws rds-data execute-statement \
  --resource-arn "$CLUSTER_ARN" \
  --secret-arn "$SECRET_ARN" \
  --database "$DB_NAME" \
  --sql "CREATE EXTENSION IF NOT EXISTS vector;" \
  --output text > /dev/null

echo -e "${GREEN}  ✓ pgvector extension created${NC}"

# Create table
echo -e "${YELLOW}[2/4] Creating knowledge base table...${NC}"
aws rds-data execute-statement \
  --resource-arn "$CLUSTER_ARN" \
  --secret-arn "$SECRET_ARN" \
  --database "$DB_NAME" \
  --sql "
    CREATE TABLE IF NOT EXISTS $TABLE_NAME (
      id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
      embedding vector($VECTOR_DIMENSIONS),
      content TEXT,
      metadata JSONB
    );" \
  --output text > /dev/null

echo -e "${GREEN}  ✓ Table '$TABLE_NAME' created${NC}"

# Create vector index
echo -e "${YELLOW}[3/4] Creating vector index...${NC}"
aws rds-data execute-statement \
  --resource-arn "$CLUSTER_ARN" \
  --secret-arn "$SECRET_ARN" \
  --database "$DB_NAME" \
  --sql "
    CREATE INDEX IF NOT EXISTS ${TABLE_NAME}_embedding_idx
    ON $TABLE_NAME
    USING hnsw (embedding vector_cosine_ops);" \
  --output text > /dev/null

echo -e "${GREEN}  ✓ Vector index created${NC}"

# Create content text search index (required by Bedrock)
echo -e "${YELLOW}[4/4] Creating content text search index...${NC}"
aws rds-data execute-statement \
  --resource-arn "$CLUSTER_ARN" \
  --secret-arn "$SECRET_ARN" \
  --database "$DB_NAME" \
  --sql "
    CREATE INDEX IF NOT EXISTS ${TABLE_NAME}_content_idx
    ON $TABLE_NAME
    USING gin (to_tsvector('simple', content));" \
  --output text > /dev/null

echo -e "${GREEN}  ✓ Content text search index created${NC}"

echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  Setup Complete!${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo -e "${YELLOW}Next steps:${NC}"
echo "  1. Run: cd $PROJECT_ROOT/terraform/environments/dev && terraform apply"
echo "  2. Upload docs: $PROJECT_ROOT/scripts/sync-knowledge-base.sh"
echo ""
