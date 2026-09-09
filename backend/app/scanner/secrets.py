"""Secrets detector — regex patterns, entropy analysis, and allowlist filtering.

Detection strategy (in order):
1. Regex pattern matching against all PRD-specified secret categories.
2. Shannon entropy analysis on long alphanumeric strings (potential keys).
3. Context-aware false-positive reduction (empty strings, example values, …).
4. Path-based allowlisting (.example, .template, .sample, test files for low-sev).
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from pathlib import Path

# ── Secret patterns (from PRD) ────────────────────────────────────────────────

SECRET_PATTERNS: dict[str, tuple[str, str, float]] = {
    # (pattern, category, cvss_score)
    "aws_access_key":     (r"AKIA[0-9A-Z]{16}", "cloud_credential", 9.0),
    "aws_secret_key":     (r"(?<![A-Za-z0-9/+])[A-Za-z0-9/+]{40}(?![A-Za-z0-9/+])", "cloud_credential", 9.0),
    "github_token":       (r"ghp_[0-9a-zA-Z]{36}", "vcs_token", 8.0),
    "github_pat":         (r"github_pat_[0-9a-zA-Z_]{82}", "vcs_token", 8.5),
    "openai_key":         (r"sk-[0-9a-zA-Z]{48}", "api_key", 7.5),
    "stripe_live_key":    (r"sk_live_[0-9a-zA-Z]{24}", "payment_credential", 9.5),
    "jwt_secret":         (r'(jwt[_-]?secret|JWT_SECRET)\s*[=:]\s*[\'"]([^\'"]{16,})[\'"]', "auth_secret", 8.0),
    "database_url":       (r'(DATABASE_URL|DB_URL)\s*[=:]\s*[\'"][^\'"]+[\'"]', "connection_string", 7.0),
    "private_key_header": (r"-----BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY-----", "private_key", 10.0),
    "google_api_key":     (r"AIza[0-9A-Za-z\-_]{35}", "api_key", 7.5),
    "slack_token":        (r"xox[baprs]-([0-9a-zA-Z]{10,48})", "api_key", 7.0),
    "generic_password":   (r'(password|passwd|pwd)\s*[=:]\s*[\'"][^\'"]{8,}[\'"]', "credential", 6.0),
    "heroku_api_key":     (r"[hH]eroku.*[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}", "api_key", 7.0),
    "sendgrid_api_key":   (r"SG\.[0-9A-Za-z\-_]{22}\.[0-9A-Za-z\-_]{43}", "api_key", 7.5),
    "twilio_sid":         (r"AC[0-9a-fA-F]{32}", "api_key", 7.0),
}

# Strings that indicate example/placeholder values — suppress finding
_ALLOWLIST_VALUES = frozenset({
    "your_api_key_here",
    "your-secret-key",
    "changeme",
    "example",
    "placeholder",
    "xxx",
    "xxxxxxxx",
    "your_token",
    "insert_key",
    "<your-key>",
    "REPLACE_ME",
    "TODO",
})

# File extensions/patterns to skip entirely
_SKIP_EXTENSIONS = frozenset({
    ".example", ".sample", ".template", ".tpl",
    ".test", ".spec", ".fixture",
})

# Minimum Shannon entropy to flag a random-looking string as a secret
_MIN_ENTROPY = 4.5
# Minimum length for entropy scan targets
_MIN_SECRET_LEN = 20


@dataclass
class RawFinding:
    """A single detected secret finding before normalization.

    Attributes:
        rule_id: Rule identifier string.
        title: Short finding title.
        description: Longer description.
        severity: critical | high | medium | low | info.
        cvss_score: Numeric CVSS score.
        file_path: Relative path of the file.
        start_line: 1-indexed line number.
        end_line: 1-indexed end line.
        snippet: Matched text (redacted if needed).
        category: Secret category slug.
        extra: Additional metadata.
    """

    rule_id: str
    title: str
    description: str
    severity: str
    cvss_score: float
    file_path: str
    start_line: int
    end_line: int
    snippet: str
    category: str
    extra: dict = field(default_factory=dict)


def _shannon_entropy(text: str, charset: str = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/=") -> float:
    """Calculate Shannon entropy of a string over the given character set.

    Args:
        text: Input string.
        charset: Characters to include in probability mass.

    Returns:
        Entropy value (0.0 – log2(len(charset))).
    """
    filtered = [c for c in text if c in charset]
    if not filtered:
        return 0.0
    freq: dict[str, int] = {}
    for c in filtered:
        freq[c] = freq.get(c, 0) + 1
    total = len(filtered)
    return -sum((count / total) * math.log2(count / total) for count in freq.values())


def _should_skip_path(file_path: str) -> bool:
    """Return True if this file path should be excluded from secret scanning.

    Args:
        file_path: Relative file path.

    Returns:
        True if the file should be skipped.
    """
    p = Path(file_path)
    for suffix in p.suffixes:
        if suffix.lower() in _SKIP_EXTENSIONS:
            return True
    name_lower = p.name.lower()
    return any(kw in name_lower for kw in (".example", ".sample", ".template"))


def _is_likely_placeholder(matched_value: str) -> bool:
    """Return True if the matched string looks like a placeholder.

    Args:
        matched_value: The extracted secret value.

    Returns:
        True if it matches common placeholder patterns.
    """
    lower = matched_value.lower().strip()
    if lower in _ALLOWLIST_VALUES:
        return True
    if not lower:
        return True
    # All same character repeated (e.g. "xxxxxxxxxx")
    if len(set(lower)) <= 2:
        return True
    return False


def _cvss_to_severity(cvss: float) -> str:
    """Convert a CVSS score to a severity label.

    Args:
        cvss: CVSS numeric score (0.0-10.0).

    Returns:
        Severity label string.
    """
    if cvss >= 9.0:
        return "critical"
    elif cvss >= 7.0:
        return "high"
    elif cvss >= 4.0:
        return "medium"
    elif cvss > 0:
        return "low"
    return "info"


def scan_file_for_secrets(file_path: str, source: str) -> list[RawFinding]:
    """Scan a single file's source text for secrets using regex + entropy.

    Args:
        file_path: Relative file path (used for context and skipping).
        source: Full file source text.

    Returns:
        List of RawFinding instances (may be empty).
    """
    if _should_skip_path(file_path):
        return []

    findings: list[RawFinding] = []
    lines = source.splitlines()
    is_test_file = any(
        kw in file_path.lower()
        for kw in ("/test", "/tests/", "_test.", ".spec.", "_spec.")
    )

    # ── Pattern scan ─────────────────────────────────────────────────────────
    for rule_id, (pattern, category, cvss) in SECRET_PATTERNS.items():
        severity = _cvss_to_severity(cvss)

        # In test files, skip low/info findings
        if is_test_file and severity in ("low", "info", "medium"):
            continue

        for i, line in enumerate(lines, start=1):
            for match in re.finditer(pattern, line, re.IGNORECASE):
                matched = match.group(0)
                if _is_likely_placeholder(matched):
                    continue
                findings.append(
                    RawFinding(
                        rule_id=f"secrets.{rule_id}",
                        title=f"Potential {rule_id.replace('_', ' ').title()} detected",
                        description=(
                            f"A pattern matching a {rule_id.replace('_', ' ')} was found "
                            f"at line {i}. Hardcoded credentials expose systems to compromise."
                        ),
                        severity=severity,
                        cvss_score=cvss,
                        file_path=file_path,
                        start_line=i,
                        end_line=i,
                        snippet=_redact_snippet(line.strip(), matched),
                        category=category,
                        extra={"rule_id": rule_id, "match_start": match.start()},
                    )
                )

    # ── Entropy scan ──────────────────────────────────────────────────────────
    # Only scan non-test files for high-entropy strings
    if not is_test_file:
        _entropy_scan(file_path, lines, findings)

    return findings


def _entropy_scan(file_path: str, lines: list[str], findings: list[RawFinding]) -> None:
    """Append entropy-based findings to the accumulator.

    Looks for long alphanumeric tokens in assignment statements that have
    Shannon entropy above the threshold, suggesting a random secret.

    Args:
        file_path: Relative file path.
        lines: Source lines (1-indexed externally).
        findings: Accumulator list to append to.
    """
    # Look for: identifier = "long_random_string"
    assign_re = re.compile(r'[\'"]([\w+/=\-]{' + str(_MIN_SECRET_LEN) + r',})[\'"]')
    for i, line in enumerate(lines, start=1):
        for match in assign_re.finditer(line):
            token = match.group(1)
            entropy = _shannon_entropy(token)
            if entropy < _MIN_ENTROPY:
                continue
            if _is_likely_placeholder(token):
                continue
            findings.append(
                RawFinding(
                    rule_id="secrets.high_entropy_string",
                    title="High-entropy string detected",
                    description=(
                        f"A string with Shannon entropy {entropy:.2f} was found at line {i}. "
                        "High-entropy strings in assignments often indicate hardcoded secrets."
                    ),
                    severity="medium",
                    cvss_score=5.0,
                    file_path=file_path,
                    start_line=i,
                    end_line=i,
                    snippet=_redact_snippet(line.strip(), token),
                    category="high_entropy",
                    extra={"entropy": round(entropy, 3), "token_length": len(token)},
                )
            )


def _redact_snippet(line: str, secret: str) -> str:
    """Replace the matched secret in the snippet with a redacted marker.

    Args:
        line: The source line.
        secret: The matched secret value to redact.

    Returns:
        Line with secret replaced by ``[REDACTED]``.
    """
    return line.replace(secret, "[REDACTED]")
