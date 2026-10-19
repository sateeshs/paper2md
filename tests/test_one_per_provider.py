"""One block per provider (explain_math_only.py --one-per-provider).

Instead of every worker sharing one provider until it runs out, each provider
with quota left explains exactly one block at a time, so every free quota is
spent concurrently. A provider that runs out hands its block to another.
"""
from __future__ import annotations

import dataclasses
import json
import threading
import time

import pytest

from lib import dspy_config, dspy_modules
from tests.test_parallel_explain import _FakeClient, _load_explain_script, _rows


@pytest.fixture
def keyed(tmp_path, monkeypatch):
    """Isolate the usage file and key gemini, groq, nvidia and openai.

    Returns the loaded script — loading it runs load_dotenv, so it must
    happen before the real keys are cleared.
    """
    emo = _load_explain_script()
    monkeypatch.setattr(dspy_config, "_COUNTS_FILE", tmp_path / "counts.json")
    monkeypatch.delenv("PAPER2MD_LLM_PROVIDER", raising=False)
    for cfg in dspy_config.PROVIDER_CONFIG.values():
        monkeypatch.delenv(cfg["env_key"], raising=False)
    for name in ("GEMINI_API_KEY", "GROQ_API_KEY", "NVIDIA_NIM_API_KEY", "OPENAI_API_KEY"):
        monkeypatch.setenv(name, "k")
    return emo


def test_live_providers_are_keyed_unexhausted_and_free(keyed):
    dspy_config.mark_provider_exhausted("groq")
    # openai is paid, so it never takes a share of the blocks.
    assert dspy_config.live_providers() == ["gemini", "nvidia"]


def test_pinned_daily_quota_error_marks_only_that_provider(keyed, monkeypatch):
    monkeypatch.setattr(dspy_modules, "wait_for_call_slot", lambda _p: None)

    def quota_spent(**_kw):
        raise RuntimeError("429 free-models-per-day")

    with dspy_modules.pinned_provider("groq"):
        # dspy_modules holds the class it raises; other tests reload dspy_config.
        with pytest.raises(dspy_modules.ProviderQuotaError) as err:
            dspy_modules._call_with_tracking(quota_spent)

    assert err.value.provider == "groq"
    assert dspy_config.live_providers() == ["gemini", "nvidia"]


def _run(emo, monkeypatch, explainer_cls, rows: int, client=None):
    monkeypatch.setattr(emo, "_ensure_dspy", lambda: None)
    monkeypatch.setattr(emo, "_get_client", lambda: client or _FakeClient())
    monkeypatch.setattr(emo, "fetch_unexplained_blocks", lambda *a: _rows(rows))
    monkeypatch.setattr(emo, "find_defect", lambda _e: None)
    monkeypatch.setattr(dspy_modules, "MathExplainer", explainer_cls)
    return emo.run(arxiv_id="x", max_blocks=100, force=False, min_expr_len=6,
                   paper_type="textbook", one_per_provider=True)


def _explained(block):
    return dataclasses.replace(
        block, explanation=json.dumps({"ok": "yes"}),
        explanation_model=dspy_modules.pinned_provider_name(),
    )


def test_each_live_provider_explains_one_block_at_a_time(keyed, monkeypatch):
    emo = keyed
    client = _FakeClient()
    lock = threading.Lock()
    now: dict[str, int] = {}
    peak: dict[str, int] = {}

    class Recording:
        def explain_block(self, block, *args):
            provider = dspy_modules.pinned_provider_name()
            with lock:
                now[provider] = now.get(provider, 0) + 1
                peak[provider] = max(peak.get(provider, 0), now[provider])
            time.sleep(0.03)
            with lock:
                now[provider] -= 1
            return _explained(block)

    code = _run(emo, monkeypatch, Recording, rows=9, client=client)

    assert code == 0
    assert sorted(client.updated) == sorted(f"b{i}" for i in range(9))
    assert peak == {"gemini": 1, "groq": 1, "nvidia": 1}


def test_spent_provider_hands_its_block_to_another(keyed, monkeypatch):
    emo = keyed
    client = _FakeClient()

    class GroqRunsOut:
        def explain_block(self, block, *args):
            provider = dspy_modules.pinned_provider_name()
            if provider == "groq":
                dspy_config.mark_provider_exhausted("groq")
                raise dspy_config.ProviderQuotaError("groq")
            time.sleep(0.01)
            return _explained(block)

    code = _run(emo, monkeypatch, GroqRunsOut, rows=6, client=client)

    assert code == 0
    assert sorted(client.updated) == sorted(f"b{i}" for i in range(6))


def test_stops_with_quota_exit_when_every_provider_is_spent(keyed, monkeypatch):
    emo = keyed
    calls: list[str] = []

    class AllRunOut:
        def explain_block(self, block, *args):
            provider = dspy_modules.pinned_provider_name()
            calls.append(provider)
            dspy_config.mark_provider_exhausted(provider)
            raise dspy_config.ProviderQuotaError(provider)

    code = _run(emo, monkeypatch, AllRunOut, rows=10)

    assert code == emo.EXIT_QUOTA_EXHAUSTED
    assert sorted(calls) == ["gemini", "groq", "nvidia"]


def test_lm_calls_have_a_timeout(keyed):
    assert dspy_config._make_lm("nvidia").kwargs["timeout"] == dspy_config.LM_TIMEOUT_S


def test_provider_whose_quota_returns_joins_while_lanes_are_busy(keyed, monkeypatch):
    emo = keyed
    monkeypatch.setattr(emo, "REFILL_INTERVAL_S", 0.02)
    dspy_config.mark_provider_exhausted("gemini")
    dspy_config.mark_provider_exhausted("groq")
    used: set[str] = set()

    class SlowNvidia:
        def explain_block(self, block, *args):
            provider = dspy_modules.pinned_provider_name()
            used.add(provider)
            if provider == "nvidia" and "gemini" not in used:
                # Gemini's quota comes back while this lane is still busy.
                counts = dspy_config._load_counts()
                counts.pop("gemini:exhausted_until")
                dspy_config._save_counts(counts)
                deadline = time.monotonic() + 2
                while "gemini" not in used and time.monotonic() < deadline:
                    time.sleep(0.01)
            return _explained(block)

    code = _run(emo, monkeypatch, SlowNvidia, rows=4)

    assert code == 0
    assert "gemini" in used
