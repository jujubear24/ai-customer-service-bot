# ADR-005: Lambda Layer Architecture

## Status

Accepted

## Date

2025-11-23

## Context

- AWS Lambda functions need access to common code and dependencies.
- As we build multiple Lambda functions for the customer service bot (intent-classifier, context-builder, bedrock-handler, etc.), we need a strategy for sharing code and libraries.

Without a sharing mechanism, we face:

1. **Code Duplication**: Same utility functions copied across multiple functions
2. **Inconsistent Dependencies**: Each function manages its own `boto3`, `pydantic`, etc.
3. **Large Deployment Packages**: Each function includes full dependencies (~15MB each)
4. **Slow Deployments**: Uploading same dependencies multiple times
5. **Maintenance Overhead**: Bug fixes require updating multiple functions
6. **Version Drift**: Functions end up with different library versions

AWS Lambda Layers provide a way to share code and dependencies across functions, but we need to decide:

- One layer vs multiple layers?
- What goes in the layer vs function packages?
- How to manage layer versions?

## Decision

We will use a **single shared Lambda layer** containing:

### Layer Contents (`shared-layer.zip`)

1. **Common Dependencies** (installed via pip):
   - `boto3` >= 1.35.0 (AWS SDK)
   - `aws-lambda-powertools[tracer]` >= 2.31.0 (logging, tracing, metrics)
   - `pydantic` >= 2.5.0 (data validation)
   - `redis` >= 5.0.0 (caching - for future use)

2. **Shared Custom Code** (`python/shared/`):
   - `config.py` - Environment configuration management
   - `types.py` - Pydantic models (IntentClassification, etc.)
   - `exceptions.py` - Custom exception classes
   - `utils.py` - Helper functions (format_response, parse_json_body)
   - `logger.py` - Powertools logger setup
   - `metrics.py` - CloudWatch metrics utilities
   - `tracing.py` - X-Ray tracing utilities
   - `cache_client.py` - Redis client (prepared for future)

### Function Package Contents

Each function package contains **only**:

- Function-specific source code (`handler.py`, business logic files)
- Function-specific dependencies (if any)

### Layer Distribution

- All Lambda functions reference the same layer ARN
- Layer is versioned (e.g., `shared-layer:1`, `shared-layer:2`)
- Functions update layer version as needed

## Alternatives Considered

### Alternative 1: No Layers - All Code in Functions

**Rejected**: Each function packages everything independently.

Pros:

- Simple mental model
- No layer management

Cons:

- Massive code duplication
- 15MB+ deployment packages per function
- Slow deployments (uploading dependencies repeatedly)
- Inconsistent versions across functions
- Hard to update shared code (change in 6 places)

### Alternative 2: Multiple Specialized Layers

**Rejected**: Separate layers for different concerns.

Example:

- `aws-layer` (boto3, powertools)
- `data-layer` (pydantic, redis)
- `custom-layer` (our shared code)

Pros:

- Fine-grained control
- Can update layers independently
- Might reduce some function cold starts

Cons:

- **Layer Limit**: Lambda supports max 5 layers per function
- Complex dependency management
- Unclear boundaries (where does each package go?)
- More layers to maintain and version
- Overkill for current scale

### Alternative 3: Inline Shared Code (No Dependencies in Layer)

**Rejected**: Layer has only our code, functions install dependencies.

Pros:

- Shared code is managed
- Functions control dependency versions

Cons:

- Still duplicating large dependencies (pydantic ~5MB)
- Slow function deployments
- Defeats primary purpose of layers

### Alternative 4: Vendor All Dependencies in Git

**Rejected**: Check dependencies into source control.

Pros:

- No build step needed
- Reproducible

Cons:

- **Huge Git Repo**: Dependencies are ~15MB
- Slow git operations
- Binary files in Git (bad practice)
- Still need layer or duplication
- Hard to update dependencies

## Consequences

### Positive

#### Development Efficiency

- ✅ **Single Update Point**: Fix bug once, all functions get it
- ✅ **Consistent Dependencies**: All functions use same library versions
- ✅ **Fast Function Deployments**: Function ZIPs are ~10KB (code only)
- ✅ **Shared Types**: Pydantic models defined once, used everywhere
- ✅ **Centralized Logging**: Common logging configuration

#### Operational Benefits

- ✅ **Faster Cold Starts**: Layer cached by Lambda runtime
- ✅ **Efficient Storage**: 15MB stored once, not per function
- ✅ **Version Control**: Layer versions for rollback capability
- ✅ **Easy Updates**: Update layer, redeploy functions (or gradual rollout)

#### Code Quality

- ✅ **DRY Principle**: Don't Repeat Yourself
- ✅ **Single Source of Truth**: Shared types prevent drift
- ✅ **Easier Testing**: Test shared code once
- ✅ **Clear Boundaries**: Shared vs function-specific code

### Negative

#### Complexity

- ⚠️ **Layer Management**: Must version and deploy layers separately
- ⚠️ **Coordination Required**: Multiple functions depend on layer
- ⚠️ **Breaking Changes**: Layer changes can break multiple functions
- ⚠️ **Build Process**: Requires Docker build for layer

