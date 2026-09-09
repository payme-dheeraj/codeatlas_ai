"""PR/MR Analysis service.

Accepts a diff (unified format) and a description, then uses an LLM to:
  - Summarise the changes
  - Identify potential issues (bugs, security, style)
  - Generate inline review comments per file
  - Produce an overall review verdict (approve | request_changes | comment)
"""

from __future__ import annotations

from typing import Any

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

_SYSTEM = (
    "You are an expert code reviewer with deep knowledge of security, performance, "
    "maintainability, and best practices. Perform a thorough pull request review. "
    "Be constructive, specific, and cite exact line numbers when possible."
)

_PROMPT = """\
Review the following pull request.

## Repository: {repo_name}
## PR Title: {pr_title}
## PR Description:
{pr_description}

## Diff:
```diff
{diff}
```

## Review Task

Provide a structured review with EXACTLY these sections:

### Summary
(2-3 sentence summary of what this PR does)

### Verdict
(One of: APPROVE | REQUEST_CHANGES | COMMENT — with a brief reason)

### Issues Found
(Numbered list of specific issues. For each:
  - Severity: critical | high | medium | low
  - File: filename
  - Line: approximate line number
  - Issue: description
  - Suggestion: how to fix)

### Positive Aspects
(What the PR does well)

### Security Considerations
(Any security implications — XSS, injection, auth bypass, secret exposure, etc.)

Respond with ONLY the structured review — no preamble.
"""


async def analyze_pr(
    diff: str,
    *,
    repo_name: str = "Unknown Repository",
    pr_title: str = "Untitled PR",
    pr_description: str = "",
    llm_provider: str | None = None,
    llm_model: str | None = None,
) -> dict[str, Any]:
    """Run AI code review on a PR diff.

    Args:
        diff: Unified diff string (from ``git diff`` or GitHub API).
        repo_name: Repository display name.
        pr_title: Pull request title.
        pr_description: Pull request body/description.
        llm_provider: Override LLM provider.
        llm_model: Override LLM model.

    Returns:
        Dict with raw_review, summary, verdict, issues, and metadata.
    """
    from app.docs_gen._llm import call_llm

    # Truncate very large diffs to avoid exceeding context window
    max_diff_chars = 12_000
    truncated = len(diff) > max_diff_chars
    diff_text = diff[:max_diff_chars] + ("\n... [diff truncated]" if truncated else "")

    prompt = _PROMPT.format(
        repo_name=repo_name,
        pr_title=pr_title,
        pr_description=pr_description or "(no description provided)",
        diff=diff_text,
    )

    provider = llm_provider or getattr(settings, "llm_provider", "ollama")
    model = llm_model or getattr(settings, "llm_model", "llama3.2")

    logger.info("pr_analysis_started", repo=repo_name, pr_title=pr_title)

    try:
        raw_review = call_llm(provider, model, _SYSTEM, prompt, max_tokens=3000, temperature=0.1)
    except Exception as exc:
        logger.error("pr_analysis_llm_failed", error=str(exc))
        raw_review = f"*AI review failed: {exc}*"

    verdict = _extract_verdict(raw_review)
    issues = _extract_issues(raw_review)

    return {
        "repo_name": repo_name,
        "pr_title": pr_title,
        "verdict": verdict,
        "issues_count": len(issues),
        "issues": issues,
        "raw_review": raw_review,
        "diff_truncated": truncated,
        "llm_provider": provider,
        "llm_model": model,
    }


def _extract_verdict(review: str) -> str:
    """Extract the verdict keyword from the AI review text.

    Args:
        review: Full review Markdown string.

    Returns:
        One of: APPROVE | REQUEST_CHANGES | COMMENT | UNKNOWN.
    """
    upper = review.upper()
    for verdict in ("REQUEST_CHANGES", "APPROVE", "COMMENT"):
        if verdict in upper:
            return verdict
    return "UNKNOWN"


def _extract_issues(review: str) -> list[dict[str, str]]:
    """Parse numbered issues from the review text.

    Args:
        review: Full review Markdown string.

    Returns:
        List of issue dicts with severity, file, line, issue, suggestion.
    """
    import re
    issues = []
    issue_re = re.compile(
        r"-\s+Severity:\s*(.+?)\n\s*-\s+File:\s*(.+?)\n\s*-\s+Line:\s*(.+?)\n"
        r"\s*-\s+Issue:\s*(.+?)\n\s*-\s+Suggestion:\s*(.+?)(?=\n\d+\.|$)",
        re.DOTALL,
    )
    for m in issue_re.finditer(review):
        issues.append({
            "severity": m.group(1).strip(),
            "file": m.group(2).strip(),
            "line": m.group(3).strip(),
            "issue": m.group(4).strip(),
            "suggestion": m.group(5).strip(),
        })
    return issues
