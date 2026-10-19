"""Parallel math explanation (explain_math_only.py --workers N).

Free providers spend most of each call generating (~70s on OpenRouter), so one
call at a time leaves most of the requests-per-minute allowance unused. Worker
threads share one provider state: usage counts must not lose updates, failover
must work from any thread (dspy.configure only works on its owner thread), and
call starts stay spaced to each provider's rpm.
"""
from __future__ import annotations

import importlib.util
import json
import threading
import time
from pathlib import Path

import pytest

from lib import dspy_config


@pytest.fixture
def providers(tmp_path, monkeypatch):
    """Isolate the usage file and give only gemini + openrouter a key."""
    monkeypatch.setattr(dspy_config, "_COUNTS_FILE", tmp_path / "counts.json")
    monkeypatch.delenv("PAPER2MD_LLM_PROVIDER", raising=False)
    for cfg in dspy_config.PROVIDER_CONFIG.values():
        monkeypatch.delenv(cfg["env_key"], raising=False)
    monkeypatch.setenv("GEMINI_API_KEY", "g-key")
    monkeypatch.setenv("OPENROUTER_API_KEY", "or-key")


def test_concurrent_count_increments_are_not_lost(providers):
    def bump():
        for _ in range(25):
            dspy_config.increment_provider_count("gemini")

    threads = [threading.Thread(target=bump) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert dspy_config.get_provider_count("gemini") == 200


def test_failover_from_a_worker_thread_switches_the_shared_lm(providers, monkeypatch):
    configured_from: list[bool] = []
    monkeypatch.setattr(
        dspy_config.dspy, "configure",
        lambda **kw: configured_from.append(threading.current_thread() is threading.main_thread()),
    )
    dspy_config.configure_dspy()
    assert dspy_config.active_lm().model.startswith("gemini/")

    errors: list[Exception] = []

    def worker():
        try:
            dspy_config.failover_provider("gemini")
        except Exception as e:  # surfaced below; a thread swallows it otherwise
            errors.append(e)

    t = threading.Thread(target=worker)
    t.start()
    t.join()

    assert errors == []
    assert dspy_config.active_lm().model.startswith("openrouter/")
    assert all(configured_from)  # dspy.configure never called off the main thread


def test_call_starts_are_spaced_by_the_provider_rpm(monkeypatch):
    clock = {"t": 1000.0}
    monkeypatch.setattr(dspy_config.time, "monotonic", lambda: clock["t"])
    monkeypatch.setattr(dspy_config.time, "sleep", lambda s: clock.__setitem__("t", clock["t"] + s))
    monkeypatch.setattr(dspy_config, "_next_call_at", {})

    starts = []
    for _ in range(3):
        dspy_config.wait_for_call_slot("groq")  # 30 rpm -> one start every 2s
        starts.append(clock["t"])

    assert starts == [1000.0, 1002.0, 1004.0]


def _load_explain_script():
    path = Path(__file__).parent.parent / "explain_math_only.py"
    spec = importlib.util.spec_from_file_location("emo_parallel", path)
    emo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(emo)
    return emo


def _rows(n: int) -> list[dict]:
    return [{"id": f"b{i}", "order_idx": i, "env_type": "equation",
             "latex_expr": r"\begin{equation}x = 1\end{equation}",
             "sections": {"id": "s1", "title": "S", "paper_id": "p",
                          "papers": {"arxiv_id": "x", "title": "P"}}}
            for i in range(n)]


class _FakeClient:
    """Records math_blocks updates made through the supabase query chain."""

    def __init__(self) -> None:
        self.updated: list[str] = []
        self._payload: dict = {}

    def table(self, _name):
        return self

    def update(self, payload):
        self._payload = payload
        return self

    def eq(self, _col, value):
        self.updated.append(value)
        return self

    def execute(self):
        return None


def test_run_with_workers_explains_blocks_concurrently(monkeypatch):
    import dataclasses

    from lib import dspy_modules

    emo = _load_explain_script()
    client = _FakeClient()
    lock = threading.Lock()
    state = {"now": 0, "peak": 0}

    class SlowExplainer:
        def explain_block(self, block, *args):
            with lock:
                state["now"] += 1
                state["peak"] = max(state["peak"], state["now"])
            time.sleep(0.05)
            with lock:
                state["now"] -= 1
            return dataclasses.replace(block, explanation=json.dumps({"ok": "yes"}),
                                       explanation_model="gemini")

    monkeypatch.setattr(emo, "_ensure_dspy", lambda: None)
    monkeypatch.setattr(emo, "_get_client", lambda: client)
    monkeypatch.setattr(emo, "fetch_unexplained_blocks", lambda *a: _rows(8))
    monkeypatch.setattr(emo, "find_defect", lambda _e: None)
    monkeypatch.setattr(dspy_modules, "MathExplainer", SlowExplainer)

    code = emo.run(arxiv_id="x", max_blocks=10, force=False, min_expr_len=6,
                   paper_type="textbook", workers=4)

    assert code == 0
    assert sorted(client.updated) == sorted(f"b{i}" for i in range(8))
    assert state["peak"] > 1


def test_exhaustion_with_workers_stops_submitting_new_blocks(monkeypatch):
    from lib import dspy_modules

    emo = _load_explain_script()
    calls: list[int] = []

    class Exhausted:
        def explain_block(self, block, *args):
            calls.append(block.order_idx)
            raise dspy_config.ProvidersExhaustedError("all exhausted")

    monkeypatch.setattr(emo, "_ensure_dspy", lambda: None)
    monkeypatch.setattr(emo, "_get_client", lambda: None)
    monkeypatch.setattr(emo, "fetch_unexplained_blocks", lambda *a: _rows(20))
    monkeypatch.setattr(dspy_modules, "MathExplainer", Exhausted)

    code = emo.run(arxiv_id="x", max_blocks=30, force=False, min_expr_len=6,
                   paper_type="textbook", workers=3)

    assert code == emo.EXIT_QUOTA_EXHAUSTED
    assert len(calls) <= 3
