"""AI remediation generator — produces fix suggestions for security findings.

Uses the configured LLM (OpenAI / Anthropic / Ollama) with the PRD's
structured prompt template to generate:
1. A vulnerability explanation.
2. Fixed code.
3. Additional recommendations.
"""

from __future__ import annotations

import json
from typing import Any

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

# ── Prompt template (from PRD) ────────────────────────────────────────────────

_SYSTEM = (
    "You are a security expert. Provide concise, actionable remediation advice "
    "for the described vulnerability. Respond with valid JSON only."
)

_USER_TEMPLATE = """\
A security vulnerability was found in a software repository.

FINDING:
- Type: {category}
- Severity: {severity}
- File: {file_path}
- Lines: {start_line}-{end_line}
- Rule: {rule_id}
- Description: {description}

VULNERABLE CODE:
```{language}
{snippet}
```

Provide a JSON object with exactly these keys:
{{
  "vulnerability": "<2-3 sentence explanation of why this is a vulnerability>",
  "fixed_code": "<corrected code snippet>",
  "recommendations": ["<rec 1>", "<rec 2>", "<rec 3>"]
}}

RESPONSE (JSON only, no markdown fences):"""

_EMPTY_REMEDIATION: dict[str, Any] = {
    "vulnerability": "See description.",
    "fixed_code": "",
    "recommendations": [],
}


def generate_remediation(finding: dict[str, Any]) -> dict[str, Any]:
    """Generate AI remediation for a single finding dict.

    Args:
        finding: Normalized finding dict with keys:
            category, severity, file_path, start_line, end_line,
            rule_id, description, snippet, language.

    Returns:
        Dict with keys: vulnerability, fixed_code, recommendations.
        Returns a safe empty dict on any LLM failure.
    """
    snippet = (finding.get("snippet") or "").strip()
    if not snippet:
        return _EMPTY_REMEDIATION

    user_prompt = _USER_TEMPLATE.format(
        category=finding.get("category", "security"),
        severity=finding.get("severity", "medium"),
        file_path=finding.get("file_path", ""),
        start_line=finding.get("start_line", 0),
        end_line=finding.get("end_line", 0),
        rule_id=finding.get("rule_id", ""),
        description=finding.get("description", ""),
        language=finding.get("language") or "text",
        snippet=snippet[:1000],
    )

    provider = getattr(settings, "llm_provider", "ollama").lower()
    model = getattr(settings, "llm_model", "llama3.2")

    try:
        raw = _call_llm(provider, model, user_prompt)
        return _parse_response(raw)
    except Exception as exc:
        logger.warning(
            "remediation_failed",
            rule_id=finding.get("rule_id"),
            error=str(exc),
        )
        return _EMPTY_REMEDIATION


def generate_remediations_batch(
    findings: list[dict[str, Any]],
    *,
    max_findings: int = 20,
) -> dict[str, dict[str, Any]]:
    """Generate remediation for a batch of findings.

    Only generates for findings with a non-empty snippet and
    severity >= medium to keep LLM costs manageable.

    Args:
        findings: List of normalized finding dicts.
        max_findings: Maximum number of findings to process.

    Returns:
        Dict mapping finding fingerprint → remediation dict.
    """
    priority_order = ["critical", "high", "medium"]
    eligible = [
        f for f in findings
        if f.get("snippet") and f.get("severity", "low") in priority_order
    ][:max_findings]

    results: dict[str, dict[str, Any]] = {}
    for f in eligible:
        fp = f.get("fingerprint", "")
        results[fp] = generate_remediation(f)

    logger.info("remediation_batch_complete", count=len(results))
    return results


# ── LLM dispatch ──────────────────────────────────────────────────────────────


def _call_llm(provider: str, model: str, user_prompt: str) -> str:
    """Call the configured LLM and return the raw response text.

    Args:
        provider: Provider slug (openai | anthropic | ollama).
        model: Model name string.
        user_prompt: Fully rendered user prompt.

    Returns:
        Raw LLM response string.
    """
    if provider == "openai":
        import openai
        client = openai.OpenAI(api_key=settings.openai_api_key)
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": _SYSTEM},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.0,
            max_tokens=1024,
        )
        return response.choices[0].message.content or ""

    elif provider == "anthropic":
        import anthropic
        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        response = client.messages.create(
            model=model,
            system=_SYSTEM,
            messages=[{"role": "user", "content": user_prompt}],
            max_tokens=1024,
            temperature=0.0,
        )
        return response.content[0].text if response.content else ""

    else:  # ollama / local
        import httpx
        base = getattr(settings, "ollama_base_url", "http://localhost:11434")
        resp = httpx.post(
            f"{base}/api/chat",
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": _SYSTEM},
                    {"role": "user", "content": user_prompt},
                ],
                "stream": False,
                "options": {"temperature": 0.0},
            },
            timeout=60.0,
        )
        resp.raise_for_status()
        return resp.json().get("message", {}).get("content", "")


def _parse_response(raw: str) -> dict[str, Any]:
    """Parse the LLM JSON response into a structured dict.

    Strips markdown code fences if present and validates the structure.

    Args:
        raw: Raw LLM response string.

    Returns:
        Validated remediation dict.
    """
    text = raw.strip()
    # Strip markdown JSON fences if present
    if text.startswith("```"):
        lines = text.splitlines()
        text = "\n".join(
            line for line in lines
            if not line.startswith("```")
        ).strip()

    data = json.loads(text)
    return {
        "vulnerability": str(data.get("vulnerability", "")),
        "fixed_code": str(data.get("fixed_code", "")),
        "recommendations": list(data.get("recommendations", [])),
    }
