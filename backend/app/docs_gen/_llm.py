"""Internal LLM call helper shared across all docs_gen modules."""

from __future__ import annotations

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


def call_llm(
    provider: str,
    model: str,
    system: str,
    user_prompt: str,
    *,
    max_tokens: int = 4096,
    temperature: float = 0.2,
) -> str:
    """Dispatch a chat completion to the specified LLM provider.

    Args:
        provider: Provider slug (openai | anthropic | ollama).
        model: Model identifier string.
        system: System prompt string.
        user_prompt: User message string.
        max_tokens: Maximum completion tokens.
        temperature: Sampling temperature.

    Returns:
        Generated text content string.
    """
    provider = provider.lower()

    if provider == "openai":
        return _openai(model, system, user_prompt, max_tokens, temperature)
    elif provider == "anthropic":
        return _anthropic(model, system, user_prompt, max_tokens, temperature)
    else:
        return _ollama(model, system, user_prompt, max_tokens, temperature)


def _openai(model, system, user_prompt, max_tokens, temperature) -> str:
    import openai
    client = openai.OpenAI(api_key=settings.openai_api_key)
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user_prompt},
        ],
        temperature=temperature,
        max_tokens=max_tokens,
    )
    return response.choices[0].message.content or ""


def _anthropic(model, system, user_prompt, max_tokens, temperature) -> str:
    import anthropic
    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    response = client.messages.create(
        model=model,
        system=system,
        messages=[{"role": "user", "content": user_prompt}],
        max_tokens=max_tokens,
        temperature=temperature,
    )
    return response.content[0].text if response.content else ""


def _ollama(model, system, user_prompt, max_tokens, temperature) -> str:
    import httpx
    base = getattr(settings, "ollama_base_url", "http://localhost:11434")
    resp = httpx.post(
        f"{base}/api/chat",
        json={
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user_prompt},
            ],
            "stream": False,
            "options": {"temperature": temperature, "num_predict": max_tokens},
        },
        timeout=180.0,
    )
    resp.raise_for_status()
    return resp.json().get("message", {}).get("content", "")