#### Constraints

- ⚠️ **Size Limit**: 250MB unzipped layer limit (currently using ~50MB)
- ⚠️ **Coupling**: Functions coupled to layer version
- ⚠️ **Deployment Order**: Must deploy layer before functions

### Mitigations

To address the negatives:

1. **Semantic Versioning**: Layer versions follow semver (breaking changes = major version)
2. **Gradual Rollout**: Test new layer with one function before updating all
3. **Compatibility Testing**: Test layer changes with all functions before release
4. **Documentation**: Clear guidelines on what belongs in layer vs functions
5. **Size Monitoring**: Track layer size, alert if approaching 200MB

### Neutral

- 📝 **Layer ARN Management**: Terraform outputs layer ARN for function references
- 📝 **Build Script**: `build-lambda-layer.sh` handles layer packaging
- 📝 **Import Path**: Functions import via `from shared import ...`

## Design Principles

### What Goes in the Layer?

**Include if:**

- ✅ Used by 2+ functions
- ✅ Stable, rarely changes
- ✅ General-purpose utility
- ✅ Core dependency (boto3, powertools, pydantic)

**Exclude if:**

- ❌ Function-specific logic
- ❌ Experimental/unstable code
- ❌ Function-unique dependencies
- ❌ Frequently changing code

### Layer Update Strategy

- **Patch versions** (1.0.0 → 1.0.1): Bug fixes, safe to auto-update
- **Minor versions** (1.0.0 → 1.1.0): New features, test before updating
- **Major versions** (1.0.0 → 2.0.0): Breaking changes, coordinated update

## Implementation Details

### Layer Structure

```bash
shared-layer.zip
└── python/
    ├── shared/                         # Our code
    │   ├── __init__.py
    │   ├── config.py
    │   ├── types.py
    │   ├── utils.py
    │   ├── exceptions.py
    │   ├── logger.py
    │   ├── metrics.py
    │   ├── tracing.py
    │   └── cache_client.py
    ├── boto3/                          # Dependencies
    ├── pydantic/
    ├── aws_lambda_powertools/
    └── redis/
```

### Lambda Runtime Paths

When a Lambda function uses the layer:

```bash
/opt/python/shared/        # Layer code (accessible)
/var/task/handler.py       # Function code
```

### Import in Functions

```python
# Functions import shared code naturally
from shared.config import Config
from shared.types import IntentClassification
from shared.utils import format_response
```

### Terraform Configuration

```hcl
# Layer
resource "aws_lambda_layer_version" "shared" {
  filename            = "builds/shared-layer.zip"
  layer_name          = "${var.project_name}-shared-layer-${var.environment}"
  compatible_runtimes = ["python3.12"]
  source_code_hash    = filebase64sha256("builds/shared-layer.zip")
}

# Function references layer
resource "aws_lambda_function" "intent_classifier" {
  layers = [aws_lambda_layer_version.shared.arn]
  # ...
}
```

## Performance Considerations

### Cold Start Impact

**Minimal**: Layers are cached by Lambda runtime. First invocation pays cold start cost, subsequent invocations reuse cached layer.

### Layer Size Optimization

Current optimizations in `build-lambda-layer.sh`:

- Remove `__pycache__` directories
- Remove `.dist-info` directories
- Remove test files
- Strip debug symbols from `.so` files
- Current size: ~15MB zipped, ~50MB unzipped

### Future Optimizations

If layer grows too large:

1. Remove unused dependencies
2. Use slim/minimal package versions
3. Consider splitting into app layer + dependency layer
4. Pre-compile Python bytecode

## Future Considerations

### When to Split the Layer

Consider splitting if:

- Layer approaches 200MB unzipped
- Functions have very different dependency needs
- Deployment becomes problematic
- Update frequency varies significantly

### Potential Future Layers

- `ml-layer`: If we add ML models (scikit-learn, tensorflow)
- `data-layer`: If we add heavy data processing (pandas, numpy)
- Keep current `shared-layer` for common utilities

### Layer Versioning Strategy

Future improvement: Pin layer versions in function code

```python
# handler.py
REQUIRED_LAYER_VERSION = "1.5.0"
# Validate at import time
```

## Monitoring

### Layer Usage Metrics

Track:

- Layer size over time
- Number of functions using layer
- Update frequency
- Cold start times with layer

### Alerts

- Layer size approaching 200MB
- Failed layer updates
- Functions using outdated layers (future)

## References

- [AWS Lambda Layers](https://docs.aws.amazon.com/lambda/latest/dg/configuration-layers.html)
- [Lambda Layer Best Practices](https://aws.amazon.com/blogs/compute/working-with-lambda-layers-and-extensions-in-container-images/)
- [Layer Size Limits](https://docs.aws.amazon.com/lambda/latest/dg/gettingstarted-limits.html)

## Related ADRs

- [ADR-003: Docker-Based Lambda Build Process](003-docker-based-lambda-build-process.md)
- [ADR-004: Separation of Build and Deploy Phases](004-separation-of-build-and-deploy-phases.md)
