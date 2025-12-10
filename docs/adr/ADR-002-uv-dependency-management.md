# ADR-002: Using UV for Python Dependency Management

**Date:** 2024-01-10
**Status:** Accepted
**Deciders:** Development Team

## Context

Python dependency management is a critical aspect of our project, especially with:

- Multiple Lambda functions with different dependencies
- Need for reproducible builds in CI/CD
- Lambda deployment packages that must be fast to build
- Development workflow that needs to be efficient

Traditional options include pip, poetry, and pipenv.

## Decision

We will use **UV** as our primary dependency management tool.

### Implementation

1. **Project configuration** in `pyproject.toml`
2. **Lock file** (`uv.lock`) committed to repository
3. **requirements.txt** generated for Lambda compatibility
4. **Makefile commands** for common UV operations

```bash
# Install dependencies
uv sync --all-extras

# Add new dependency
uv add package-name

# Update dependencies
uv sync --upgrade
```

## Consequences

### Positive

- **Speed:** 10-100x faster than pip (written in Rust)
  - Local dev: `uv sync` takes ~3 seconds vs pip's ~45 seconds
  - CI/CD: Significantly faster build times

- **Reliability:** Lock file ensures exact reproducible builds
  - Everyone gets the same dependency versions
  - CI/CD matches local environment

- **Lambda Compatible:** Works seamlessly with AWS Lambda
  - Can generate pip-compatible requirements.txt
  - Fast package installation in CI/CD

- **Better Dependency Resolution:** Handles conflicts better than pip
  - Automatically resolves version conflicts
  - Clear error messages when resolution fails

- **Modern Tooling:** Active development, growing adoption
  - Used by major Python projects
  - Regular updates and improvements

### Negative

- **Learning Curve:** Team needs to learn UV commands
  - Different from familiar pip workflow
  - Need to understand lock file concept

- **Newer Tool:** Less mature than pip (but stable)
  - Fewer Stack Overflow answers
  - Some edge cases may not be documented

- **Additional Tool:** One more tool to install and maintain
  - Needs to be installed in CI/CD
  - Developers need to install locally

### Neutral

- **pyproject.toml required:** Modern Python standard anyway
- **Lock file in git:** Standard practice for applications

## Alternatives Considered

### Option 1: pip with requirements.txt

**Pros:**

- Industry standard, everyone knows it
- No additional tools needed
- Simple to understand

**Cons:**

- Very slow (especially with many dependencies)
- No lock file (requirements.txt is insufficient)
- Poor dependency resolution
- Manual version pinning is error-prone

**Why not chosen:** Speed and reliability are critical for developer experience and CI/CD performance.

### Option 2: Poetry

**Pros:**

- Popular, mature tool
- Good lock file support
- Nice CLI experience

**Cons:**

- Slower than UV (though faster than pip)
- More complex configuration
- Can have issues with Lambda deployment
- Heavy dependency itself

**Why not chosen:** UV is significantly faster and simpler for our Lambda-focused use case.

### Option 3: pipenv

**Pros:**

- Virtual environment + dependencies in one tool
- Lock file support

**Cons:**

- Slow (similar to pip)
- Project seems less actively maintained
- Lock file can be problematic

**Why not chosen:** Performance and active development favor UV.

## Migration Strategy

For existing pip-based projects:

```bash
# 1. Create pyproject.toml from requirements.txt
uv init

# 2. Sync dependencies
uv sync --all-extras

# 3. Generate requirements.txt for Lambda
uv pip compile pyproject.toml -o requirements.txt
```

## Success Metrics

- **Build time:** Should see >10x improvement in dependency installation
- **Reproducibility:** Zero "works on my machine" issues
- **Developer satisfaction:** Faster local development workflow

## References

- [UV GitHub Repository](https://github.com/astral-sh/uv)
- [UV Benchmarks](https://github.com/astral-sh/uv#benchmarks)
- [UV with AWS Lambda Discussion](https://github.com/astral-sh/uv/discussions/1461)
- [Python Packaging Guide](https://packaging.python.org/)
