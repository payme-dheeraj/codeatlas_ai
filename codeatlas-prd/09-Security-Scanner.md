# 09 — Security Scanner

## Overview

The Security Scanner service runs automated security analysis over indexed repositories. It detects hardcoded secrets, performs static application security testing (SAST), analyzes Infrastructure-as-Code (IaC) files, and uses AI to generate targeted remediation suggestions.

---

## Scanning Modules

```
┌─────────────────────────────────────────────────────────┐
│               Security Scanner Service                   │
│                                                          │
│  ┌──────────────────────────────────────────────────┐   │
│  │               Scan Orchestrator                   │   │
│  │          (triggered via Celery task)               │   │
│  └─────────────────────┬────────────────────────────┘   │
│                        │                                 │
│         ┌──────────────┼──────────────────┐             │
│         │              │                  │              │
│  ┌──────▼──────┐ ┌─────▼─────┐  ┌────────▼────────┐   │
│  │  Secrets    │ │   SAST    │  │   IaC Scanner   │   │
│  │  Detector   │ │  Engine   │  │                 │   │
│  │             │ │           │  │  Dockerfile     │   │
│  │ detect-     │ │ semgrep   │  │  docker-compose │   │
│  │  secrets    │ │  rules    │  │  Terraform      │   │
│  │ trufflehog  │ │           │  │  Helm charts    │   │
│  │  patterns   │ │           │  │  K8s manifests  │   │
│  └──────┬──────┘ └─────┬─────┘  └────────┬────────┘   │
│         └──────────────┼──────────────────┘             │
│                        │                                 │
│  ┌─────────────────────▼────────────────────────────┐   │
│  │              Findings Aggregator                  │   │
│  │      Deduplicate, Normalize, Severity Score       │   │
│  └─────────────────────┬────────────────────────────┘   │
│                        │                                 │
│  ┌─────────────────────▼────────────────────────────┐   │
│  │            AI Remediation Generator               │   │
│  │       (LLM generates fix for each finding)        │   │
│  └─────────────────────┬────────────────────────────┘   │
│                        │                                 │
│  ┌─────────────────────▼────────────────────────────┐   │
│  │         PostgreSQL (security_findings)            │   │
│  └──────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────┘
```

---

## Module 1: Secrets Detector

### Detection Methods

| Method | Tool | Examples Detected |
|--------|------|--------------------|
| Regex patterns | Custom + truffleHog rules | AWS keys, GitHub tokens, private keys |
| Entropy analysis | Shannon entropy | High-entropy strings in assignments |
| ML classifier | detect-secrets | Generic high-confidence secrets |
| Git history | truffleHog | Secrets committed and later deleted |

### Secret Categories

```python
SECRET_PATTERNS = {
    "aws_access_key": r"AKIA[0-9A-Z]{16}",
    "aws_secret_key": r"[0-9a-zA-Z/+]{40}",
    "github_token": r"ghp_[0-9a-zA-Z]{36}",
    "github_pat": r"github_pat_[0-9a-zA-Z_]{82}",
    "openai_key": r"sk-[0-9a-zA-Z]{48}",
    "stripe_key": r"sk_live_[0-9a-zA-Z]{24}",
    "jwt_secret": r"(jwt[_-]?secret|JWT_SECRET)\s*[=:]\s*['\"]([^'\"]{16,})['\"]",
    "database_url": r"(DATABASE_URL|DB_URL)\s*[=:]\s*['\"][^'\"]+['\"]",
    "private_key": r"-----BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY-----",
    "google_api": r"AIza[0-9A-Za-z\-_]{35}",
    "slack_token": r"xox[baprs]-([0-9a-zA-Z]{10,48})",
    "generic_password": r"(password|passwd|pwd)\s*[=:]\s*['\"][^'\"]{8,}['\"]",
}
```

### False Positive Reduction
- Skip test files when severity is below Medium
- Allowlist patterns (e.g., example values like `your_api_key_here`)
- Context-aware: `password = ""` is not a secret
- Skip `.example`, `.template`, `.sample` files

---

## Module 2: SAST Engine

### Rule Sets

