"""DSPy multi-provider configuration with automatic fallback.

Provider priority:
  1. Gemini Flash  — 1,500 req/day, 15 RPM  (primary)
  2. Groq          — 1,000 req/day, 30 RPM  (fallback)
  3. OpenRouter    —    50 req/day, 20 RPM  (emergency fallback)

Usage:
    from lib.dspy_config import configure_dspy
    configure_dspy()   # call once at startup
"""

from __future__ import annotations

import json
import os
import time
from datetime import date
from pathlib import Path
from typing import Any

import dspy


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_COUNTS_FILE = Path.home() / ".paper2md" / "provider_counts.json"

PROVIDER_CONFIG: dict[str, dict[str, Any]] = {
    "gemini": {
        "model":    "gemini/gemini-2.0-flash",
        "env_key":  "GEMINI_API_KEY",
        "daily_limit": 1_500,
        "rpm":      15,
        "sleep_s":  4.0,
    },
    "groq": {
        "model":    "groq/llama-3.3-70b-versatile",
        "env_key":  "GROQ_API_KEY",
        "daily_limit": 1_000,
        "rpm":      30,
        "sleep_s":  2.0,
    },
    "openrouter": {
        "model":    "openrouter/openrouter/free",
        "env_key":  "OPENROUTER_API_KEY",
        "daily_limit": 200,
        "rpm":      10,
        "sleep_s":  6.0,
    },
    # Legacy: keep working if user only has OPENAI_API_KEY
    "openai": {
        "model":    "openai/gpt-4o-mini",
        "env_key":  "OPENAI_API_KEY",
        "daily_limit": None,   # paid — no limit tracked
        "rpm":      500,
        "sleep_s":  0.1,
    },
}


# ---------------------------------------------------------------------------
# Daily usage tracking
# ---------------------------------------------------------------------------

def _load_counts() -> dict[str, Any]:
    if not _COUNTS_FILE.exists():
        return {}
    try:
        return json.loads(_COUNTS_FILE.read_text())
    except (json.JSONDecodeError, OSError):
        return {}


def _save_counts(counts: dict[str, Any]) -> None:
    _COUNTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    _COUNTS_FILE.write_text(json.dumps(counts, indent=2))


def increment_provider_count(provider: str) -> int:
    """Increment daily call count for provider. Returns new count."""
    today = str(date.today())
    counts = _load_counts()
    key = f"{provider}:{today}"
    counts[key] = counts.get(key, 0) + 1
    _save_counts(counts)
    return counts[key]


def get_provider_count(provider: str) -> int:
    """Return today's call count for provider."""
    today = str(date.today())
    counts = _load_counts()
    return counts.get(f"{provider}:{today}", 0)


def is_provider_exhausted(provider: str) -> bool:
    """Return True if provider has hit its daily free limit."""
    cfg = PROVIDER_CONFIG.get(provider, {})
    limit = cfg.get("daily_limit")
    if limit is None:
        return False
    return get_provider_count(provider) >= limit


# ---------------------------------------------------------------------------
# DSPy LM factory
# ---------------------------------------------------------------------------

def _make_lm(provider: str) -> dspy.LM | None:
    """Build a dspy.LM for provider if its API key is set."""
    cfg = PROVIDER_CONFIG[provider]
    api_key = os.environ.get(cfg["env_key"], "").strip()
    if not api_key:
        return None

    kwargs: dict[str, Any] = {
        "api_key":    api_key,
        "max_tokens": 4000,
        "temperature": 0.2,
    }

    # OpenRouter requires an extra header
    if provider == "openrouter":
        kwargs["extra_headers"] = {
            "HTTP-Referer": "https://github.com/paper2md",
            "X-Title":      "paper2md",
        }

    # OpenAI-compatible base URLs are handled by LiteLLM inside DSPy
    # via the provider-prefixed model name (e.g. "groq/llama-3.3-70b-versatile")
    if provider == "openai":
        base_url = os.environ.get("OPENAI_BASE_URL", "").strip()
        if base_url:
            kwargs["base_url"] = base_url
        model = os.environ.get("OPENAI_MODEL", cfg["model"])
        # Strip provider prefix if user already configured OPENAI_MODEL without it
        if not model.startswith("openai/"):
            model = f"openai/{model}" if "/" not in model else model
        return dspy.LM(model, **kwargs)

    return dspy.LM(cfg["model"], **kwargs)


def configure_dspy() -> str:
    """
    Configure DSPy with primary provider + fallback chain.

    Provider selection order:
      1. PAPER2MD_LLM_PROVIDER env var (explicit)
      2. First provider with API key set and not exhausted

    Returns: name of the primary provider configured.
    Raises: RuntimeError if no provider is available.
    """
    explicit = os.environ.get("PAPER2MD_LLM_PROVIDER", "").strip().lower()
    order = (
        [explicit] + [p for p in ["gemini", "groq", "openrouter", "openai"] if p != explicit]
        if explicit in PROVIDER_CONFIG
        else ["gemini", "groq", "openrouter", "openai"]
    )

    primary_lm: dspy.LM | None = None
    primary_name: str = ""
    fallback_lms: list[dspy.LM] = []

    for provider in order:
        lm = _make_lm(provider)
        if lm is None:
            continue
        if primary_lm is None:
            primary_lm = lm
            primary_name = provider
        else:
            fallback_lms.append(lm)

    if primary_lm is None:
        raise RuntimeError(
            "No LLM provider API key found. Set at least one of: "
            "GEMINI_API_KEY, GROQ_API_KEY, OPENROUTER_API_KEY, OPENAI_API_KEY"
        )

    if fallback_lms:
        primary_lm = dspy.LM(
            PROVIDER_CONFIG[primary_name]["model"],
            api_key=os.environ.get(PROVIDER_CONFIG[primary_name]["env_key"], ""),
            max_tokens=4000,
            temperature=0.2,
            fallback=fallback_lms,
        )

    dspy.configure(lm=primary_lm)
    return primary_name


def get_sleep_for_provider(provider: str) -> float:
    """Return the inter-call sleep duration in seconds for the provider."""
    return PROVIDER_CONFIG.get(provider, {}).get("sleep_s", 2.0)


def rate_limit_sleep(provider: str) -> None:
    """Sleep the appropriate amount to respect provider RPM limits."""
    sleep_s = get_sleep_for_provider(provider)
    if sleep_s > 0:
        time.sleep(sleep_s)
