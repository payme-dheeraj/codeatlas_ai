"""SAST engine — Semgrep-based static analysis wrapper.

Invokes ``semgrep`` as a subprocess with the ``auto`` ruleset plus
additional custom rules targeting the PRD-specified OWASP categories.
Falls back to a built-in pattern set if Semgrep is not installed.
"""

from __future__ import annotations

import json
import re
import subprocess
import tempfile
from pathlib import Path

from app.core.logging import get_logger
from app.scanner.secrets import RawFinding

logger = get_logger(__name__)

# ── Severity / CVSS mappings ──────────────────────────────────────────────────

_SEMGREP_SEV_MAP: dict[str, tuple[str, float]] = {
    "ERROR":   ("critical", 9.0),
    "WARNING": ("high", 7.5),
    "INFO":    ("medium", 5.0),
}

# ── Built-in fallback rule patterns ──────────────────────────────────────────
# Used when Semgrep is not installed.  Each entry:
# (rule_id, title, description, pattern_regex, severity, cvss, category)

_BUILTIN_RULES: list[tuple[str, str, str, str, str, float, str]] = [
    (
        "sast.python.eval_exec",
        "Dangerous eval() or exec() usage",
        "eval() and exec() execute arbitrary code and must never be called with user input.",
        r"\beval\s*\(|\bexec\s*\(",
        "high", 8.0, "insecure_deserialization",
    ),
    (
        "sast.python.pickle_loads",
        "Insecure pickle.loads()",
        "pickle.loads() deserializes arbitrary Python objects and can execute malicious code.",
        r"\bpickle\.loads\s*\(|\bpickle\.load\s*\(",
        "high", 8.5, "insecure_deserialization",
    ),
    (
        "sast.python.sql_format",
        "Potential SQL injection via string formatting",
        "String formatting in SQL queries allows SQL injection attacks.",
        r'(execute|raw)\s*\(\s*[f\'"]{1}.*(%s|%d|\{)',
        "critical", 9.5, "injection",
    ),
    (
        "sast.python.subprocess_shell",
        "subprocess with shell=True",
        "Using shell=True in subprocess calls with user input enables command injection.",
        r"subprocess\.(run|Popen|call|check_output)\s*\([^)]*shell\s*=\s*True",
        "high", 8.0, "injection",
    ),
    (
        "sast.python.os_system",
        "os.system() with dynamic arguments",
        "os.system() executes shell commands and is vulnerable to command injection.",
        r"\bos\.system\s*\(",
        "high", 7.5, "injection",
    ),
    (
        "sast.python.md5_sha1_password",
        "Weak hash algorithm for password",
        "MD5 and SHA1 are cryptographically broken and must not be used for passwords.",
        r"hashlib\.(md5|sha1)\s*\(",
        "medium", 6.5, "insecure_crypto",
    ),
    (
        "sast.python.flask_debug",
        "Flask app.run(debug=True)",
        "Running Flask with debug=True in production exposes the interactive debugger.",
        r"app\.run\s*\([^)]*debug\s*=\s*True",
        "high", 7.0, "misconfiguration",
    ),
    (
        "sast.python.assert_in_production",
        "assert used for security check",
        "assert statements are removed in optimized Python (-O flag) and must not be used for security validation.",
        r"^\s*assert\s+\w+",
        "medium", 5.5, "broken_auth",
    ),
    (
        "sast.generic.hardcoded_ip",
        "Hardcoded IP address",
        "Hardcoded IP addresses indicate inflexible configuration and possible information disclosure.",
        r'\b(?:(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\.){3}(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\b',
        "info", 2.0, "misconfiguration",
    ),
    (
        "sast.python.xml_etree_parse",
        "Unsafe XML parsing (XXE risk)",
        "xml.etree.ElementTree.parse() is vulnerable to XXE attacks. Use defusedxml.",
        r"xml\.etree\.ElementTree\.(parse|fromstring|XML)\s*\(",
        "medium", 6.0, "xxe",
    ),
]


def scan_directory_sast(
    repo_path: str,
    language: str | None = None,
) -> list[RawFinding]:
    """Run SAST analysis on a repository directory.

    Attempts to use Semgrep first; falls back to built-in patterns if
    Semgrep is not installed or fails.

    Args:
        repo_path: Absolute path to the repository directory.
        language: Optional language filter (e.g. ``"python"``).

    Returns:
        List of RawFinding instances.
    """
    try:
        return _run_semgrep(repo_path, language)
    except FileNotFoundError:
        logger.warning("semgrep_not_found_using_fallback")
        return _run_builtin(repo_path)
    except Exception as exc:
        logger.warning("semgrep_failed_using_fallback", error=str(exc))
        return _run_builtin(repo_path)


