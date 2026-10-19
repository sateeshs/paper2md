"""A paper marked "explaining" is readable while the backfill runs; the runner
flips it to "complete" once a pass has worked through every remaining block."""
from __future__ import annotations

import dataclasses
import importlib.util
import json
from pathlib import Path

import pytest

from lib import dspy_config


class _RecordingClient:
    """Records each update as (table, payload, filters)."""

    def __init__(self) -> None:
        self.updates: list[tuple[str, dict, dict]] = []

    def table(self, name):
        return _Query(self, name)


class _Query:
    def __init__(self, client, name):
        self.client, self.name, self.payload, self.filters = client, name, {}, {}

    def update(self, payload):
        self.payload = payload
        return self

    def eq(self, col, value):
        self.filters[col] = value
        return self

    def execute(self):
        self.client.updates.append((self.name, self.payload, self.filters))


def _rows(n):
    return [{"id": f"b{i}", "order_idx": i, "env_type": "equation",
             "latex_expr": r"\begin{equation}x = 1\end{equation}",
             "sections": {"id": "s1", "title": "S", "paper_id": "p",
                          "papers": {"arxiv_id": "x", "title": "P"}}}
            for i in range(n)]


@pytest.fixture
def emo(monkeypatch):
    from lib import dspy_modules

    path = Path(__file__).parent.parent / "explain_math_only.py"
    spec = importlib.util.spec_from_file_location("emo_explaining", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    class Explainer:
        def explain_block(self, block, *args):
            return dataclasses.replace(block, explanation=json.dumps({"ok": "y"}),
                                       explanation_model="gemini")

    monkeypatch.setattr(module, "_ensure_dspy", lambda: None)
    monkeypatch.setattr(module, "find_defect", lambda _e: None)
    monkeypatch.setattr(dspy_modules, "MathExplainer", Explainer)
    return module


COMPLETE = ("papers", {"status": "complete"}, {"arxiv_id": "x", "status": "explaining"})


def _run(emo, monkeypatch, rows, **kw):
    client = _RecordingClient()
    monkeypatch.setattr(emo, "_get_client", lambda: client)
    monkeypatch.setattr(emo, "fetch_unexplained_blocks", lambda *a: rows)
    args = dict(arxiv_id="x", max_blocks=10, force=False, min_expr_len=6, paper_type="textbook")
    args.update(kw)
    return emo.run(**args), client


def test_full_pass_marks_an_explaining_paper_complete(emo, monkeypatch):
    code, client = _run(emo, monkeypatch, _rows(3))
    assert code == 0
    assert client.updates[-1] == COMPLETE


def test_nothing_left_to_explain_marks_it_complete(emo, monkeypatch):
    _, client = _run(emo, monkeypatch, [])
    assert client.updates == [COMPLETE]


def test_capped_pass_does_not_mark_complete(emo, monkeypatch):
    _, client = _run(emo, monkeypatch, _rows(5), max_blocks=2)
    assert COMPLETE not in client.updates


def test_dry_run_does_not_mark_complete(emo, monkeypatch):
    _, client = _run(emo, monkeypatch, _rows(2), dry_run=True)
    assert client.updates == []


def test_exhausted_pass_does_not_mark_complete(emo, monkeypatch):
    from lib import dspy_modules

    class Exhausted:
        def explain_block(self, block, *args):
            raise dspy_config.ProvidersExhaustedError("all exhausted")

    monkeypatch.setattr(dspy_modules, "MathExplainer", Exhausted)
    code, client = _run(emo, monkeypatch, _rows(3))
    assert code == emo.EXIT_QUOTA_EXHAUSTED
    assert COMPLETE not in client.updates
