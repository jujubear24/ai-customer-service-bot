# ADR-001: Repository Structure and Tooling

**Date:** 2024-01-10
**Status:** Accepted
**Deciders:** Development Team

## Context

We need to establish a consistent repository structure for our AI Customer Service Bot project that supports:

- Multiple Lambda functions with shared code
- Infrastructure as Code with Terraform
- Frontend application with Next.js
- Comprehensive testing at multiple levels
- CI/CD automation

## Decision

We will use a **monorepo structure** with the following organization:

```bash
ai-customer-service-bot/
├── lambda/              # Backend Lambda functions
│   ├── layers/          # Shared Lambda layers
│   └── functions/       # Individual Lambda functions
├── terraform/           # Infrastructure as Code
│   ├── modules/         # Reusable Terraform modules
│   └── environments/    # Environment-specific configs (dev/staging/prod)
├── web/                 # Next.js frontend application
├── tests/               # Integration and E2E tests
├── scripts/             # Utility scripts
└── docs/                # Documentation
    ├── adr/             # Architecture Decision Records
    ├── architecture/    # System design docs
    └── runbooks/        # Operational guides
```

### Tooling Decisions

1. **Dependency Management:** UV (instead of pip)
   - 10-100x faster than pip
   - Better dependency resolution
   - Lock file for reproducible builds
   - Works seamlessly with AWS Lambda

2. **Python Version:** 3.12
   - Latest stable version
   - Better performance than 3.11
   - Improved type hints

3. **Infrastructure as Code:** Terraform
   - Industry standard for AWS
   - Reusable modules
   - Multiple environment support

4. **CI/CD:** GitHub Actions
   - Native GitHub integration
   - Free for public repos
   - Mature ecosystem

5. **Code Quality:**
   - Black (formatting)
   - isort (import sorting)
   - flake8 (linting)
   - mypy (type checking)
   - pre-commit hooks (automated checks)

## Consequences

### Positive

- **Clear organization:** Each component has a dedicated directory
- **Scalability:** Easy to add new Lambda functions or Terraform modules
- **Separation of concerns:** Frontend, backend, and infrastructure are isolated
- **Shared code:** Lambda layers reduce duplication
- **Fast development:** UV speeds up dependency installation significantly
- **Quality assurance:** Pre-commit hooks catch issues before commit

### Negative

- **Learning curve:** Team needs to learn UV if not familiar
- **Monorepo complexity:** More files in single repository
- **Build time:** CI/CD needs to handle multiple components

### Neutral

- **Tooling overhead:** Multiple tools to maintain (Black, mypy, Terraform, etc.)
- **Python 3.12:** Some libraries may not have full support yet

## Alternatives Considered

### Multi-Repo (Separate repositories for frontend, backend, infrastructure)

**Why not chosen:**

- Harder to coordinate changes across repos
- More complex CI/CD setup
- Difficult to share code/types between components
- For a portfolio project, monorepo is simpler

### Poetry instead of UV

**Why not chosen:**

- UV is significantly faster (10-100x)
- Better lock file format
- Growing community adoption
- UV specifically optimized for AWS Lambda use case

### Python 3.11 instead of 3.12

**Why not chosen:**

- 3.12 is stable and production-ready
- Better performance characteristics
- Improved error messages
- Future-proof choice

### pip instead of UV

**Why not chosen:**

- pip is much slower (especially with many dependencies)
- No lock file by default (requirements.txt is insufficient)
- Dependency resolution issues are common
- UV provides better reproducibility

## References

- [UV Documentation](https://github.com/astral-sh/uv)
- [AWS Lambda Best Practices](https://docs.aws.amazon.com/lambda/latest/dg/best-practices.html)
- [Terraform AWS Modules](https://registry.terraform.io/namespaces/terraform-aws-modules)
- [Monorepo Best Practices](https://monorepo.tools/)
