#!/bin/bash
# Script to update all Lambda function pyproject.toml files
# Updates Ruff version and Python target version for consistency

set -e

# Colors
GREEN="\033[0;32m"
BLUE="\033[0;34m"
YELLOW="\033[1;33m"
NC="\033[0m"

echo -e "${BLUE}Updating Lambda function pyproject.toml files...${NC}"
echo ""

# Counter for updated files
UPDATED=0

# Find all pyproject.toml files in lambda/functions/*/
for pyproject in lambda/functions/*/pyproject.toml; do
    if [ -f "$pyproject" ]; then
        function_name=$(basename "$(dirname "$pyproject")")
        echo -e "${BLUE}Processing: $function_name${NC}"

        # Backup original file
        cp "$pyproject" "$pyproject.bak"

        # Update ruff version from 0.1.0 or 0.3.0 to 0.8.4
        if grep -q 'ruff>=0\.[13]\.0' "$pyproject"; then
            sed -i.tmp 's/ruff>=0\.[13]\.0/ruff>=0.8.4/g' "$pyproject"
            echo -e "  ${GREEN}✓${NC} Updated ruff version to 0.8.4"
        fi

        # Update Python target version from py311 to py312
        if grep -q 'target-version = "py311"' "$pyproject"; then
            sed -i.tmp 's/target-version = "py311"/target-version = "py312"/g' "$pyproject"
            echo -e "  ${GREEN}✓${NC} Updated target-version to py312"
        fi

        # Clean up temp files
        rm -f "$pyproject.tmp"

        # Check if file was actually modified
        if ! diff -q "$pyproject" "$pyproject.bak" > /dev/null 2>&1; then
            echo -e "  ${GREEN}✓${NC} File updated"
            UPDATED=$((UPDATED + 1))
            rm "$pyproject.bak"
        else
            echo -e "  ${YELLOW}○${NC} No changes needed"
            mv "$pyproject.bak" "$pyproject"  # Restore original
        fi

        echo ""
    fi
done

echo -e "${GREEN}================================${NC}"
echo -e "${GREEN}Summary:${NC}"
echo -e "  Updated: $UPDATED file(s)"
echo -e "${GREEN}================================${NC}"

if [ $UPDATED -gt 0 ]; then
    echo ""
    echo -e "${BLUE}Don't forget to sync dependencies:${NC}"
    echo "  uv sync --all-packages"
    echo ""
    echo -e "${BLUE}Or from project root with dev dependencies:${NC}"
    echo "  uv sync --all-packages --all-extras"
fi
