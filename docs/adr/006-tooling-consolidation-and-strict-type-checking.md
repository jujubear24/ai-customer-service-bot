# ADR-006: Tooling Consolidation and Strict Type Checking

**Date:**

2025-11-23

**Status:**

Accepted

**Deciders:**

Senior Cloud Architect

## Context

Our initial Python code quality stack (``Black``, ``isort``, ``flake8``, ``mypy``) was fragmented, leading to slower execution times locally and in CI.
Furthermore, running ``mypy`` directly on a monorepo structure caused persistent "Duplicate module" errors and did not adequately handle imports from the shared layer.
To ensure production-grade reliability, we needed a single, fast tool for linting/formatting and a robust solution for monorepo type checking.

## Decision

1. **Consolidate Tooling**: We are migrating our linting and formatting pipeline to ``Ruff``. ``Ruff`` replaces the functionality of Black, isort, and Flake8, significantly improving execution speed.
2. **Monorepo Type Checking**:
We resolve the "Duplicate module" error by switching the ``mypy`` hook to run the custom script scripts/lint-lambdas.sh.
This script runs ``mypy`` individually within each function's directory, leveraging the local ``pyproject.toml``'s:
    mypy_path setting (``../../layers/common/Python``) to correctly resolve imports to the shared layer.
3. **Strict Type Enforcement**: We enabled stricter ``mypy`` configuration settings (e.g., ``disallow_untyped_defs``, ``warn_return_any``, ``strict_equality``) to enforce high code quality and prevent,
runtime errors (e.g., forcing type casting for the output of ``json.loads`` and ensuring all handlers return the exact ``LambdaResponse`` type).

## Consequences

### Positive

- **Performance**: Ruff drastically cuts formatting and linting time (10x+ faster), improving developer experience and CI throughput.

- **Quality**: Strict mypy rules ensure all functions have robust type safety, especially when dealing with external I/O and shared layer models.

- **Maintainability**: Simplification of the Python ecosystem down to Ruff and Mypy.

### Negative

- **Initial Overhead**: Required dedicated time to configure mypy_path in all six function packages and fix the resulting type errors across all scaffolded handlers.

### Neutral

- **Tooling Overhead**: Requires the use of a custom shell script to orchestrate Mypy/Ruff, which is acceptable for the monorepo structure.

## Alternatives Considered

### Option 1: Continue using Black/isort/flake8

**Why not chosen**: Sub-optimal performance and maintenance burden compared to a consolidated Rust-based solution like Ruff.


Description and why it was not chosen

### Option 2: Exclude Lambda function source from Mypy

Why not chosen: Sacrifices critical type safety for convenience, directly contradicting our requirement for a production-grade system where type errors should be caught before deployment.

## References

- [ADR-002: UV Dependency Management](002-uv-dependency-management.md)
- [Ruff Documentation](https://docs.astral.sh/ruff/?utm_source=chatgpt.com)
- [Mypy Documentation](https://mypy.readthedocs.io/?utm_source=chatgpt.com)
