"""Tests for the PAPER2MD_OPENROUTER_MODEL override in lib/dspy_config.py.

The free slug queues requests for ~70s each and is capped at 200/day. A paid
OpenRouter account should be able to opt out of that without editing code,
while free-tier keys keep the safe defaults.
"""

from __future__ import annotations

import importlib

import pytest


def load_config(monkeypatch, model: str | None):
    """Re-import dspy_config with PAPER2MD_OPENROUTER_MODEL set or cleared."""
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
