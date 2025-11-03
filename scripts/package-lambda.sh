# scripts/package-lambda.sh
#!/bin/bash
FUNCTION_NAME=$1

cd lambda/functions/$FUNCTION_NAME

# Create clean package directory
rm -rf package
mkdir package

# Use UV to install deps (faster!)
uv pip install -r requirements.txt --target package/

# Copy source code
cp -r src/* package/

# Create ZIP
cd package
zip -r ../function.zip .
cd ..

echo "✓ Lambda packaged: function.zip"