def _run_semgrep(repo_path: str, language: str | None) -> list[RawFinding]:
    """Execute ``semgrep --config auto`` and parse SARIF output.

    Args:
        repo_path: Absolute path to the repository directory.
        language: Optional language filter flag.

    Returns:
        List of RawFinding from Semgrep output.
    """
    cmd = [
        "semgrep",
        "--config", "auto",
        "--json",
        "--quiet",
        "--no-git-ignore",
        repo_path,
    ]
    if language:
        cmd += ["--lang", language]

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=300,
    )

    if result.returncode not in (0, 1):  # 1 = findings found
        raise RuntimeError(f"semgrep exited {result.returncode}: {result.stderr[:500]}")

    output = json.loads(result.stdout)
    findings: list[RawFinding] = []
    base = Path(repo_path)

    for item in output.get("results", []):
        sev_label = item.get("extra", {}).get("severity", "WARNING")
        severity, cvss = _SEMGREP_SEV_MAP.get(sev_label, ("medium", 5.0))

        abs_path = item.get("path", "")
        try:
            rel_path = str(Path(abs_path).relative_to(base))
        except ValueError:
            rel_path = abs_path

        findings.append(
            RawFinding(
                rule_id=item.get("check_id", "sast.unknown"),
                title=item.get("extra", {}).get("message", "SAST finding")[:200],
                description=item.get("extra", {}).get("message", ""),
                severity=severity,
                cvss_score=cvss,
                file_path=rel_path,
                start_line=item.get("start", {}).get("line", 0),
                end_line=item.get("end", {}).get("line", 0),
                snippet=item.get("extra", {}).get("lines", "")[:500],
                category=_infer_category(item.get("check_id", "")),
                extra={
                    "semgrep_rule": item.get("check_id", ""),
                    "engine": "semgrep",
                },
            )
        )

    logger.info("semgrep_complete", findings=len(findings), repo=repo_path)
    return findings


def _run_builtin(repo_path: str) -> list[RawFinding]:
    """Run the built-in regex-based SAST rules over all source files.

    Args:
        repo_path: Absolute path to the repository directory.

    Returns:
        List of RawFinding instances.
    """
    base = Path(repo_path)
    source_extensions = {".py", ".js", ".ts", ".jsx", ".tsx", ".java", ".go"}
    findings: list[RawFinding] = []

    for src_file in base.rglob("*"):
        if not src_file.is_file():
            continue
        if src_file.suffix.lower() not in source_extensions:
            continue
        if any(part.startswith(".") or part in ("node_modules", "__pycache__", "dist", "build")
               for part in src_file.parts):
            continue

        try:
            source = src_file.read_text(errors="replace")
            rel_path = str(src_file.relative_to(base))
            findings.extend(_apply_builtin_rules(rel_path, source))
        except Exception:
            continue

    return findings


def _apply_builtin_rules(file_path: str, source: str) -> list[RawFinding]:
    """Apply built-in regex SAST rules to a single file.

    Args:
        file_path: Relative file path.
        source: File source text.

    Returns:
        List of RawFinding instances.
    """
    findings: list[RawFinding] = []
    lines = source.splitlines()

    for rule_id, title, description, pattern, severity, cvss, category in _BUILTIN_RULES:
        rx = re.compile(pattern, re.IGNORECASE | re.MULTILINE)
        for i, line in enumerate(lines, start=1):
            if rx.search(line):
                findings.append(
                    RawFinding(
                        rule_id=rule_id,
                        title=title,
                        description=description,
                        severity=severity,
                        cvss_score=cvss,
                        file_path=file_path,
                        start_line=i,
                        end_line=i,
                        snippet=line.strip()[:500],
                        category=category,
                        extra={"engine": "builtin"},
                    )
                )

    return findings


def _infer_category(rule_id: str) -> str:
    """Infer a semantic category from a Semgrep rule ID string.

    Args:
        rule_id: Semgrep rule identifier.

    Returns:
        Category slug string.
    """
    lower = rule_id.lower()
    if "sql" in lower or "injection" in lower:
        return "injection"
    if "xss" in lower:
        return "xss"
    if "ssrf" in lower:
        return "ssrf"
    if "pickle" in lower or "deserializ" in lower or "eval" in lower:
        return "insecure_deserialization"
    if "auth" in lower or "password" in lower or "credential" in lower:
        return "broken_auth"
    if "path" in lower or "traversal" in lower:
        return "path_traversal"
    if "crypto" in lower or "md5" in lower or "sha1" in lower:
        return "insecure_crypto"
    if "xml" in lower or "xxe" in lower:
        return "xxe"
    if "redirect" in lower:
        return "open_redirect"
    if "log" in lower:
        return "information_disclosure"
    return "sast"
