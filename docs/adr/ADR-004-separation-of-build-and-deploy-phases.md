# ADR-004: Separation of Build and Deploy Phases

## Status

Accepted

## Date

2025-11-24

## Context

- Infrastructure as Code (IaC) tools like Terraform are designed for provisioning and managing cloud resources (networks, IAM roles, databases, etc.), not for software build processes.
- However, AWS Lambda deployment requires creating ZIP files containing application code and dependencies.

- We need to decide: Should Terraform handle both building Lambda packages AND deploying infrastructure, or should these be separate phases?

### The Problem with Mixed Responsibilities

Our initial implementation had Terraform's `archive_file` data source packaging function code:

```hcl
data "archive_file" "intent_classifier" {
  source_dir  = "lambda/functions/intent-classifier/src"
  output_path = "builds/intent-classifier.zip"
}
```

This approach has limitations:

1. **No dependency installation**: Terraform doesn't run `pip install` or `uv sync`
2. **No Docker compilation**: Can't compile native extensions for Lambda runtime
3. **Limited build logic**: Can't run tests, linting, or custom build steps
4. **Inconsistent builds**: Layer uses Docker, but functions don't
5. **CI/CD complexity**: Build happens during deploy, can't separate stages

### Python Dependency Complexity

Python packages have specific challenges:

- Native extensions must be compiled for target platform (Amazon Linux 2)
- Dependency resolution can be complex (version conflicts, transitive deps)
- Virtual environments and package isolation
- Build tools: pip, uv, poetry, PDM - none of which Terraform supports

Terraform is infrastructure-focused and deliberately doesn't include build toolchains.

## Decision

We will **separate the build and deploy phases** using the following architecture:

### Build Phase (Shell Scripts + Docker + uv)

**Tool**: Shell scripts (`build-lambdas.sh`, `build-lambda-layer.sh`)

**Responsibilities**:

- Install dependencies using Docker (Amazon Linux 2 environment)
- Compile native extensions for Lambda runtime
- Package source code into ZIP files
- Clean up build artifacts
- Place output in `terraform/modules/lambda/builds/`

**Output**: Pre-built, Lambda-compatible ZIP files

### Deploy Phase (Terraform)

**Tool**: Terraform

**Responsibilities**:

- Reference pre-built ZIP files
- Create Lambda functions and layers
- Configure IAM roles and policies
- Set up networking (VPC, subnets, security groups)
- Configure environment variables
- Set up API Gateway
- Manage all other infrastructure

**Input**: Pre-built ZIP files from build phase

### Workflow

```bash
# Build Phase
./scripts/build-lambdas.sh          # Creates all ZIPs

# Test Phase (optional)
cd lambda/functions/intent-classifier
uv run pytest

# Deploy Phase
cd terraform/environments/dev
terraform apply                      # Deploys infrastructure
```

## Alternatives Considered

### Alternative 1: Terraform Handles Everything

**Rejected**: Current initial approach that led to this decision.

Pros:

- Single tool
- Simpler mental model

Cons:

- Can't handle Python dependencies
- No Docker compilation
- Can't run tests during build
- Not CI/CD friendly

### Alternative 2: AWS SAM

**Considered but rejected**:

Pros:

- Built-in `sam build` handles dependencies
- Integrates with CloudFormation
- Official AWS tool

Cons:

- Would replace our Terraform investment
- Less flexible than Terraform for complex infrastructure
- SAM templates less powerful than Terraform
- Team already knows Terraform

### Alternative 3: Terraform + null_resource with local-exec

**Rejected**: Running shell scripts via Terraform's `local-exec` provisioner.

```hcl
resource "null_resource" "build_lambda" {
  provisioner "local-exec" {
    command = "./scripts/build-lambda.sh"
  }
}
```

Cons:

- Still mixing concerns (build runs during deploy)
- Hard to debug when scripts fail
- Difficult to test builds independently
- Creates implicit dependencies that Terraform can't track well
- Makes it harder to cache builds in CI/CD

### Alternative 4: Build in CI/CD Only

**Rejected**: No local builds, only build in GitHub Actions/GitLab CI.

Cons:

- Slow developer feedback loop
- Can't test locally before pushing
- Requires network access and CI credits for every build
- Makes development workflow painful

## Consequences

### Positive

#### Developer Experience

- ✅ **Fast Local Builds**: Developers can build and test without deploying
- ✅ **Clear Error Messages**: Build failures happen before Terraform, easier to debug
- ✅ **Faster Iteration**: Change code → build → test → deploy (skip rebuild if code unchanged)

#### CI/CD Benefits

