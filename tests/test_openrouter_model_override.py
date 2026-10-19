"""Tests for the PAPER2MD_OPENROUTER_MODEL override in lib/dspy_config.py.

The free slug queues requests for ~70s each and is capped at 200/day. A paid
OpenRouter account should be able to opt out of that without editing code,
while free-tier keys keep the safe defaults.
"""

from __future__ import annotations

import importlib

import pytest


def load_config(monkeypatch, model: str | None, daily_limit: str | None = None):
    """Re-import dspy_config with the OpenRouter env overrides set or cleared."""
    if daily_limit is None:
        monkeypatch.delenv("PAPER2MD_OPENROUTER_DAILY_LIMIT", raising=False)
    else:
        monkeypatch.setenv("PAPER2MD_OPENROUTER_DAILY_LIMIT", daily_limit)
    if model is None:
        monkeypatch.delenv("PAPER2MD_OPENROUTER_MODEL", raising=False)
    else:
        monkeypatch.setenv("PAPER2MD_OPENROUTER_MODEL", model)

    import lib.dspy_config as cfg
    return importlib.reload(cfg)


@pytest.fixture(autouse=True)
def _restore(monkeypatch):
    yield
    monkeypatch.delenv("PAPER2MD_OPENROUTER_MODEL", raising=False)
    monkeypatch.delenv("PAPER2MD_OPENROUTER_DAILY_LIMIT", raising=False)
    import lib.dspy_config as cfg
    importlib.reload(cfg)


def test_defaults_to_the_free_slug(monkeypatch):
    cfg = load_config(monkeypatch, None)
    assert cfg.PROVIDER_CONFIG["openrouter"]["model"] == "openrouter/openrouter/free"


def test_free_slug_keeps_the_protective_throttles(monkeypatch):
    cfg = load_config(monkeypatch, None)
    openrouter = cfg.PROVIDER_CONFIG["openrouter"]
    assert openrouter["daily_limit"] == 200
    assert openrouter["rpm"] == 10
    assert openrouter["sleep_s"] == 6.0


def test_override_sets_the_model(monkeypatch):
    cfg = load_config(monkeypatch, "openrouter/google/gemini-2.0-flash-001")
    assert cfg.PROVIDER_CONFIG["openrouter"]["model"] == "openrouter/google/gemini-2.0-flash-001"


def test_override_lifts_the_free_tier_throttles(monkeypatch):
    cfg = load_config(monkeypatch, "openrouter/google/gemini-2.0-flash-001")
    openrouter = cfg.PROVIDER_CONFIG["openrouter"]
    assert openrouter["daily_limit"] is None
    assert openrouter["rpm"] > 10
    assert openrouter["sleep_s"] < 6.0


def test_explicitly_setting_the_free_slug_keeps_throttles(monkeypatch):
    cfg = load_config(monkeypatch, "openrouter/openrouter/free")
    assert cfg.PROVIDER_CONFIG["openrouter"]["daily_limit"] == 200


def test_blank_override_falls_back_to_free(monkeypatch):
    cfg = load_config(monkeypatch, "   ")
    openrouter = cfg.PROVIDER_CONFIG["openrouter"]
    assert openrouter["model"] == "openrouter/openrouter/free"
    assert openrouter["daily_limit"] == 200


def test_paid_provider_is_never_marked_exhausted(monkeypatch):
    cfg = load_config(monkeypatch, "openrouter/google/gemini-2.0-flash-001")
    monkeypatch.setattr(cfg, "get_provider_count", lambda _p: 10_000)
    assert cfg.is_provider_exhausted("openrouter") is False


def test_free_provider_is_exhausted_past_its_limit(monkeypatch):
    cfg = load_config(monkeypatch, None)
    monkeypatch.setattr(cfg, "get_provider_count", lambda _p: 200)
    assert cfg.is_provider_exhausted("openrouter") is True


def test_pinned_free_model_keeps_the_protective_throttles(monkeypatch):
    # A specific ":free" model still draws on the free-model daily allowance.
    cfg = load_config(monkeypatch, "openrouter/google/gemma-4-31b-it:free")
    openrouter = cfg.PROVIDER_CONFIG["openrouter"]
    assert openrouter["model"] == "openrouter/google/gemma-4-31b-it:free"
    assert openrouter["daily_limit"] == 200
    assert openrouter["sleep_s"] == 6.0


def test_free_daily_limit_is_overridable(monkeypatch):
    # Accounts that have bought credits get 1,000 free requests a day, not 200.
    cfg = load_config(monkeypatch, None, daily_limit="950")
    assert cfg.PROVIDER_CONFIG["openrouter"]["daily_limit"] == 950


@pytest.mark.parametrize("bad", ["", "  ", "lots", "0", "-5"])
def test_invalid_daily_limit_falls_back_to_default(monkeypatch, bad):
    cfg = load_config(monkeypatch, None, daily_limit=bad)
    assert cfg.PROVIDER_CONFIG["openrouter"]["daily_limit"] == 200


def test_openrouter_quota_day_rolls_over_at_utc_midnight(monkeypatch):
    # OpenRouter resets free-model allowances at 00:00 UTC, not local midnight.
    cfg = load_config(monkeypatch, None)
    just_after_utc_midnight = 1792461600.0  # 2026-10-20T02:00:00Z
    assert cfg.quota_day("openrouter", just_after_utc_midnight) == "2026-10-20"
