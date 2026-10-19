"""DSPy multi-provider configuration with automatic fallback.

Provider priority:
  1. Gemini Flash  — 1,500 req/day, 15 RPM  (primary)
  2. Groq          — 1,000 req/day, 30 RPM  (fallback)
  3. Ollama Cloud  — 5h session + weekly GPU-time limits
  4. NVIDIA NIM    — no daily cap, ~40 RPM
  5. OpenRouter    — 50 free req/day, or 1,000 once $10+ credits bought

Usage:
    from lib.dspy_config import configure_dspy
    configure_dspy()   # call once at startup
"""

from __future__ import annotations

import json
import os
import re
import threading
import time
from datetime import datetime, timezone
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

# Groq retired llama-3.3-70b-versatile ("model_not_found"); same override as Gemini.
_GROQ_DEFAULT_MODEL = "groq/openai/gpt-oss-120b"
_GROQ_MODEL = os.environ.get(
    "PAPER2MD_GROQ_MODEL", _GROQ_DEFAULT_MODEL
).strip() or _GROQ_DEFAULT_MODEL

# Ollama Cloud free tier: no published daily cap — usage is GPU-time metered
# with 5-hour session and weekly windows, so daily_limit is None and the
# "usage limit" 429 drives failover instead.
_OLLAMA_DEFAULT_MODEL = "ollama_chat/gpt-oss:120b"
_OLLAMA_MODEL = os.environ.get(
    "PAPER2MD_OLLAMA_MODEL", _OLLAMA_DEFAULT_MODEL
).strip() or _OLLAMA_DEFAULT_MODEL
_OLLAMA_API_BASE = "https://ollama.com"

# NVIDIA NIM (build.nvidia.com) free tier: no daily cap, only ~40 RPM per key,
# so daily_limit is None — it keeps the runner going once the capped providers
# are spent. LiteLLM supplies the integrate.api.nvidia.com base URL.
_NVIDIA_DEFAULT_MODEL = "nvidia_nim/nvidia/nemotron-3-super-120b-a12b"
_NVIDIA_MODEL = os.environ.get(
    "PAPER2MD_NVIDIA_MODEL", _NVIDIA_DEFAULT_MODEL
).strip() or _NVIDIA_DEFAULT_MODEL

_OPENROUTER_FREE_MODEL = "openrouter/openrouter/free"
_OPENROUTER_MODEL = os.environ.get(
    "PAPER2MD_OPENROUTER_MODEL", _OPENROUTER_FREE_MODEL
).strip() or _OPENROUTER_FREE_MODEL
# A pinned ":free" model (e.g. "openrouter/google/gemma-4-31b-it:free") draws
# on the same free-model allowance as the router, so it keeps the throttles.
_OPENROUTER_IS_PAID = (
    _OPENROUTER_MODEL != _OPENROUTER_FREE_MODEL
    and not _OPENROUTER_MODEL.endswith(":free")
)


def _positive_int_env(name: str, default: int) -> int:
    """Read a positive integer from the environment, or fall back to default."""
    raw = os.environ.get(name, "").strip()
    return int(raw) if raw.isdigit() and int(raw) > 0 else default


# Free-model requests per day: 50 for keys that never bought credits, 1,000
# once the account has bought $10+. 200 is a safe middle; raise it with
# PAPER2MD_OPENROUTER_DAILY_LIMIT when the key has the larger allowance.
_OPENROUTER_FREE_DAILY_LIMIT = _positive_int_env("PAPER2MD_OPENROUTER_DAILY_LIMIT", 200)