- ✅ **Separated Stages**: Build → Test → Deploy in distinct CI pipeline stages
- ✅ **Cacheable Artifacts**: ZIPs can be stored and reused across environments
- ✅ **Deploy to Multiple Environments**: Build once, deploy to dev/staging/prod
- ✅ **Parallel Deployments**: Can deploy to multiple regions with same artifact

#### Technical Benefits

- ✅ **Consistent Builds**: All packaging uses Docker (layer + functions)
- ✅ **Portable Artifacts**: ZIPs are standalone, can be shared/archived
- ✅ **Terraform Simplicity**: Terraform only does infrastructure, stays focused
- ✅ **Function-Specific Dependencies**: Each function can have its own requirements

#### Maintenance Benefits

- ✅ **Easier Debugging**: Know if issue is build vs deploy
- ✅ **Independent Testing**: Test builds without deploying
- ✅ **Clear Responsibilities**: Shell scripts = build, Terraform = deploy

### Negative

#### Complexity

- ⚠️ **Two-Step Process**: Must remember to build before deploying
- ⚠️ **Manual Coordination**: Developers must run build script explicitly
- ⚠️ **More Scripts**: Additional shell scripts to maintain
- ⚠️ **Documentation**: Must document the two-phase process

#### Developer Workflow

- ⚠️ **Extra Command**: `./scripts/build-lambdas.sh` before `terraform apply`
- ⚠️ **Forgotten Builds**: Risk of deploying stale artifacts if build step is skipped
- ⚠️ **Disk Space**: Pre-built ZIPs stored in repo (added to .gitignore)

### Mitigations

To address the negatives:

1. **Unified Build Script**: `build-lambdas.sh` builds everything in one command
2. **Build Verification in Terraform**: Use `filebase64sha256()` to detect stale builds
3. **Documentation**: Clear README files and quick reference guides
4. **Pre-commit Hook**: Could add hook to ensure builds are current
5. **CI/CD Automation**: GitHub Actions automatically runs build before deploy
6. **Make Targets**: Provide `make build`, `make deploy` shortcuts

### Neutral

- 📝 **Build Artifacts Location**: `terraform/modules/lambda/builds/` (gitignored)
- 📝 **Build Script Maintenance**: Team must maintain shell scripts alongside Terraform
- 📝 **Docker Requirement**: Already required for layer, now consistent everywhere

## Implementation Details

### Build Script Features

The `build-lambdas.sh` script:

- Calls `build-lambda-layer.sh` for the shared layer
- Builds each Lambda function package
- Detects function-specific dependencies
- Uses Docker when dependencies exist
- Simple ZIP for pure Python functions
- Color-coded output for clarity
- Informative error messages

### Terraform Integration

```hcl
resource "aws_lambda_function" "intent_classifier" {
  filename         = "${path.module}/builds/intent-classifier.zip"
  source_code_hash = filebase64sha256("${path.module}/builds/intent-classifier.zip")
  # ... other config
}
```

The `source_code_hash` ensures Terraform re-deploys when the ZIP changes.

### Developer Workflow Examples

**Quick code change:**

```bash
# Edit code
vim lambda/functions/intent-classifier/src/handler.py

# Rebuild only functions (layer unchanged)
./scripts/build-lambdas.sh --functions-only

# Deploy
cd terraform/environments/dev && terraform apply
```

**Dependency change:**

```bash
# Update dependencies
vim lambda/layers/common/pyproject.toml

# Rebuild everything
./scripts/build-lambdas.sh

# Deploy
cd terraform/environments/dev && terraform apply
```

## Future Considerations

### CI/CD Pipeline (Future)

```yaml
jobs:
  build:
    - run: ./scripts/build-lambdas.sh
    - run: pytest
    - upload: lambda-builds/

  deploy-dev:
    - download: lambda-builds/
    - run: terraform apply dev

  deploy-prod:
    - download: lambda-builds/  # Same artifacts!
    - run: terraform apply prod
```

### Build Cache (Future)

Could implement build caching:

- Hash source code + dependencies
- Skip build if hash unchanged
- Store in CI cache for faster builds

### Pre-built Layers (Future)

For truly stable dependencies, could:

- Pre-build layer once
- Store in S3 or artifact registry
- Reference by version number

## References

- [The Twelve-Factor App - Build, Release, Run](https://12factor.net/build-release-run)
- [AWS Lambda Deployment Best Practices](https://docs.aws.amazon.com/lambda/latest/dg/best-practices.html)
- [Terraform Best Practices](https://www.terraform-best-practices.com/)
- [Build Architecture Documentation](../build-deploy-architecture.md)

## Related ADRs

- [ADR-003: Docker-Based Lambda Build Process](003-docker-based-lambda-build-process.md)
- [ADR-005: Lambda Layer Architecture](005-lambda-layer-architecture.md)
