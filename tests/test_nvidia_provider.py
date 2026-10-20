"""Tests for the NVIDIA NIM provider in lib/dspy_config.py.

build.nvidia.com's free tier has no daily cap, only ~40 requests/minute, so it
keeps the runner going after the daily-capped providers are spent.
"""

from __future__ import annotations

import importlib

import pytest


def load_config(monkeypatch, model: str | None = None):
    """Re-import dspy_config with PAPER2MD_NVIDIA_MODEL set or cleared."""
    if model is None:
        monkeypatch.delenv("PAPER2MD_NVIDIA_MODEL", raising=False)
    else:
        monkeypatch.setenv("PAPER2MD_NVIDIA_MODEL", model)
    monkeypatch.delenv("PAPER2MD_LLM_PROVIDER", raising=False)

    import lib.dspy_config as cfg
    return importlib.reload(cfg)


@pytest.fixture(autouse=True)
def _restore(monkeypatch):
    yield
    monkeypatch.delenv("PAPER2MD_NVIDIA_MODEL", raising=False)
    import lib.dspy_config as cfg
    importlib.reload(cfg)


def test_defaults_to_nemotron_super(monkeypatch):
    cfg = load_config(monkeypatch)
    assert cfg.PROVIDER_CONFIG["nvidia"]["model"] == "nvidia_nim/nvidia/nemotron-3-super-120b-a12b"


def test_reads_the_litellm_standard_key(monkeypatch):
    cfg = load_config(monkeypatch)
    assert cfg.PROVIDER_CONFIG["nvidia"]["env_key"] == "NVIDIA_NIM_API_KEY"


def test_has_no_daily_cap_and_paces_to_40_rpm(monkeypatch):
    cfg = load_config(monkeypatch)
    nvidia = cfg.PROVIDER_CONFIG["nvidia"]
    assert nvidia["daily_limit"] is None
    assert nvidia["rpm"] == 40


def test_model_is_overridable(monkeypatch):
    cfg = load_config(monkeypatch, "nvidia_nim/nvidia/nemotron-3-ultra-550b-a55b")
    assert cfg.PROVIDER_CONFIG["nvidia"]["model"] == "nvidia_nim/nvidia/nemotron-3-ultra-550b-a55b"


def test_blank_override_falls_back_to_default(monkeypatch):
    cfg = load_config(monkeypatch, "   ")
    assert cfg.PROVIDER_CONFIG["nvidia"]["model"] == "nvidia_nim/nvidia/nemotron-3-super-120b-a12b"


def test_runs_after_the_daily_capped_providers_and_before_openrouter(monkeypatch):
    cfg = load_config(monkeypatch)
    order = cfg._provider_order()
    assert order.index("ollama") < order.index("nvidia") < order.index("openrouter")


def test_is_never_exhausted_by_call_count(monkeypatch):
    cfg = load_config(monkeypatch)
    monkeypatch.setattr(cfg, "get_provider_count", lambda _p: 100_000)
    monkeypatch.setattr(cfg, "_load_counts", lambda: {})
    assert cfg.is_provider_exhausted("nvidia") is False


def test_ultra_is_a_second_nvidia_lane_on_the_same_key(monkeypatch):
    cfg = load_config(monkeypatch)
    ultra = cfg.PROVIDER_CONFIG["nvidia_ultra"]
    assert ultra["model"] == "nvidia_nim/nvidia/nemotron-3-ultra-550b-a55b"
    assert ultra["env_key"] == cfg.PROVIDER_CONFIG["nvidia"]["env_key"]
    assert ultra["daily_limit"] is None
    order = cfg._provider_order()
    assert order.index("nvidia") < order.index("nvidia_ultra") < order.index("openrouter")


def test_active_provider_tells_the_two_nvidia_models_apart(monkeypatch):
    cfg = load_config(monkeypatch)
    from lib import dspy_modules

    class FakeLM:
        model = cfg.PROVIDER_CONFIG["nvidia_ultra"]["model"]

    monkeypatch.setattr(dspy_modules, "active_lm", lambda: FakeLM())
    monkeypatch.setattr(dspy_modules, "PROVIDER_CONFIG", cfg.PROVIDER_CONFIG)
    assert dspy_modules._active_provider() == "nvidia_ultra"
