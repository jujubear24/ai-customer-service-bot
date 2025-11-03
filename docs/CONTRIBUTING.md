# Contributing Guidelines

Thank you for considering contributing to the AI Customer Service Bot project!

## 📋 Code of Conduct

- Be respectful and inclusive
- Provide constructive feedback
- Focus on the best outcome for the project

## 🎯 Development Workflow

### 1. Branch Naming Convention

```
feature/short-description    # New features
bugfix/issue-description     # Bug fixes
hotfix/critical-fix          # Production hotfixes
docs/what-changed            # Documentation updates
refactor/component-name      # Code refactoring
```

### 2. Commit Message Format

We follow [Conventional Commits](https://www.conventionalcommits.org/):

```bash
<type>(<scope>): <subject>

<body>

<footer>
```

**Types:**

- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation changes
- `style`: Code style changes (formatting, etc.)
- `refactor`: Code refactoring
- `test`: Adding or updating tests
- `chore`: Maintenance tasks

**Examples:**

```bash
feat(lambda): add sentiment analysis to response validator

Integrated Amazon Comprehend for real-time sentiment detection
in customer messages. Sentiment scores are now stored in DynamoDB
and used for escalation scoring.

Closes #123
```

### 3. Pull Request Process

1. **Create a feature branch** from `main`
2. **Make your changes** with clear commits
3. **Write/update tests** (maintain >80% coverage)
4. **Update documentation** if needed
5. **Run all checks** locally:

   ```bash
   make test-all
   make lint
   make typecheck
   ```

6. **Create a PR** with a clear description
7. **Address review feedback** promptly

### 4. Pull Request Template

Your PR should include:

```markdown
## Description
Brief description of changes

## Type of Change
- [ ] Bug fix
- [ ] New feature
- [ ] Breaking change
- [ ] Documentation update

## Testing
- [ ] Unit tests added/updated
- [ ] Integration tests added/updated
- [ ] Manual testing completed

## Checklist
- [ ] Code follows project style guidelines
- [ ] Self-review completed
- [ ] Comments added for complex logic
- [ ] Documentation updated
- [ ] No new warnings generated
- [ ] Tests pass locally
```

## 🧪 Testing Guidelines

### Unit Tests

- Test individual functions in isolation
- Mock external dependencies (AWS services, etc.)
- Aim for >80% code coverage
- Use descriptive test names

```python
def test_calculate_escalation_score_high_priority_customer():
    """Test escalation score for VIP customer with negative sentiment"""
    score = calculate_escalation_score(
        sentiment={'label': 'NEGATIVE', 'score': 0.9},
        rules_violations=[],
        conversation_length=3,
        customer_tier='vip'
    )
    assert score >= 0.5
```

### Integration Tests

- Test interactions between components
- Use test AWS resources when possible
- Clean up resources after tests

### E2E Tests

- Test complete user workflows
- Run against staging environment
- Cover critical paths

## 💻 Coding Standards

### Python

- **Style**: PEP 8 with Black formatter
- **Type hints**: Required for all function signatures
- **Docstrings**: Google style for all public functions
- **Max line length**: 100 characters

```python
from typing import Dict, Any, Optional

def process_message(
    message: str,
    context: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Process incoming customer message.
    
    Args:
        message: Raw message text from customer
        context: Optional conversation context
        
    Returns:
        Processed message with metadata
        
    Raises:
        ValueError: If message is empty
    """
    if not message.strip():
        raise ValueError("Message cannot be empty")
    
    # Implementation...
```

### TypeScript

- **Style**: ESLint + Prettier
- **Types**: Explicit types, avoid `any`
- **Components**: Functional components with hooks
- **File naming**: PascalCase for components, camelCase for utilities

```typescript
interface MessageProps {
  content: string;
  role: 'user' | 'assistant';
  timestamp: Date;
}

export function Message({ content, role, timestamp }: MessageProps): JSX.Element {
  // Implementation...
}
```

### Terraform

- **Format**: `terraform fmt` before commit
- **Variables**: Always include descriptions
- **Outputs**: Document what each output provides
- **Modules**: Reusable, single-responsibility

```hcl
variable "environment" {
  description = "Environment name (dev, staging, prod)"
  type        = string
  validation {
    condition     = contains(["dev", "staging", "prod"], var.environment)
    error_message = "Environment must be dev, staging, or prod."
  }
}
```

## 📝 Documentation Standards

### Code Comments

- Explain **why**, not **what**
- Keep comments up-to-date
- Use TODO/FIXME for temporary notes

### README Files

- Each major directory should have a README
- Include purpose, usage, and examples
- Keep up-to-date with code changes

### Architecture Decision Records (ADRs)

- Document significant architectural decisions
- Use the template in `docs/adr/template.md`
- Number sequentially (001, 002, etc.)

## 🔍 Review Process

### For Reviewers

- Review within 24-48 hours if possible
- Be constructive and specific
- Approve if changes look good
- Request changes if issues found

### For Authors

- Address all comments
- Mark resolved comments
- Re-request review after changes
- Be patient and professional

## 🚀 Release Process

1. **Version Bump**: Update version in relevant files
2. **Changelog**: Update CHANGELOG.md
3. **Tag**: Create git tag `v1.2.3`
4. **Push**: `git push origin v1.2.3`
5. **CI/CD**: GitHub Actions handles deployment

## 🐛 Bug Reports

Use GitHub Issues with the bug template:

```markdown
**Describe the bug**
Clear description of what's wrong

**To Reproduce**
Steps to reproduce the behavior

**Expected behavior**
What should happen

**Screenshots**
If applicable

**Environment**
- OS: [e.g. macOS]
- Version: [e.g. 1.2.3]
- AWS Region: [e.g. us-east-1]
```

## 💡 Feature Requests

Use GitHub Issues with the feature template:

```markdown
**Problem Statement**
What problem does this solve?

**Proposed Solution**
How should it work?

**Alternatives Considered**
What else did you think about?

**Additional Context**
Any other relevant information
```

## ❓ Questions?

- Create a GitHub Discussion
- Tag with `question` label
- Provide context and what you've tried

---

Thank you for contributing! 🎉
