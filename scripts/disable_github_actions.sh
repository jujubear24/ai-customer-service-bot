#!/bin/bash
# Script to disable GitHub Actions workflows during development

set -e

GREEN="\033[0;32m"
BLUE="\033[0;34m"
NC="\033[0m"

echo -e "${BLUE}Disabling GitHub Actions workflows...${NC}"
echo ""

# Disable workflows by renaming
if [ -f ".github/workflows/ci.yml" ]; then
    mv .github/workflows/ci.yml .github/workflows/ci.yml.disabled
    echo -e "${GREEN}✓${NC} Disabled ci.yml"
fi

if [ -f ".github/workflows/lambda-test.yml" ]; then
    mv .github/workflows/lambda-test.yml .github/workflows/lambda-test.yml.disabled
    echo -e "${GREEN}✓${NC} Disabled lambda-test.yml"
fi

echo ""
echo -e "${BLUE}Workflows disabled. To re-enable:${NC}"
echo "  mv .github/workflows/ci.yml.disabled .github/workflows/ci.yml"
echo "  mv .github/workflows/lambda-test.yml.disabled .github/workflows/lambda-test.yml"
