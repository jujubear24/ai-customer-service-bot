# ADR-003: Docker-Based Lambda Build Process

## Status

Accepted

## Date

2025-11-23

## Context

AWS Lambda functions run on Amazon Linux 2, which is a specific operating system environment.
Python packages that contain native extensions (compiled C/C++/Rust code) must be compiled for the target platform. Examples include:

- `pydantic` (uses Rust via pydantic-core)
- `cryptography`
- `numpy`
- `pandas`

When building Lambda deployment packages on macOS or Windows, the compiled native extensions:
(`.so` files on Linux, `.dylib` on macOS, `.dll` on Windows) are incompatible with the Lambda runtime, causing import errors like:

  ```bash
  ImportError: No module named 'pydantic_core._pydantic_core'
  ```

We need a build process that ensures our Lambda packages are compatible with the AWS Lambda runtime environment, regardless of the developer's local operating system.

## Decision

We will use **Docker with the official AWS Lambda Python base images** (`public.ecr.aws/lambda/python:3.12`) to build all Lambda deployment packages (both layers and functions).

Build script implementation:

```bash
docker run --rm \
  --entrypoint pip \
  -v "$BUILD_DIR":/var/task \
  public.ecr.aws/lambda/python:3.12 \
  install -r requirements.txt -t /var/task/python/ --no-cache-dir
```

This approach:

1. Uses the exact same OS and Python version as Lambda
2. Compiles native extensions for Amazon Linux 2
3. Ensures 100% runtime compatibility
4. Works consistently across all developer platforms (Mac, Windows, Linux)

## Alternatives Considered

### Alternative 1: Build on Developer's Local Machine

**Rejected**: Would work for pure Python packages but fail for packages with native extensions. Different developers on different operating systems would produce incompatible builds.

### Alternative 2: Use AWS SAM Build

**Considered but not chosen**: SAM CLI internally uses Docker and would work, but:

- Adds another tool to the stack (we already use Terraform)
- Less control over the build process
- Would require learning SAM-specific conventions
- More difficult to customize for our specific needs

### Alternative 3: Build on EC2 or CodeBuild

**Rejected**: Would work but adds complexity:

- Requires provisioning and maintaining EC2 instances or CodeBuild projects
- Slower build times (network latency, instance startup)
- More expensive than local Docker builds
- Requires network access and AWS credentials during build

### Alternative 4: Use Pre-built Lambda Layers from Third Parties

**Rejected**:

- Limited control over versions
- Security concerns (trusting third-party builds)
- May not include our specific dependency versions
- Doesn't solve the problem for custom code or function-specific dependencies

### Alternative 5: Build Without Native Extensions

**Rejected**: Would limit us to pure Python packages only, excluding essential tools like:

- Pydantic (data validation)
- Cryptography libraries
- Scientific computing packages (future needs)

## Consequences

### Positive

- ✅ **100% Lambda Compatibility**: Packages always work in Lambda runtime
- ✅ **Cross-Platform Development**: Developers on Mac, Windows, Linux all produce identical builds
- ✅ **Reproducible Builds**: Same inputs always produce same outputs
- ✅ **Official AWS Images**: Using AWS-maintained images ensures compatibility with Lambda updates
- ✅ **Local Development**: Fast builds without requiring AWS credentials or network access
- ✅ **CI/CD Ready**: Easy to integrate into GitHub Actions, GitLab CI, etc.

### Negative

- ⚠️ **Docker Dependency**: All developers must have Docker installed and running
- ⚠️ **Build Time**: Docker builds are slower than pure local builds (2-3 minutes vs 10-30 seconds)
- ⚠️ **Disk Space**: Docker images consume ~500MB each
- ⚠️ **Learning Curve**: Team members need basic Docker knowledge

### Neutral

- 📝 **Build Scripts Required**: Need to maintain build scripts (`build-lambda-layer.sh`, `build-lambdas.sh`)
- 📝 **Documentation**: Must document the Docker requirement and troubleshooting steps

## Implementation Notes

### Build Script Location

- Layer build: `scripts/build-lambda-layer.sh`
- Unified build: `scripts/build-lambdas.sh`

### Docker Image Version Pinning

We use `public.ecr.aws/lambda/python:3.12` (latest 3.12 version). Consider pinning to specific digest in the future for even more reproducibility:

```bash
public.ecr.aws/lambda/python:3.12@sha256:abc123...
```

### Build Optimization

To keep builds fast:

- Use `--no-cache-dir` to avoid storing pip cache
- Clean up unnecessary files (`.dist-info`, `__pycache__`, tests)
- Strip debug symbols from `.so` files
- Layer size kept under 50MB for fast cold starts

### Troubleshooting

Common issues documented in build script comments:

- Docker not running: Clear error message directs users to start Docker
- Permission issues: Mount points use proper permissions
- Network issues: Docker pull failures have retry logic

## References

- [AWS Lambda runtimes](https://docs.aws.amazon.com/lambda/latest/dg/lambda-runtimes.html)
- [Lambda deployment package format](https://docs.aws.amazon.com/lambda/latest/dg/python-package.html)
- [AWS Lambda base images](https://docs.aws.amazon.com/lambda/latest/dg/python-image.html)
- [Build Architecture Documentation](../build-deploy-architecture.md)

## Related ADRs

- [ADR-004: Separation of Build and Deploy Phases](004-separation-of-build-and-deploy-phases.md)
- [ADR-005: Lambda Layer Architecture](005-lambda-layer-architecture.md)