| Category | Examples | Severity |
|----------|---------|---------|
| Injection | SQL injection, command injection, LDAP injection | Critical |
| XSS | Reflected/stored XSS, unsafe HTML rendering | High |
| SSRF | Unvalidated URL fetch, redirect | High |
| Insecure Deserialization | pickle.loads, eval(), exec() | High |
| Broken Auth | Hardcoded credentials, weak password hashing | High |
| Path Traversal | `os.path.join` with user input | Medium |
| Insecure Crypto | MD5/SHA1 for passwords, ECB mode | Medium |
| XXE | Unsafe XML parsing | Medium |
| Open Redirect | Unvalidated redirect targets | Medium |
| Debug/Logging | Sensitive data in logs | Low |

### Language-Specific Rules

```yaml
# Python rules (semgrep)
rules:
  - id: python.django.security.sql-injection
    pattern: |
      $Q.raw($SQL.format(...))
    severity: CRITICAL

  - id: python.flask.security.debug-true
    pattern: |
      app.run(debug=True)
    severity: HIGH

  - id: python.requests.security.ssrf
    pattern: |
      requests.get($URL, ...)
    severity: MEDIUM
```

---

## Module 3: IaC Scanner

### Dockerfile Rules

| Rule | Severity |
|------|---------|
| Running as root (`USER root` or no USER directive) | High |
| `latest` tag for base images | Medium |
| `ADD` instead of `COPY` (potential remote fetch) | Medium |
| Secrets in `ENV` or `ARG` | Critical |
| No health check defined | Low |
| `--no-check-certificate` in wget/curl | High |

### Kubernetes Manifest Rules

| Rule | Severity |
|------|---------|
| `privileged: true` container | Critical |
| No resource limits defined | Medium |
| `hostNetwork: true` | High |
| `hostPID: true` | High |
| Secrets in plain ConfigMap | Critical |
| No readiness/liveness probes | Low |
| `runAsRoot: true` or no securityContext | High |
| `allowPrivilegeEscalation: true` | High |

### Terraform Rules

| Rule | Severity |
|------|---------|
| S3 bucket public access enabled | High |
| Security group `0.0.0.0/0` on port 22 | Critical |
| RDS instance publicly accessible | High |
| Unencrypted EBS volume | Medium |
| IAM `*` action with `*` resource | Critical |
| CloudTrail logging disabled | Medium |

---

## AI Remediation Generation

For each finding, the AI Service generates a concrete fix:

### Prompt Template

```
You are a security expert. A security vulnerability was found in a software repository.

FINDING:
- Type: {finding_type}
- Severity: {severity}
- File: {file_path}
- Lines: {start_line}-{end_line}
- Rule: {rule_id}
- Description: {description}

VULNERABLE CODE:
```{language}
{vulnerable_snippet}
```

Provide:
1. A brief explanation of why this is a vulnerability (2-3 sentences)
2. The fixed code
3. Any additional security recommendations

RESPONSE:
```

### Example Remediation Output

```json
{
  "vulnerability": "SQL injection via string concatenation. User input is directly embedded into SQL queries without parameterization, allowing attackers to manipulate the query structure.",
  "fixed_code": "cursor.execute('SELECT * FROM users WHERE id = %s', (user_id,))",
  "recommendations": [
    "Always use parameterized queries or prepared statements",
    "Consider using an ORM (SQLAlchemy) to abstract SQL construction",
    "Validate and sanitize all user inputs before use"
  ]
}
```

---

## Findings Severity Scoring

| Severity | CVSS Range | Action Required |
|---------|-----------|----------------|
| **Critical** | 9.0–10.0 | Fix immediately; block deployment |
| **High** | 7.0–8.9 | Fix within current sprint |
| **Medium** | 4.0–6.9 | Fix within next sprint |
| **Low** | 0.1–3.9 | Fix in next available cycle |
| **Info** | 0.0 | Awareness only |

---

## Report Export Formats

| Format | Use Case |
|--------|---------|
| **JSON** | API integration, CI/CD pipelines |
| **SARIF 2.1** | GitHub Code Scanning, VS Code integration |
| **PDF** | Executive reports, compliance audits |
| **CSV** | Spreadsheet analysis |
| **Markdown** | Documentation embedding |

---

## CI/CD Integration

Security scans can be triggered via API for CI/CD integration:

```bash
# Trigger a scan via API
curl -X POST https://codeatlas.example.com/api/security/scan \
  -H "Authorization: Bearer $API_KEY" \
  -d '{"repo_id": "uuid", "scan_types": ["secrets", "sast", "iac"]}'

# Check scan status
curl https://codeatlas.example.com/api/security/scan/{scan_id}/status

# Download SARIF report
curl https://codeatlas.example.com/api/security/report/{scan_id}?format=sarif
```
