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

# OpenRouter model is overridable because a paid account should not be forced
# through the free queue (~70s/call). The free slug stays the default so nothing
# changes for free-tier keys; the daily_limit / rpm / sleep_s throttles above
# exist only to stay inside the free tier and are lifted for a paid slug.
# Google retires model ids without warning — gemini-2.0-flash 404'd with
# "no longer available". Overridable so a retirement is a one-line env fix
# rather than a code change; "gemini/gemini-flash-latest" tracks the newest.
_GEMINI_MODEL = os.environ.get(
    "PAPER2MD_GEMINI_MODEL", "gemini/gemini-3.8-flash"
).strip() or "gemini/gemini-3.8-flash"

_OPENROUTER_FREE_MODEL = "openrouter/openrouter/free"
_OPENROUTER_MODEL = os.environ.get(
    "PAPER2MD_OPENROUTER_MODEL", _OPENROUTER_FREE_MODEL
).strip() or _OPENROUTER_FREE_MODEL
_OPENROUTER_IS_PAID = _OPENROUTER_MODEL != _OPENROUTER_FREE_MODEL


PROVIDER_CONFIG: dict[str, dict[str, Any]] = {
    "gemini": {
        "model":    _GEMINI_MODEL,
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
        # Free routing by default. Set PAPER2MD_OPENROUTER_MODEL to a paid slug
        # (e.g. "openrouter/google/gemini-2.0-flash-001") to bypass the free
        # queue; the throttles below are lifted when that is set.
        "model":    _OPENROUTER_MODEL,
        "env_key":  "OPENROUTER_API_KEY",
        "daily_limit": None if _OPENROUTER_IS_PAID else 200,
        "rpm":      500 if _OPENROUTER_IS_PAID else 10,
        "sleep_s":  0.1 if _OPENROUTER_IS_PAID else 6.0,
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
    if _load_counts().get(f"{provider}:{date.today()}:exhausted"):
        return True
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
        "max_tokens": 8000,
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


class ProvidersExhaustedError(RuntimeError):
    """Every provider with an API key has used up today's quota."""


# Markers of a per-day cap, as opposed to a per-minute one that backoff clears:
# Gemini "...PerDayPerProject...", OpenRouter "free-models-per-day",
# Groq "requests per day (RPD)".
_DAILY_QUOTA_MARKERS = ("perday", "per-day", "per day", "per_day")


def is_daily_quota_error(error: Exception) -> bool:
    """Return True if `error` is a 429 for a daily quota, not a per-minute one."""
    msg = str(error).lower()
    return any(marker in msg for marker in _DAILY_QUOTA_MARKERS)


def mark_provider_exhausted(provider: str) -> None:
    """Record that `provider` refused a call for today's quota."""
    counts = _load_counts()
    counts[f"{provider}:{date.today()}:exhausted"] = True
    _save_counts(counts)


def _provider_order() -> list[str]:
    explicit = os.environ.get("PAPER2MD_LLM_PROVIDER", "").strip().lower()
    default = ["gemini", "groq", "openrouter", "openai"]
    if explicit not in PROVIDER_CONFIG:
        return default
    return [explicit] + [p for p in default if p != explicit]


def configure_dspy() -> str:
    """
    Configure DSPy with the first usable provider.

    Provider selection order:
      1. PAPER2MD_LLM_PROVIDER env var (explicit)
      2. First provider with API key set and not exhausted

    Failover is done by failover_provider() when a call hits a daily quota —
    dspy.LM has no fallback chain of its own.

    Returns: name of the provider configured.
    Raises: RuntimeError if no provider has a key;
            ProvidersExhaustedError if every keyed provider is exhausted today.
    """
    keyed = [p for p in _provider_order()
             if os.environ.get(PROVIDER_CONFIG[p]["env_key"], "").strip()]
    if not keyed:
        raise RuntimeError(
            "No LLM provider API key found. Set at least one of: "
            "GEMINI_API_KEY, GROQ_API_KEY, OPENROUTER_API_KEY, OPENAI_API_KEY"
        )

    usable = [p for p in keyed if not is_provider_exhausted(p)]
    if not usable:
        raise ProvidersExhaustedError(
            f"Daily quota exhausted for every configured provider: {', '.join(keyed)}"
        )

    provider = usable[0]
    dspy.configure(lm=_make_lm(provider))
    return provider


def failover_provider(provider: str) -> str:
    """Mark `provider` exhausted for today and switch DSPy to the next one.

    Returns the new provider's name; raises ProvidersExhaustedError if none is left.
    """
    mark_provider_exhausted(provider)
    return configure_dspy()


def get_sleep_for_provider(provider: str) -> float:
    """Return the inter-call sleep duration in seconds for the provider."""
    return PROVIDER_CONFIG.get(provider, {}).get("sleep_s", 2.0)


def rate_limit_sleep(provider: str) -> None:
    """Sleep the appropriate amount to respect provider RPM limits."""
    sleep_s = get_sleep_for_provider(provider)
    if sleep_s > 0:
        time.sleep(sleep_s)
