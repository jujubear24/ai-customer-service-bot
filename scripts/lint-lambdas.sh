#!/bin/bash

set -e

# Colors
GREEN="\033[0;32m"
RED="\033[0;31m"
BLUE="\033[0;34m"
YELLOW="\033[1;33m"
NC="\033[0m"

echo -e "${BLUE}Running linting and type checking for all Lambda functions...${NC}"
echo ""

FAILED_FUNCTIONS=()
PASSED_FUNCTIONS=()

for func_dir in lambda/functions/*/; do
  if [[ -f "${func_dir}pyproject.toml" ]]; then
    func_name=$(basename "${func_dir}")
    echo -e "${BLUE}Checking ${func_name}...${NC}"

    cd "$func_dir"

    # Sync dependencies WITH dev extras
    echo "  Syncing dependencies (including dev tools)..."
    if uv sync --all-extras --quiet 2>&1 > /dev/null; then
      echo -e "    ${GREEN}✓ Dependencies synced${NC}"
    else
      echo -e "    ${YELLOW}⚠ Warning: Sync may have failed${NC}"
    fi

    # Verify ruff is available
    if ! uv run ruff --version > /dev/null 2>&1; then
      echo -e "    ${RED}✗ Ruff not available after sync${NC}"
      FAILED_FUNCTIONS+=("$func_name:ruff")
      FAILED_FUNCTIONS+=("$func_name:mypy")
      cd - > /dev/null
      continue
    fi

    # Run ruff check
    echo "  Running ruff..."
    if uv run ruff check src/ tests/ > /dev/null 2>&1; then
      echo -e "    ${GREEN}✓ Ruff passed${NC}"
    else
      echo -e "    ${RED}✗ Ruff failed${NC}"
      uv run ruff check src/ tests/ 2>&1 | head -5
      FAILED_FUNCTIONS+=("$func_name:ruff")
    fi

    # Run mypy
    echo "  Running mypy..."
    if uv run mypy src/ > /dev/null 2>&1; then
      echo -e "    ${GREEN}✓ Mypy passed${NC}"
    else
      echo -e "    ${RED}✗ Mypy failed${NC}"
      uv run mypy src/ 2>&1 | head -5
      FAILED_FUNCTIONS+=("$func_name:mypy")
    fi

    # Check if this function passed both checks
    if [[ ! " ${FAILED_FUNCTIONS[@]} " =~ " ${func_name}:" ]]; then
      echo -e "${GREEN}✓ ${func_name} passed all checks${NC}"
      PASSED_FUNCTIONS+=("$func_name")
    fi

    cd - > /dev/null
    echo ""
  fi
done

echo "================================"
echo "Linting Summary:"
echo "  Passed: ${#PASSED_FUNCTIONS[@]}"
echo "  Failed: ${#FAILED_FUNCTIONS[@]}"

if [ ${#FAILED_FUNCTIONS[@]} -gt 0 ]; then
  echo -e "${RED}Failed checks:${NC}"
  for func in "${FAILED_FUNCTIONS[@]}"; do
    echo "  - $func"
  done
  exit 1
else
  echo -e "${GREEN}All checks passed!${NC}"
fi
