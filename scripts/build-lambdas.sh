#!/bin/bash
#
# Build Lambda Functions and Layer
# This script handles the complete build process for Lambda artifacts
#
# Usage:
#   ./scripts/build-lambdas.sh                          # Build layer + all functions
#   ./scripts/build-lambdas.sh --layer-only             # Only rebuild layer
#   ./scripts/build-lambdas.sh --functions-only         # Only rebuild all functions
#   ./scripts/build-lambdas.sh -f chat-orchestrator     # Build single function
#   ./scripts/build-lambdas.sh -f rag-retriever -f bedrock-handler  # Build multiple
#   ./scripts/build-lambdas.sh --list                   # List available functions
#   ./scripts/build-lambdas.sh --clean                  # Clean all build artifacts
#   ./scripts/build-lambdas.sh --help                   # Show help
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
BUILD_OUTPUT="$PROJECT_ROOT/terraform/modules/lambda/builds"
FUNCTIONS_DIR="$PROJECT_ROOT/lambda/functions"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Default options
BUILD_LAYER=true
BUILD_FUNCTIONS=true
SPECIFIC_FUNCTIONS=()
LIST_ONLY=false
CLEAN_ONLY=false
VERBOSE=false

# ==============================================================================
# Helper Functions
# ==============================================================================

show_help() {
    cat << EOF
${GREEN}Lambda Build Script${NC}
Build Lambda functions and/or shared layer for deployment.

${YELLOW}Usage:${NC}
    $(basename "$0") [OPTIONS]

${YELLOW}Options:${NC}
    -h, --help              Show this help message
    -l, --layer-only        Only rebuild the shared layer
    -F, --functions-only    Only rebuild functions (skip layer)
    -f, --function NAME     Build specific function(s). Can be used multiple times.
    --list                  List all available functions
    --clean                 Remove all build artifacts
    -v, --verbose           Enable verbose output

${YELLOW}Examples:${NC}
    $(basename "$0")                                      # Build everything
    $(basename "$0") --layer-only                         # Only build layer
    $(basename "$0") --functions-only                     # Only build all functions
    $(basename "$0") -f chat-orchestrator                 # Build single function
    $(basename "$0") -f rag-retriever -f bedrock-handler  # Build multiple functions
    $(basename "$0") --list                               # List available functions
    $(basename "$0") --clean                              # Clean build artifacts

${YELLOW}Available functions:${NC}
    Functions are auto-detected from: lambda/functions/
    A valid function must have a src/handler.py file.

${YELLOW}Build Output:${NC}
    $BUILD_OUTPUT
EOF
}

