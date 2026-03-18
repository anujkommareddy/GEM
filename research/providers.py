"""Model provider abstraction.

Supports OpenAI and Anthropic with a unified interface for script analysis.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Optional


@dataclass
class CompletionResult:
    """Unified response from any provider."""

    text: str
    input_tokens: int
    output_tokens: int
    model: str
    provider: str


# ---------------------------------------------------------------------------
# Pricing (per million tokens)
# ---------------------------------------------------------------------------

PRICING = {
    # OpenAI
    "gpt-4o-mini": {"input": 0.15, "output": 0.60},
    "gpt-4o": {"input": 2.50, "output": 10.00},
    "gpt-4.1-nano": {"input": 0.10, "output": 0.40},
    # Anthropic
    "claude-haiku-4-5-20251001": {"input": 1.00, "output": 5.00},
    "claude-sonnet-4-20250514": {"input": 3.00, "output": 15.00},
}

# Default cheapest models per provider
DEFAULT_MODELS = {
    "openai": "gpt-4o-mini",
    "anthropic": "claude-haiku-4-5-20251001",
}


def get_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    """Calculate cost for a completion."""
    pricing = PRICING.get(model, {"input": 1.0, "output": 5.0})
    return (input_tokens / 1_000_000) * pricing["input"] + \
           (output_tokens / 1_000_000) * pricing["output"]


# ---------------------------------------------------------------------------
# Provider implementations
# ---------------------------------------------------------------------------

def complete_openai(
    system_prompt: str,
    user_prompt: str,
    model: str = "gpt-4o-mini",
    api_key: Optional[str] = None,
    max_tokens: int = 4096,
) -> CompletionResult:
    """Send a completion request to OpenAI."""
    try:
        from openai import OpenAI
    except ImportError:
        raise ImportError("Install openai: pip install openai")

    key = api_key or os.environ.get("OPENAI_API_KEY")
    if not key:
        raise ValueError("OPENAI_API_KEY not set")

    client = OpenAI(api_key=key)

    for attempt in range(5):
        try:
            response = client.chat.completions.create(
                model=model,
                max_tokens=max_tokens,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
            )
            break
        except Exception as e:
            if "429" in str(e) or "rate_limit" in str(e):
                wait = 2 ** attempt + 1
                time.sleep(wait)
                if attempt == 4:
                    raise
            else:
                raise

    text = response.choices[0].message.content or ""
    usage = response.usage
    return CompletionResult(
        text=text.strip(),
        input_tokens=usage.prompt_tokens if usage else 0,
        output_tokens=usage.completion_tokens if usage else 0,
        model=model,
        provider="openai",
    )


def complete_anthropic(
    system_prompt: str,
    user_prompt: str,
    model: str = "claude-haiku-4-5-20251001",
    api_key: Optional[str] = None,
    max_tokens: int = 4096,
) -> CompletionResult:
    """Send a completion request to Anthropic."""
    try:
        import anthropic
    except ImportError:
        raise ImportError("Install anthropic: pip install anthropic")

    key = api_key or os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        raise ValueError("ANTHROPIC_API_KEY not set")

    client = anthropic.Anthropic(api_key=key)

    for attempt in range(5):
        try:
            response = client.messages.create(
                model=model,
                max_tokens=max_tokens,
                system=system_prompt,
                messages=[{"role": "user", "content": user_prompt}],
            )
            break
        except Exception as e:
            if "429" in str(e) or "rate_limit" in str(e):
                wait = 2 ** attempt + 1
                time.sleep(wait)
                if attempt == 4:
                    raise
            else:
                raise

    text = response.content[0].text
    return CompletionResult(
        text=text.strip(),
        input_tokens=response.usage.input_tokens if response.usage else 0,
        output_tokens=response.usage.output_tokens if response.usage else 0,
        model=model,
        provider="anthropic",
    )


# ---------------------------------------------------------------------------
# Unified dispatch
# ---------------------------------------------------------------------------

PROVIDERS = {
    "openai": complete_openai,
    "anthropic": complete_anthropic,
}


def complete(
    system_prompt: str,
    user_prompt: str,
    provider: str = "openai",
    model: Optional[str] = None,
    api_key: Optional[str] = None,
    max_tokens: int = 4096,
) -> CompletionResult:
    """Unified completion interface. Dispatches to the right provider."""
    if provider not in PROVIDERS:
        raise ValueError(f"Unknown provider: {provider}. Supported: {list(PROVIDERS.keys())}")

    model = model or DEFAULT_MODELS[provider]

    return PROVIDERS[provider](
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        model=model,
        api_key=api_key,
        max_tokens=max_tokens,
    )
