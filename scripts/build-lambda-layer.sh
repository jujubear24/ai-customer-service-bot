#!/bin/bash
#
# Build Lambda Layer with Dependencies
# This script builds the shared Lambda layer with all Python dependencies
# Uses Docker to ensure compatibility with AWS Lambda runtime
#
# Usage:
#   ./scripts/build-lambda-layer.sh              # Build layer
#   ./scripts/build-lambda-layer.sh --verbose    # Build with detailed output
#   ./scripts/build-lambda-layer.sh --force      # Force rebuild (ignore cache)
#   ./scripts/build-lambda-layer.sh --dry-run    # Show what would be built
#   ./scripts/build-lambda-layer.sh --help       # Show help
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
LAYER_DIR="$PROJECT_ROOT/lambda/layers/common"
BUILD_DIR="$PROJECT_ROOT/.build/lambda-layer"
OUTPUT_DIR="$PROJECT_ROOT/terraform/modules/lambda/builds"
OUTPUT_FILE="$OUTPUT_DIR/shared-layer.zip"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Options
VERBOSE=false
FORCE=false
DRY_RUN=false

# Layer dependencies - centralized for easy management
# Add new dependencies here
LAYER_DEPENDENCIES=(
    "boto3>=1.35.0"
    "aws-lambda-powertools[tracer]>=2.31.0"
    "pydantic>=2.5.0"
    "tenacity>=8.2.0"
)

# ==============================================================================
# Helper Functions
# ==============================================================================

show_help() {
    cat << EOF
${GREEN}Lambda Layer Build Script${NC}
Build the shared Lambda layer with Python dependencies.

${YELLOW}Usage:${NC}
    $(basename "$0") [OPTIONS]

${YELLOW}Options:${NC}
    -h, --help      Show this help message
    -v, --verbose   Enable verbose output
    -f, --force     Force rebuild even if layer exists
    --dry-run       Show what would be built without building

${YELLOW}Layer Contents:${NC}
    - Shared code from: lambda/layers/common/python/shared/
    - Dependencies:
$(printf '      - %s\n' "${LAYER_DEPENDENCIES[@]}")

${YELLOW}Output:${NC}
    $OUTPUT_FILE
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

check_docker() {
    if ! docker info > /dev/null 2>&1; then
        log_error "Docker is not running. Please start Docker Desktop."
        exit 1
    fi
    log_verbose "Docker is running"
}

# Generate requirements hash for caching
get_requirements_hash() {
    echo "${LAYER_DEPENDENCIES[@]}" | md5sum | cut -d' ' -f1
}

# Check if rebuild is needed
needs_rebuild() {
    if [ "$FORCE" = true ]; then
        log_verbose "Force rebuild requested"
        return 0
    fi

    if [ ! -f "$OUTPUT_FILE" ]; then
        log_verbose "Layer ZIP does not exist"
        return 0
    fi

    # Check if shared code changed
    if [ -d "$LAYER_DIR/python/shared" ]; then
        local layer_mtime
        layer_mtime=$(stat -c %Y "$OUTPUT_FILE" 2>/dev/null || stat -f %m "$OUTPUT_FILE" 2>/dev/null)

        # Find newest file in shared directory
        local newest_shared
        newest_shared=$(find "$LAYER_DIR/python/shared" -type f -name "*.py" -exec stat -c %Y {} \; 2>/dev/null | sort -rn | head -1 || \
                        find "$LAYER_DIR/python/shared" -type f -name "*.py" -exec stat -f %m {} \; 2>/dev/null | sort -rn | head -1)

        if [ -n "$newest_shared" ] && [ "$newest_shared" -gt "$layer_mtime" ]; then
            log_verbose "Shared code has changed since last build"
            return 0
        fi
    fi

    log_info "Layer is up to date (use --force to rebuild)"
    return 1
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
        -v|--verbose)
            VERBOSE=true
            shift
            ;;
        -f|--force)
            FORCE=true
            shift
            ;;
        --dry-run)
            DRY_RUN=true
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

echo -e "${GREEN}Building Lambda Layer${NC}"
echo "Project root: $PROJECT_ROOT"
echo ""

# Dry run mode
if [ "$DRY_RUN" = true ]; then
    echo -e "${YELLOW}Dry run mode - no changes will be made${NC}"
    echo ""
    echo "Would build layer with:"
    echo "  Source: $LAYER_DIR/python/shared/"
    echo "  Output: $OUTPUT_FILE"
    echo ""
    echo "Dependencies:"
    printf '  - %s\n' "${LAYER_DEPENDENCIES[@]}"
    exit 0
fi

# Pre-flight checks
check_docker

# Verify source directory exists
if [ ! -d "$LAYER_DIR/python/shared" ]; then
    log_error "Shared layer source not found at $LAYER_DIR/python/shared"
    exit 1
