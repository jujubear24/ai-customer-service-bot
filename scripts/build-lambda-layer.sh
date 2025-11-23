#!/bin/bash
#
# Build Lambda Layer with Dependencies
# This script builds the shared Lambda layer with all Python dependencies
# Uses Docker to ensure compatibility with AWS Lambda runtime
#

set -e

# Get absolute paths
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
LAYER_DIR="$PROJECT_ROOT/lambda/layers/common"
BUILD_DIR="$PROJECT_ROOT/.build/lambda-layer"

echo "Building Lambda layer for AWS Lambda runtime..."
echo "Project root: $PROJECT_ROOT"

# Check if Docker is running
if ! docker info > /dev/null 2>&1; then
    echo "Error: Docker is not running. Please start Docker Desktop."
    exit 1
fi

# Verify source directory exists
if [ ! -d "$LAYER_DIR/python/shared" ]; then
    echo "Error: Shared layer source not found at $LAYER_DIR/python/shared"
    exit 1
fi

# Clean previous build
rm -rf "$BUILD_DIR"
mkdir -p "$BUILD_DIR/python"

# Copy shared code
echo "Copying shared code..."
cp -r "$LAYER_DIR/python/shared" "$BUILD_DIR/python/"

# Create a temporary requirements file
cat > "$BUILD_DIR/requirements.txt" << 'EOF'
boto3>=1.35.0
aws-lambda-powertools[tracer]>=2.31.0
pydantic>=2.5.0
redis>=5.0.0
EOF

# Install dependencies using Docker with Lambda Python runtime
echo "Installing dependencies in Lambda-compatible environment..."
docker run --rm \
  --entrypoint pip \
  -v "$BUILD_DIR":/var/task \
  public.ecr.aws/lambda/python:3.12 \
  install -r /var/task/requirements.txt -t /var/task/python/ --no-cache-dir

# Clean up unnecessary files to reduce layer size
echo "Cleaning up build artifacts..."
cd "$BUILD_DIR"
find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
find . -type d -name "*.dist-info" -exec rm -rf {} + 2>/dev/null || true
find . -type d -name "tests" -exec rm -rf {} + 2>/dev/null || true
find . -type f -name "*.pyc" -delete 2>/dev/null || true
find . -type f -name "*.pyo" -delete 2>/dev/null || true
find . -name "*.so" -exec strip {} \; 2>/dev/null || true

# Remove requirements file
rm -f "$BUILD_DIR/requirements.txt"

# Create builds directory if it doesn't exist
mkdir -p "$PROJECT_ROOT/terraform/modules/lambda/builds"

# Create ZIP file
echo "Creating layer ZIP..."
cd "$BUILD_DIR"
zip -r "$PROJECT_ROOT/terraform/modules/lambda/builds/shared-layer.zip" python/ -q

LAYER_SIZE=$(du -h "$PROJECT_ROOT/terraform/modules/lambda/builds/shared-layer.zip" | cut -f1)
echo "✓ Layer built successfully: $LAYER_SIZE"
echo "  Location: terraform/modules/lambda/builds/shared-layer.zip"

# Cleanup
rm -rf "$BUILD_DIR"

echo "Done!"