log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_verbose() {
    if [ "$VERBOSE" = true ]; then
        echo -e "${CYAN}[DEBUG]${NC} $1"
    fi
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Get list of all valid Lambda functions (those with src/handler.py)
get_all_functions() {
    local functions=()
    for dir in "$FUNCTIONS_DIR"/*/; do
        if [ -d "$dir/src" ] && [ -f "$dir/src/handler.py" ]; then
            functions+=("$(basename "$dir")")
        fi
    done
    echo "${functions[@]}"
}

# List all functions with their status
list_functions() {
    echo -e "${GREEN}========================================${NC}"
    echo -e "${GREEN}  Available Lambda Functions${NC}"
    echo -e "${GREEN}========================================${NC}"
    echo ""

    local count=0
    local valid_count=0

    for dir in "$FUNCTIONS_DIR"/*/; do
        if [ -d "$dir" ]; then
            ((count++))
            local func_name
            func_name=$(basename "$dir")
            local has_handler=false
            local has_tests=false
            local has_pyproject=false

            [ -f "$dir/src/handler.py" ] && has_handler=true
            [ -d "$dir/tests" ] && [ "$(ls -A "$dir/tests" 2>/dev/null)" ] && has_tests=true
            [ -f "$dir/pyproject.toml" ] && has_pyproject=true

            if [ "$has_handler" = true ]; then
                ((valid_count++))
                echo -e "  ${GREEN}✓${NC} ${YELLOW}$func_name${NC}"
            else
                echo -e "  ${RED}○${NC} ${func_name} (missing handler.py)"
            fi

            if [ "$VERBOSE" = true ]; then
                echo -e "      handler.py:     $([ "$has_handler" = true ] && echo "✓" || echo "✗")"
                echo -e "      tests/:         $([ "$has_tests" = true ] && echo "✓" || echo "✗")"
                echo -e "      pyproject.toml: $([ "$has_pyproject" = true ] && echo "✓" || echo "✗")"

                # Check if ZIP exists
                if [ -f "$BUILD_OUTPUT/$func_name.zip" ]; then
                    local size
                    size=$(du -h "$BUILD_OUTPUT/$func_name.zip" | cut -f1)
                    echo -e "      build:          ✓ ($size)"
                else
                    echo -e "      build:          ✗ (not built)"
                fi
                echo ""
            fi
        fi
    done

    echo ""
    echo -e "  ${CYAN}Total: $count directories, $valid_count buildable functions${NC}"
    echo ""
}

# Clean all build artifacts
clean_builds() {
    echo -e "${YELLOW}Cleaning build artifacts...${NC}"

    if [ -d "$BUILD_OUTPUT" ]; then
        local count
        count=$(find "$BUILD_OUTPUT" -name "*.zip" 2>/dev/null | wc -l)
        rm -f "$BUILD_OUTPUT"/*.zip
        log_success "Removed $count ZIP file(s) from $BUILD_OUTPUT"
    fi

    if [ -d "$PROJECT_ROOT/.build" ]; then
        rm -rf "$PROJECT_ROOT/.build"
        log_success "Removed .build directory"
    fi

    echo -e "${GREEN}✓ Clean complete${NC}"
}

# Build a single Lambda function
build_function() {
    local FUNCTION=$1
    local FUNCTION_DIR="$FUNCTIONS_DIR/$FUNCTION"
    local start_time
    start_time=$(date +%s)

    echo -e "  Building ${YELLOW}${FUNCTION}${NC}..."

    # Validate function directory
    if [ ! -d "$FUNCTION_DIR" ]; then
        log_error "Function directory not found: $FUNCTION_DIR"
        return 1
    fi

    if [ ! -d "$FUNCTION_DIR/src" ]; then
        log_error "Source directory not found: $FUNCTION_DIR/src"
        return 1
    fi

    if [ ! -f "$FUNCTION_DIR/src/handler.py" ]; then
        log_error "handler.py not found in $FUNCTION_DIR/src/"
        return 1
    fi

    # Check for function-specific dependencies
    local HAS_DEPS=0
    if [ -f "$FUNCTION_DIR/pyproject.toml" ]; then
        log_verbose "Found pyproject.toml for $FUNCTION"

        # Parse dependencies from pyproject.toml (exclude dev dependencies)
        HAS_DEPS=$(grep -A 20 '^\[project\]' "$FUNCTION_DIR/pyproject.toml" 2>/dev/null | \
                   grep -A 10 'dependencies = \[' | \
                   grep -E '^\s+"[^"]+' | \
                   grep -v -E 'pytest|ruff|mypy|black|coverage' | \
                   wc -l || echo "0")
        HAS_DEPS=$(echo "$HAS_DEPS" | tr -d ' ')

        log_verbose "Found $HAS_DEPS production dependencies"
    fi

    if [ "$HAS_DEPS" -gt 0 ]; then
        echo "    → Installing function-specific dependencies..."

        # Create temporary build directory
        local TEMP_BUILD="$PROJECT_ROOT/.build/lambda-$FUNCTION"
        rm -rf "$TEMP_BUILD"
        mkdir -p "$TEMP_BUILD"

        # Copy source code
        cp -r "$FUNCTION_DIR/src/"* "$TEMP_BUILD/"

        # Try to install dependencies
        local deps_installed=false

        # Method 1: Use uv to compile requirements and install
        log_verbose "Using uv to compile dependencies"
        cd "$FUNCTION_DIR"

        if uv pip compile pyproject.toml --no-dev -o "/tmp/requirements-$FUNCTION.txt" 2>/dev/null; then
            if [ -s "/tmp/requirements-$FUNCTION.txt" ]; then
                log_verbose "Installing from compiled requirements"
                docker run --rm \
                    --entrypoint pip \
                    -v "$TEMP_BUILD":/var/task \
                    -v /tmp:/reqs:ro \
                    public.ecr.aws/lambda/python:3.12 \
                    install -r "/reqs/requirements-$FUNCTION.txt" -t /var/task/ --no-cache-dir 2>/dev/null && deps_installed=true
            fi
            rm -f "/tmp/requirements-$FUNCTION.txt"
        fi

        if [ "$deps_installed" = false ]; then
            log_warning "Could not install function-specific dependencies, packaging source only"
        fi

        # Clean up unnecessary files
        cd "$TEMP_BUILD"
        find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
        find . -type d -name "*.dist-info" -exec rm -rf {} + 2>/dev/null || true
        find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
        find . -type d -name "tests" -exec rm -rf {} + 2>/dev/null || true
        find . -type f -name "*.pyc" -delete 2>/dev/null || true
        find . -type f -name "*.pyo" -delete 2>/dev/null || true

        # Create ZIP
        zip -r "$BUILD_OUTPUT/$FUNCTION.zip" . -q

        # Cleanup temp directory
        rm -rf "$TEMP_BUILD"
    else
        # No dependencies, just package source
        echo "    → Packaging source code..."
        cd "$FUNCTION_DIR/src"
        zip -r "$BUILD_OUTPUT/$FUNCTION.zip" . -q \
            -x "*.pyc" -x "*__pycache__*" -x "*.egg-info/*"
    fi

    local end_time
    end_time=$(date +%s)
    local duration=$((end_time - start_time))

    if [ -f "$BUILD_OUTPUT/$FUNCTION.zip" ]; then
        local SIZE
        SIZE=$(du -h "$BUILD_OUTPUT/$FUNCTION.zip" | cut -f1)
        echo -e "${GREEN}    ✓ Built: $FUNCTION.zip ($SIZE) [${duration}s]${NC}"
        return 0
    else
        log_error "Failed to create $FUNCTION.zip"
        return 1
    fi
}

# ==============================================================================
# Parse Arguments
# ==============================================================================

while [[ $# -gt 0 ]]; do
    case $1 in
        -h|--help)
            show_help
            exit 0
            ;;
        -l|--layer-only)
            BUILD_FUNCTIONS=false
            shift
            ;;
        -F|--functions-only)
            BUILD_LAYER=false
            shift
            ;;
        -f|--function)
            if [ -z "$2" ] || [[ "$2" == -* ]]; then
                log_error "--function requires a function name"
                exit 1
            fi
            SPECIFIC_FUNCTIONS+=("$2")
            BUILD_LAYER=false  # Don't build layer when building specific functions
            shift 2
            ;;
        --list)
            LIST_ONLY=true
            shift
            ;;
        --clean)
            CLEAN_ONLY=true
            shift
            ;;
        -v|--verbose)
            VERBOSE=true
            shift
            ;;
        *)
            log_error "Unknown option: $1"
            echo "Use --help for usage information"
            exit 1
            ;;
    esac
done

# ==============================================================================
# Main Execution
# ==============================================================================

# Handle --list
if [ "$LIST_ONLY" = true ]; then
    list_functions
    exit 0
fi

# Handle --clean
if [ "$CLEAN_ONLY" = true ]; then
    clean_builds
    exit 0
fi

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  Lambda Build Script${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""

# Create build output directory
mkdir -p "$BUILD_OUTPUT"

# Track overall timing
OVERALL_START=$(date +%s)

# ==============================================================================
# Build Lambda Layer
# ==============================================================================

if [ "$BUILD_LAYER" = true ]; then
    echo -e "${YELLOW}[1/2] Building Lambda Layer...${NC}"
    echo ""

    if [ ! -f "$SCRIPT_DIR/build-lambda-layer.sh" ]; then
        log_error "build-lambda-layer.sh not found at $SCRIPT_DIR"
        exit 1
    fi

    if [ "$VERBOSE" = true ]; then
        "$SCRIPT_DIR/build-lambda-layer.sh" --verbose
    else
        "$SCRIPT_DIR/build-lambda-layer.sh"
    fi

    if [ $? -eq 0 ]; then
        echo ""
        log_success "Layer built successfully"
    else
        log_error "Layer build failed"
        exit 1
    fi
    echo ""
fi

# ==============================================================================
# Build Lambda Functions
# ==============================================================================

if [ "$BUILD_FUNCTIONS" = true ] || [ ${#SPECIFIC_FUNCTIONS[@]} -gt 0 ]; then
    # Determine which functions to build
    if [ ${#SPECIFIC_FUNCTIONS[@]} -gt 0 ]; then
        FUNCTIONS_TO_BUILD=("${SPECIFIC_FUNCTIONS[@]}")
        echo -e "${YELLOW}Building ${#FUNCTIONS_TO_BUILD[@]} specific function(s)...${NC}"
    else
        read -ra FUNCTIONS_TO_BUILD <<< "$(get_all_functions)"
        if [ "$BUILD_LAYER" = true ]; then
            echo -e "${YELLOW}[2/2] Building Lambda Functions (${#FUNCTIONS_TO_BUILD[@]} found)...${NC}"
        else
            echo -e "${YELLOW}Building Lambda Functions (${#FUNCTIONS_TO_BUILD[@]} found)...${NC}"
        fi
    fi

    if [ ${#FUNCTIONS_TO_BUILD[@]} -eq 0 ]; then
        log_warning "No functions found to build"
        echo "  Check that functions have src/handler.py"
        exit 0
    fi

    echo ""

    FAILED_FUNCTIONS=()
    BUILT_COUNT=0

    for FUNCTION in "${FUNCTIONS_TO_BUILD[@]}"; do
        if build_function "$FUNCTION"; then
            ((BUILT_COUNT++))
        else
            FAILED_FUNCTIONS+=("$FUNCTION")
        fi
        echo ""
    done

    # Report results
    if [ ${#FAILED_FUNCTIONS[@]} -gt 0 ]; then
        log_error "Failed to build ${#FAILED_FUNCTIONS[@]} function(s):"
        for func in "${FAILED_FUNCTIONS[@]}"; do
            echo -e "  ${RED}- $func${NC}"
        done
        exit 1
    else
        log_success "Successfully built $BUILT_COUNT function(s)"
    fi
fi

# ==============================================================================
# Summary
# ==============================================================================

OVERALL_END=$(date +%s)
OVERALL_DURATION=$((OVERALL_END - OVERALL_START))

echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  Build Complete! (${OVERALL_DURATION}s)${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo "Artifacts location: $BUILD_OUTPUT"
echo ""

# List built artifacts with sizes
if [ -d "$BUILD_OUTPUT" ]; then
    echo "Built artifacts:"
    for zip in "$BUILD_OUTPUT"/*.zip; do
        if [ -f "$zip" ]; then
            SIZE=$(du -h "$zip" | cut -f1)
            NAME=$(basename "$zip")
            echo -e "  ${GREEN}✓${NC} $NAME ($SIZE)"
        fi
    done 2>/dev/null || echo "  No ZIP files found"
fi

echo ""
echo -e "${YELLOW}Next steps:${NC}"
echo "  1. Run tests:  cd lambda/functions/<function> && uv run pytest"
echo "  2. Deploy:     cd terraform/environments/dev && terraform apply"
echo ""
