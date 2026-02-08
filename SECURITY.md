# Security Policy

Mai-Tai takes security seriously. This document outlines our security practices and how to report vulnerabilities.

## Security Features

### Architecture

Mai-Tai is designed with security as a core principle:

- **100% Local by Default**: All data stays on your machine when running locally
- **No Cloud Required**: The self-hosted version requires no external services
- **Minimal Attack Surface**: Simple architecture with clear boundaries

### Authentication & Authorization

- **Google IAP Integration**: Production deployments use Google Identity-Aware Proxy
- **API Key Authentication**: Secure, hashed API keys for MCP server connections
- **Session Management**: JWT tokens with configurable expiration
- **No Plaintext Storage**: API keys are SHA-256 hashed before storage

### Data Protection

- **Local Database**: PostgreSQL runs locally in Docker
- **No Telemetry**: Zero usage tracking or analytics
- **No External Calls**: The app makes no calls to external services
- **Workspace Isolation**: Each workspace has its own API key and data

### Infrastructure Security

- **Container Isolation**: Frontend, backend, and database run in separate containers
- **Non-Root Containers**: Services run as non-privileged users
- **Network Segmentation**: Internal network for service-to-service communication

## CI/CD Security

Every pull request is automatically checked for:

| Check | Tool | What It Does |
|-------|------|--------------|
| Vulnerability Scan | Trivy | Scans dependencies for known CVEs |
| Static Analysis | CodeQL | Finds security issues in code |
| Secret Detection | GitGuardian | Prevents leaked credentials |
| Type Safety | TypeScript | Catches type-related bugs |
| Lint | Ruff | Enforces Python best practices |

### Dependency Management

- Dependencies are pinned to specific versions
- Trivy blocks PRs with CRITICAL or HIGH severity vulnerabilities
- Regular dependency updates via automated scanning

## Reporting a Vulnerability

If you discover a security vulnerability, please report it responsibly:

1. **Do NOT** open a public issue
2. Email security concerns to the maintainers
3. Include:
   - Description of the vulnerability
   - Steps to reproduce
   - Potential impact
   - Suggested fix (if any)

We aim to respond within 48 hours and will work with you to resolve the issue.

## Security Checklist for Contributors

Before submitting a PR:

- [ ] No secrets or credentials in code
- [ ] No hardcoded API keys or tokens
- [ ] Input validation on all user inputs
- [ ] SQL queries use parameterized statements
- [ ] No `eval()` or dynamic code execution
- [ ] Dependencies are from trusted sources
- [ ] HTTPS for all external URLs

## Known Security Considerations

### Local Development

When running locally (`./dev.sh local up`):

- The database is not encrypted at rest
- Default credentials are used (change for production)
- CORS is permissive for development ease

### Production Deployment

For production deployments, ensure:

- [ ] Change all default credentials
- [ ] Enable HTTPS/TLS
- [ ] Configure proper CORS origins
- [ ] Set secure cookie flags
- [ ] Enable Google IAP or equivalent auth
- [ ] Use managed database with encryption
- [ ] Set up log monitoring

## Version Support

| Version | Supported |
|---------|-----------|
| Latest  | ✅ Yes |
| < 1.0   | ⚠️ Best effort |

We only actively maintain the latest release. Please keep your installation up to date.

