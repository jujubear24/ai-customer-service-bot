#!/bin/bash
#
# Build All Lambda Functions and Layers
# This script handles the complete build process for all Lambda artifacts
#
# Usage:
#   ./scripts/build-lambdas.sh              # Build everything
#   ./scripts/build-lambdas.sh --layer-only  # Only rebuild layer
#   ./scripts/build-lambdas.sh --functions   # Only rebuild functions
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
BUILD_OUTPUT="$PROJECT_ROOT/terraform/modules/lambda/builds"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Parse arguments
BUILD_LAYER=true
BUILD_FUNCTIONS=true

while [[ $# -gt 0 ]]; do
    case $1 in
        --layer-only)
            BUILD_FUNCTIONS=false
            shift
            ;;
        --functions-only)
            BUILD_LAYER=false
            shift
            ;;
        *)
            echo -e "${RED}Unknown option: $1${NC}"
            exit 1
            ;;
    esac
done

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  Building Lambda Artifacts${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""

# Create build output directory
mkdir -p "$BUILD_OUTPUT"

# ==============================================================================
# Build Lambda Layer
# ==============================================================================

if [ "$BUILD_LAYER" = true ]; then
    echo -e "${YELLOW}[1/2] Building Lambda Layer...${NC}"

    if [ ! -f "$SCRIPT_DIR/build-lambda-layer.sh" ]; then
        echo -e "${RED}Error: build-lambda-layer.sh not found${NC}"
        exit 1
    fi

    "$SCRIPT_DIR/build-lambda-layer.sh"

    if [ $? -eq 0 ]; then
        echo -e "${GREEN}✓ Layer built successfully${NC}"
    else
        echo -e "${RED}✗ Layer build failed${NC}"
        exit 1
    fi
    echo ""
fi

# ==============================================================================
# Build Lambda Functions
# ==============================================================================

if [ "$BUILD_FUNCTIONS" = true ]; then
    echo -e "${YELLOW}[2/2] Building Lambda Functions...${NC}"

    LAMBDA_FUNCTIONS=(
        "intent-classifier"
        "context-builder"
        # Add more functions here as you build them:
        # "context-builder"
        # "bedrock-handler"
        # "response-validator"
    )

    for FUNCTION in "${LAMBDA_FUNCTIONS[@]}"; do
        echo ""
        echo -e "  Building ${FUNCTION}..."

        FUNCTION_DIR="$PROJECT_ROOT/lambda/functions/$FUNCTION"

        if [ ! -d "$FUNCTION_DIR" ]; then
            echo -e "${RED}  ✗ Function directory not found: $FUNCTION_DIR${NC}"
            continue
        fi

        # Check if function has its own dependencies
        if [ -f "$FUNCTION_DIR/pyproject.toml" ]; then
            echo "    → Checking for function-specific dependencies..."

            # Parse dependencies from pyproject.toml (excluding dev dependencies)
            HAS_DEPS=$(grep -A 10 '^\[project\]' "$FUNCTION_DIR/pyproject.toml" | \
                       grep -A 5 'dependencies = \[' | \
                       grep -v 'dev' | \
                       grep -c '    "' || true)

            if [ "$HAS_DEPS" -gt 0 ]; then
                echo "    → Found function-specific dependencies, installing..."

                # Create temporary build directory
                TEMP_BUILD="$PROJECT_ROOT/.build/lambda-$FUNCTION"
                rm -rf "$TEMP_BUILD"
                mkdir -p "$TEMP_BUILD"

                # Copy source code
                cp -r "$FUNCTION_DIR/src/"* "$TEMP_BUILD/"

                # Install function-specific dependencies using Docker
                echo "    → Installing dependencies in Lambda runtime..."
                docker run --rm \
                    --entrypoint pip \
                    -v "$TEMP_BUILD":/var/task \
                    -v "$FUNCTION_DIR":/function \
                    public.ecr.aws/lambda/python:3.12 \
                    install -r /function/pyproject.toml -t /var/task/ --no-cache-dir 2>/dev/null || {

                    # Fallback: Use uv to extract deps and install
                    cd "$FUNCTION_DIR"
                    uv pip compile pyproject.toml -o /tmp/requirements-$FUNCTION.txt 2>/dev/null || true

                    if [ -f "/tmp/requirements-$FUNCTION.txt" ]; then
                        docker run --rm \
                            --entrypoint pip \
                            -v "$TEMP_BUILD":/var/task \
                            -v /tmp:/reqs \
                            public.ecr.aws/lambda/python:3.12 \
                            install -r /reqs/requirements-$FUNCTION.txt -t /var/task/ --no-cache-dir
                        rm /tmp/requirements-$FUNCTION.txt
                    fi
                }

                # Clean up unnecessary files
                cd "$TEMP_BUILD"
                find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
                find . -type d -name "*.dist-info" -exec rm -rf {} + 2>/dev/null || true
                find . -type d -name "tests" -exec rm -rf {} + 2>/dev/null || true
                find . -type f -name "*.pyc" -delete 2>/dev/null || true

                # Create ZIP
                zip -r "$BUILD_OUTPUT/$FUNCTION.zip" . -q

                # Cleanup
                rm -rf "$TEMP_BUILD"
            else
                # No dependencies, just package source
                echo "    → No function-specific dependencies, packaging source only..."
                cd "$FUNCTION_DIR/src"
                zip -r "$BUILD_OUTPUT/$FUNCTION.zip" . -q \
                    -x "*.pyc" "*__pycache__*" "tests/*" "*.egg-info/*"
            fi
        else
            # No pyproject.toml, just package source
            echo "    → Packaging source code only..."
            cd "$FUNCTION_DIR/src"
            zip -r "$BUILD_OUTPUT/$FUNCTION.zip" . -q \
                -x "*.pyc" "*__pycache__*" "tests/*"
        fi

        if [ $? -eq 0 ]; then
            SIZE=$(du -h "$BUILD_OUTPUT/$FUNCTION.zip" | cut -f1)
            echo -e "${GREEN}    ✓ Built: $FUNCTION.zip ($SIZE)${NC}"
        else
            echo -e "${RED}    ✗ Failed to build $FUNCTION${NC}"
            exit 1
        fi
    done

    echo ""
    echo -e "${GREEN}✓ All functions built successfully${NC}"
fi

# ==============================================================================
# Summary
# ==============================================================================

echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  Build Complete!${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo "Artifacts created in: $BUILD_OUTPUT"
echo ""
ls -lh "$BUILD_OUTPUT"/*.zip 2>/dev/null | awk '{print "  " $9 " (" $5 ")"}'
echo ""
echo -e "${YELLOW}Next steps:${NC}"
echo "  1. Run tests: cd lambda/functions/intent-classifier && uv run pytest"
echo "  2. Deploy: cd terraform/environments/dev && terraform apply"
echo ""
