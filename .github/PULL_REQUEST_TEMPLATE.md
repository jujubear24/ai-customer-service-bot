# Pull Request Template

## 📝 Description

Provide a brief description of the changes in this PR

## 🎯 Type of Change

Mark the relevant option with an 'x'

- [ ] 🐛 Bug fix (non-breaking change that fixes an issue)
- [ ] ✨ New feature (non-breaking change that adds functionality)
- [ ] 💥 Breaking change (fix or feature that would cause existing functionality to not work as expected)
- [ ] 📚 Documentation update
- [ ] 🎨 Code refactoring (no functional changes)
- [ ] ⚡ Performance improvement
- [ ] 🔒 Security fix

## 🔗 Related Issues

Link to related issues using #issue_number

Closes #
Related to #

## 🧪 Testing

Describe the tests you ran and how to reproduce them

### Unit Tests

- [ ] Added new unit tests
- [ ] Updated existing unit tests
- [ ] All unit tests pass locally

### Integration Tests

- [ ] Added new integration tests
- [ ] Updated existing integration tests
- [ ] All integration tests pass

### Manual Testing

Describe manual testing steps

- [ ] Tested locally
- [ ] Tested in dev environment
- [ ] Tested edge cases

**Test Configuration:**

- Python version:
- Terraform version:
- AWS Region:

## 📸 Screenshots (if applicable)

<!-- Add screenshots to help explain your changes -->

## ✅ Checklist

<!-- Mark completed items with an 'x' -->

### Code Quality

- [ ] My code follows the project's style guidelines
- [ ] I have performed a self-review of my own code
- [ ] I have commented my code, particularly in hard-to-understand areas
- [ ] My changes generate no new warnings
- [ ] I have run `make check` locally and all checks pass

### Documentation

- [ ] I have updated the documentation accordingly
- [ ] I have updated the README.md if needed
- [ ] I have added/updated docstrings for new functions
- [ ] I have created/updated ADRs for architectural decisions

### Testing

- [ ] I have added tests that prove my fix is effective or that my feature works
- [ ] New and existing unit tests pass locally with my changes
- [ ] I have added integration tests if applicable
- [ ] Test coverage remains above 80%

### Infrastructure

- [ ] I have updated Terraform configurations if needed
- [ ] I have run `terraform plan` and reviewed the changes
- [ ] I have updated environment variables documentation
- [ ] I have considered security implications

### Dependencies

- [ ] I have updated requirements.txt if new Python packages were added
- [ ] I have updated package.json if new Node packages were added
- [ ] I have verified all dependencies are compatible

## 🔍 Review Focus Areas

Highlight areas where you want special attention from reviewers

## 📊 Performance Impact

Describe any performance implications

- [ ] No performance impact
- [ ] Improves performance
- [ ] May impact performance (explain below)

If performance impact, provide details

## 🔒 Security Considerations

Describe any security implications

- [ ] No security impact
- [ ] Improves security
- [ ] May impact security (explain below)

If security impact, provide details

## 💰 Cost Impact

Describe any AWS cost implications

- [ ] No cost impact
- [ ] Reduces cost
- [ ] May increase cost (explain below)

If cost impact, provide details

## 📝 Additional Notes

Any additional information that reviewers should know

## 🚀 Deployment Notes

Special instructions for deploying these changes

- [ ] No special deployment steps required
- [ ] Requires database migration
- [ ] Requires configuration changes
- [ ] Requires manual steps (describe below)

If manual steps required, provide details

---

**By submitting this PR, I confirm that:**

- [ ] I have read and followed the [Contributing Guidelines](../CONTRIBUTING.md)
- [ ] This PR is ready for review
- [ ] I am available to address review feedback
