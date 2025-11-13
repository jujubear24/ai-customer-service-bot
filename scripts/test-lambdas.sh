#!/bin/bash

set -e

# Colors
GREEN="\033[0;32m"
RED="\033[0;31m"
BLUE="\033[0;34m"
YELLOW="\033[1;33m"
NC="\033[0m" # No Color

echo -e "${BLUE}Running tests for all Lambda functions...${NC}"
echo ""

FAILED_FUNCTIONS=()
PASSED_FUNCTIONS=()
TOTAL_COVERAGE=0
FUNCTION_COUNT=0

for func_dir in lambda/functions/*/; do
  if [[ -f "${func_dir}pyproject.toml" ]]; then
    func_name=$(basename "${func_dir}")
    echo -e "${BLUE}Testing ${func_name}...${NC}"

    cd "$func_dir"

    # Run tests with coverage
    if uv run pytest --cov=src --cov-report=term --cov-report=json; then
      echo -e "${GREEN}✓ ${func_name} tests passed${NC}"
      PASSED_FUNCTIONS+=("$func_name")

      # Extract coverage percentage if available
      if [[ -f "coverage.json" ]]; then
        coverage=$(python3 -c "import json; data=json.load(open(\"coverage.json\")); print(data.get(\"totals\", {}).get(\"percent_covered\", 0))" 2>/dev/null || echo "0")
        echo -e "  Coverage: ${coverage}%"
        TOTAL_COVERAGE=$(echo "$TOTAL_COVERAGE + $coverage" | bc)
        FUNCTION_COUNT=$((FUNCTION_COUNT + 1))
      fi
    else
      echo -e "${RED}✗ ${func_name} tests failed${NC}"
      FAILED_FUNCTIONS+=("$func_name")
    fi

    cd - > /dev/null
    echo ""
  fi
done

echo "================================"
echo "Test Summary:"
echo "  Passed: ${#PASSED_FUNCTIONS[@]}"
echo "  Failed: ${#FAILED_FUNCTIONS[@]}"

if [[ $FUNCTION_COUNT -gt 0 ]]; then
  AVG_COVERAGE=$(echo "scale=2; $TOTAL_COVERAGE / $FUNCTION_COUNT" | bc)
  echo "  Average Coverage: ${AVG_COVERAGE}%"
fi

if [ ${#FAILED_FUNCTIONS[@]} -gt 0 ]; then
  echo -e "${RED}Failed functions:${NC}"
  for func in "${FAILED_FUNCTIONS[@]}"; do
    echo "  - $func"
  done
  exit 1
else
  echo -e "${GREEN}All tests passed!${NC}"
fi