fi
log_verbose "Found shared code at $LAYER_DIR/python/shared"

# Check if rebuild is needed
if ! needs_rebuild; then
    exit 0
fi

# Track build time
START_TIME=$(date +%s)

# Clean previous build
log_info "Preparing build directory..."
rm -rf "$BUILD_DIR"
mkdir -p "$BUILD_DIR/python"

# Copy shared code
log_info "Copying shared code..."
cp -r "$LAYER_DIR/python/shared" "$BUILD_DIR/python/"

if [ "$VERBOSE" = true ]; then
    echo "  Shared modules:"
    find "$BUILD_DIR/python/shared" -name "*.py" -type f | while read -r file; do
        echo "    - $(basename "$file")"
    done
fi

# Create requirements file
log_info "Creating requirements file..."
REQUIREMENTS_FILE="$BUILD_DIR/requirements.txt"
printf '%s\n' "${LAYER_DEPENDENCIES[@]}" > "$REQUIREMENTS_FILE"

if [ "$VERBOSE" = true ]; then
    echo "  Dependencies:"
    cat "$REQUIREMENTS_FILE" | while read -r dep; do
        echo "    - $dep"
    done
fi

# Install dependencies using Docker with Lambda Python runtime
log_info "Installing dependencies in Lambda-compatible environment..."
log_verbose "Using Docker image: public.ecr.aws/lambda/python:3.12"

docker run --rm \
    --entrypoint pip \
    -v "$BUILD_DIR":/var/task \
    public.ecr.aws/lambda/python:3.12 \
    install -r /var/task/requirements.txt -t /var/task/python/ --no-cache-dir \
    $([ "$VERBOSE" = true ] && echo "" || echo "-q")

# Clean up unnecessary files to reduce layer size
log_info "Cleaning up build artifacts..."
cd "$BUILD_DIR"

# Remove cache and metadata
find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
find . -type d -name "*.dist-info" -exec rm -rf {} + 2>/dev/null || true
find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
find . -type d -name "tests" -exec rm -rf {} + 2>/dev/null || true
find . -type d -name "test" -exec rm -rf {} + 2>/dev/null || true

# Remove compiled files
find . -type f -name "*.pyc" -delete 2>/dev/null || true
find . -type f -name "*.pyo" -delete 2>/dev/null || true

# Strip shared libraries (reduce size)
find . -name "*.so" -exec strip {} \; 2>/dev/null || true

# Remove unnecessary files
rm -rf "$BUILD_DIR/python/boto3" 2>/dev/null || true  # boto3 is in Lambda runtime
rm -rf "$BUILD_DIR/python/botocore" 2>/dev/null || true  # botocore is in Lambda runtime
rm -f "$BUILD_DIR/requirements.txt"

log_verbose "Cleanup complete"

# Create output directory
mkdir -p "$OUTPUT_DIR"

# Create ZIP file
log_info "Creating layer ZIP..."
cd "$BUILD_DIR"
zip -r "$OUTPUT_FILE" python/ -q

# Calculate sizes
END_TIME=$(date +%s)
DURATION=$((END_TIME - START_TIME))
LAYER_SIZE=$(du -h "$OUTPUT_FILE" | cut -f1)
UNCOMPRESSED_SIZE=$(du -sh "$BUILD_DIR/python" | cut -f1)

# Cleanup build directory
rm -rf "$BUILD_DIR"

# Summary
echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  Layer Built Successfully!${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo -e "  ${CYAN}Output:${NC}      $OUTPUT_FILE"
echo -e "  ${CYAN}Size:${NC}        $LAYER_SIZE (compressed)"
echo -e "  ${CYAN}Uncompressed:${NC} $UNCOMPRESSED_SIZE"
echo -e "  ${CYAN}Build time:${NC}  ${DURATION}s"
echo ""

# Show layer contents summary
if [ "$VERBOSE" = true ]; then
    echo "Layer contents:"
    unzip -l "$OUTPUT_FILE" | grep -E "\.py$|\.so$" | head -20
    echo "  ... (use 'unzip -l $OUTPUT_FILE' to see all)"
    echo ""
fi

# AWS Lambda layer size limits
LAYER_SIZE_MB=$(du -m "$OUTPUT_FILE" | cut -f1)
if [ "$LAYER_SIZE_MB" -gt 50 ]; then
    log_warning "Layer size ($LAYER_SIZE_MB MB) exceeds 50 MB. Consider optimizing."
elif [ "$LAYER_SIZE_MB" -gt 40 ]; then
    log_warning "Layer size ($LAYER_SIZE_MB MB) is approaching 50 MB limit."
fi

log_success "Layer build complete!"
