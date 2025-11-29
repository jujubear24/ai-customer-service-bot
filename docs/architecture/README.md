# Architecture Documentation

This directory contains architecture documentation for the AI Customer Service Bot.

---

## Documents

| Document | Description |
|----------|-------------|
| [System Design](./system-design.md) | High-level system architecture, component specifications, security, and observability |
| [Data Flow](./data-flow.md) | Detailed data flow diagrams for intent classification, context building, and DynamoDB access patterns |
| [Build & Deploy Architecture](../build-deploy-architecture.md) | CI/CD pipeline, build process, and deployment workflow |

---

## Architecture Decision Records

Key architectural decisions are documented in [ADRs](../adr/):

| ADR | Title | Status |
|-----|-------|--------|
| [ADR-007](../adr/007-api-gateway-integration-and-request-validation.md) | API Gateway Integration and Request Validation | Accepted |
| [ADR-008](../adr/008-dynamodb-schema-design.md) | DynamoDB Schema Design | Accepted |

---

## Diagrams

All diagrams use [Mermaid](https://mermaid.js.org/) syntax for version control and easy updates. They render automatically on GitHub and in most Markdown viewers.

### Viewing Diagrams

**GitHub:** Diagrams render automatically in `.md` files.

**VS Code:** Install the [Markdown Preview Mermaid Support](https://marketplace.visualstudio.com/items?itemName=bierner.markdown-mermaid) extension.

**CLI:** Use [mermaid-cli](https://github.com/mermaid-js/mermaid-cli) to export as PNG/SVG:

```bash
npm install -g @mermaid-js/mermaid-cli
mmdc -i system-design.md -o system-design.png
```

---

## Quick Reference

### Current State (Phase 1.2)

```bash
Client → API Gateway → Intent Classifier Lambda
                    ↘
         Context Builder Lambda → DynamoDB
```

### Target State (Full)

```bash
Client → CloudFront → WAF → API Gateway → Step Functions
                                              ↓
                    ┌─────────────────────────┼─────────────────────────┐
                    ↓                         ↓                         ↓
            Intent Classifier         Context Builder           Bedrock Handler
                                              ↓                         ↓
                                          DynamoDB              Amazon Bedrock
```

---

## Contributing

When updating architecture documentation:

1. Keep diagrams in Mermaid format for version control
2. Update the "Last Updated" date in each document
3. Cross-reference related ADRs
4. Ensure diagrams render correctly on GitHub before merging