PROVIDER_CONFIG: dict[str, dict[str, Any]] = {
    "gemini": {
        "model":    _GEMINI_MODEL,
        "env_key":  "GEMINI_API_KEY",
        "daily_limit": 1_500,
        "rpm":      15,
        "sleep_s":  4.0,
    },
    "groq": {
        "model":    _GROQ_MODEL,
        "env_key":  "GROQ_API_KEY",
        "daily_limit": 1_000,
        "rpm":      30,
        "sleep_s":  2.0,
    },
    "ollama": {
        "model":    _OLLAMA_MODEL,
        "env_key":  "OLLAMA_API_KEY",
        "daily_limit": None,
        "rpm":      30,
        "sleep_s":  1.0,
    },
    "nvidia": {
        "model":    _NVIDIA_MODEL,
        "env_key":  "NVIDIA_NIM_API_KEY",
        "daily_limit": None,
        "rpm":      40,
        "sleep_s":  1.5,
    },
    "openrouter": {
        # Free routing by default. Set PAPER2MD_OPENROUTER_MODEL to a paid slug
        # (e.g. "openrouter/google/gemini-2.0-flash-001") to bypass the free
        # queue; the throttles below are lifted when that is set.
        "model":    _OPENROUTER_MODEL,
        "env_key":  "OPENROUTER_API_KEY",
        "daily_limit": None if _OPENROUTER_IS_PAID else _OPENROUTER_FREE_DAILY_LIMIT,
        "rpm":      500 if _OPENROUTER_IS_PAID else 10,
        "sleep_s":  0.1 if _OPENROUTER_IS_PAID else 6.0,
        # OpenRouter resets free-model allowances at 00:00 UTC.
        "utc_day":  True,
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

# explain_math_only.py --workers runs calls on several threads. They share the
# usage file (read-modify-write) and the active LM, so both are guarded here.
_state_lock = threading.RLock()
_active_lm: dspy.LM | None = None


def _load_counts() -> dict[str, Any]:
    if not _COUNTS_FILE.exists():
        return {}
    try:
        return json.loads(_COUNTS_FILE.read_text())
    except (json.JSONDecodeError, OSError):
        return {}


def _save_counts(counts: dict[str, Any]) -> None:
    # Write-then-rename: readers outside _state_lock (is_provider_exhausted)
    # would otherwise see a half-written file, parse it as {} and treat a
    # spent provider as live.
    _COUNTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = _COUNTS_FILE.with_name(f"{_COUNTS_FILE.name}.{threading.get_ident()}.tmp")
    tmp.write_text(json.dumps(counts, indent=2))
    os.replace(tmp, _COUNTS_FILE)


def quota_day(provider: str, now: float | None = None) -> str:
    """The date a provider's daily count is filed under: UTC or local, per provider."""
    ts = time.time() if now is None else now
    utc = PROVIDER_CONFIG.get(provider, {}).get("utc_day", False)
    return str(datetime.fromtimestamp(ts, timezone.utc if utc else None).date())


def increment_provider_count(provider: str) -> int:
    """Increment daily call count for provider. Returns new count."""
    with _state_lock:
        counts = _load_counts()
        key = f"{provider}:{quota_day(provider)}"
        counts[key] = counts.get(key, 0) + 1
        _save_counts(counts)
        return counts[key]


def get_provider_count(provider: str) -> int:
    """Return today's call count for provider."""
    counts = _load_counts()
    return counts.get(f"{provider}:{quota_day(provider)}", 0)


def is_provider_exhausted(provider: str) -> bool:
    """Return True if provider has hit its daily free limit."""
    cfg = PROVIDER_CONFIG.get(provider, {})
    if _load_counts().get(f"{provider}:exhausted_until", 0) > time.time():
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

    if provider == "ollama":
        kwargs["api_base"] = _OLLAMA_API_BASE

    # OpenAI-compatible base URLs are handled by LiteLLM inside DSPy
    # via the provider-prefixed model name (e.g. "groq/openai/gpt-oss-120b")
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


class ProviderQuotaError(ProvidersExhaustedError):
    """One provider used up its quota; the other providers may still have some."""

    def __init__(self, provider: str) -> None:
        super().__init__(f"{provider} quota exhausted")
        self.provider = provider


# Paid providers never take a share of the blocks in one-per-provider mode.
_PAID_PROVIDERS = frozenset({"openai"})


def live_providers() -> list[str]:
    """Free providers with a key and quota left, in priority order."""
    return [p for p in _keyed_providers()
            if p not in _PAID_PROVIDERS and not is_provider_exhausted(p)]


_lm_by_provider: dict[str, dspy.LM] = {}


def lm_for(provider: str) -> dspy.LM | None:
    """A cached LM for `provider`, independent of the shared active one."""
    with _state_lock:
        if provider not in _lm_by_provider:
            lm = _make_lm(provider)
            if lm is None:
                return None
            _lm_by_provider[provider] = lm
        return _lm_by_provider[provider]


# Markers of a per-day cap, as opposed to a per-minute one that backoff clears:
# Gemini "...PerDayPerProject...", OpenRouter "free-models-per-day",
# Groq "requests per day (RPD)", Ollama Cloud "...session usage limit" /
# "weekly usage limit".
_DAILY_QUOTA_MARKERS = ("perday", "per-day", "per day", "per_day", "usage limit")


def is_daily_quota_error(error: Exception) -> bool:
    """Return True if `error` is a 429 for a daily quota, not a per-minute one."""
    msg = str(error).lower()
    return any(marker in msg for marker in _DAILY_QUOTA_MARKERS)


# Used when a quota error carries no retry hint (OpenRouter, Groq).
DEFAULT_QUOTA_RETRY_S = 3600
_RETRY_DELAY_RE = re.compile(r'retryDelay"?\s*:\s*"?(\d+)s')


def quota_retry_after(error: Exception) -> int:
    """Seconds until the provider says the quota resets (Gemini's retryDelay)."""
    match = _RETRY_DELAY_RE.search(str(error))
    return int(match.group(1)) if match else DEFAULT_QUOTA_RETRY_S


def mark_provider_exhausted(provider: str, retry_after_s: int = DEFAULT_QUOTA_RETRY_S) -> None:
    """Record that `provider` is out of quota for the next `retry_after_s` seconds.

    An expiry time rather than a per-date flag: Gemini resets at midnight
    Pacific, not local midnight, so a date flag either skipped Gemini for the
    rest of the day or retried it hours before the reset.
    """
    with _state_lock:
        counts = _load_counts()
        counts[f"{provider}:exhausted_until"] = time.time() + retry_after_s
        _save_counts(counts)


def _provider_order() -> list[str]:
    explicit = os.environ.get("PAPER2MD_LLM_PROVIDER", "").strip().lower()
    default = ["gemini", "groq", "ollama", "nvidia", "openrouter", "openai"]
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
    keyed = _keyed_providers()
    if not keyed:
        raise RuntimeError(
            "No LLM provider API key found. Set at least one of: "
            "GEMINI_API_KEY, GROQ_API_KEY, OLLAMA_API_KEY, NVIDIA_NIM_API_KEY, "
            "OPENROUTER_API_KEY, OPENAI_API_KEY"
        )

    with _state_lock:
        provider = _preferred_provider(keyed)
        if provider is None:
            raise ProvidersExhaustedError(
                f"Daily quota exhausted for every configured provider: {', '.join(keyed)}"
            )
        _activate(provider)
        return provider


def _activate(provider: str) -> None:
    """Make `provider` the LM every thread uses for its next call.

    dspy.configure only works on the thread that first called it, so worker
    threads read the shared LM via active_lm() and run under dspy.context.
    """
    global _active_lm
    _active_lm = _make_lm(provider)
    if threading.current_thread() is threading.main_thread():
        dspy.configure(lm=_active_lm)


def active_lm() -> dspy.LM | None:
    """The LM currently selected by configure_dspy / failover, shared by all threads."""
    return _active_lm


def _keyed_providers() -> list[str]:
    return [p for p in _provider_order()
            if os.environ.get(PROVIDER_CONFIG[p]["env_key"], "").strip()]


def _preferred_provider(keyed: list[str]) -> str | None:
    return next((p for p in keyed if not is_provider_exhausted(p)), None)


def failover_provider(provider: str, retry_after_s: int = DEFAULT_QUOTA_RETRY_S) -> str:
    """Mark `provider` exhausted and switch DSPy to the next one.

    Returns the new provider's name; raises ProvidersExhaustedError if none is left.
    """
    with _state_lock:
        mark_provider_exhausted(provider, retry_after_s)
        return configure_dspy()


def restore_preferred_provider(current: str) -> str:
    """Switch back to a higher-priority provider whose quota window has passed.

    A long run that failed over to a slow fallback would otherwise stay there
    after the preferred provider's quota resets. Returns the provider in use.
    """
    with _state_lock:
        preferred = _preferred_provider(_keyed_providers())
        if preferred is None or preferred == current:
            return current
        _activate(preferred)
        return preferred


def get_sleep_for_provider(provider: str) -> float:
    """Return the inter-call sleep duration in seconds for the provider."""
    return PROVIDER_CONFIG.get(provider, {}).get("sleep_s", 2.0)


def rate_limit_sleep(provider: str) -> None:
    """Sleep the appropriate amount to respect provider RPM limits."""
    sleep_s = get_sleep_for_provider(provider)
    if sleep_s > 0:
        time.sleep(sleep_s)


# Earliest monotonic time the next call to each provider may start.
_next_call_at: dict[str, float] = {}


def wait_for_call_slot(provider: str) -> None:
    """Block until `provider` may start another call, spacing starts by 60/rpm.

    rate_limit_sleep() paces one thread; with several workers the per-thread
    sleeps overlap, so call starts are also spaced across all threads here.
    """
    interval = 60.0 / PROVIDER_CONFIG.get(provider, {}).get("rpm", 30)
    with _state_lock:
        now = time.monotonic()
        start = max(now, _next_call_at.get(provider, now))
        _next_call_at[provider] = start + interval
    if start > now:
        time.sleep(start - now)
