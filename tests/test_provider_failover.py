"""Provider failover when a free tier's daily quota runs out.

dspy.LM has no `fallback` parameter, so the old chain never left the primary:
once Gemini's 500/day cap was hit every block burned four backoff retries and
failed. A daily-quota 429 must instead switch to the next provider with a key,
and raise ProvidersExhaustedError once none are left so callers can stop.
"""
from types import SimpleNamespace

import pytest

from lib import dspy_config
from lib.models import MathBlock

GEMINI_DAILY = (
    'litellm.RateLimitError: {"error": {"code": 429, "status": "RESOURCE_EXHAUSTED", '
    '"details": [{"quotaId": "GenerateRequestsPerDayPerProjectPerModel-FreeTier", '
    '"quotaValue": "500"}, {"retryDelay": "12442s"}]}}'
)
GEMINI_PER_MINUTE = (
    'litellm.RateLimitError: {"error": {"code": 429, "status": "RESOURCE_EXHAUSTED", '
    '"details": [{"quotaId": "GenerateRequestsPerMinutePerProjectPerModel-FreeTier"}]}}'
)
OPENROUTER_DAILY = "litellm.RateLimitError: 429 Rate limit exceeded: free-models-per-day"


@pytest.fixture
def providers(tmp_path, monkeypatch):
    """Isolate the usage file and give only gemini + openrouter a key."""
    monkeypatch.setattr(dspy_config, "_COUNTS_FILE", tmp_path / "counts.json")
    monkeypatch.delenv("PAPER2MD_LLM_PROVIDER", raising=False)
    for name, cfg in dspy_config.PROVIDER_CONFIG.items():
        monkeypatch.delenv(cfg["env_key"], raising=False)
    monkeypatch.setenv("GEMINI_API_KEY", "g-key")
    monkeypatch.setenv("OPENROUTER_API_KEY", "or-key")
    monkeypatch.setattr(dspy_config.dspy, "configure", lambda **kw: None)


@pytest.mark.parametrize("message", [GEMINI_DAILY, OPENROUTER_DAILY,
                                     "Rate limit reached on requests per day (RPD)"])
def test_daily_quota_errors_are_recognised(message):
    assert dspy_config.is_daily_quota_error(Exception(message))


def test_per_minute_limit_is_not_a_daily_quota():
    assert not dspy_config.is_daily_quota_error(Exception(GEMINI_PER_MINUTE))


def test_configure_skips_a_provider_marked_exhausted(providers):
    assert dspy_config.configure_dspy() == "gemini"
    dspy_config.mark_provider_exhausted("gemini")
    assert dspy_config.configure_dspy() == "openrouter"


def test_configure_raises_when_every_keyed_provider_is_exhausted(providers):
    dspy_config.mark_provider_exhausted("gemini")
    dspy_config.mark_provider_exhausted("openrouter")
    with pytest.raises(dspy_config.ProvidersExhaustedError):
        dspy_config.configure_dspy()


def test_call_fails_over_to_next_provider_on_daily_quota(providers, monkeypatch):
    from lib import dspy_modules

    active = {"name": "gemini"}
    monkeypatch.setattr(dspy_modules, "_active_provider", lambda: active["name"])
    monkeypatch.setattr(dspy_modules, "rate_limit_sleep", lambda p: None)

    def fake_failover(provider):
        dspy_config.mark_provider_exhausted(provider)
        active["name"] = "openrouter"
        return "openrouter"

    monkeypatch.setattr(dspy_modules, "failover_provider", fake_failover)

    def module(**kwargs):
        if active["name"] == "gemini":
            raise Exception(GEMINI_DAILY)
        return "ok"

    assert dspy_modules._call_with_tracking(module) == "ok"
    assert dspy_config.is_provider_exhausted("gemini")


def test_call_raises_when_failover_has_nowhere_to_go(providers, monkeypatch):
    from lib import dspy_modules

    monkeypatch.setattr(dspy_modules, "_active_provider", lambda: "openrouter")

    def module(**kwargs):
        raise Exception(OPENROUTER_DAILY)

    dspy_config.mark_provider_exhausted("gemini")
    with pytest.raises(dspy_config.ProvidersExhaustedError):
        dspy_modules._call_with_tracking(module)


def test_explain_block_propagates_exhaustion_instead_of_swallowing(monkeypatch):
    from lib import dspy_modules

    # dspy_modules' own reference: another test reloads lib.dspy_config,
    # which would make dspy_config.ProvidersExhaustedError a different class.
    error = dspy_modules.ProvidersExhaustedError

    def exhausted(*args, **kwargs):
        raise error("all providers exhausted")

    monkeypatch.setattr(dspy_modules, "_call_with_tracking", exhausted)
    block = MathBlock(order_idx=0, env_type="equation",
                      latex_expr=r"\begin{equation}x = 1\end{equation}",
                      context_before="", context_after="")
    with pytest.raises(error):
        dspy_modules.MathExplainer().explain_block(block, "Paper", "Section")


def test_run_stops_at_first_exhausted_block_with_distinct_exit_code(monkeypatch):
    import importlib.util
    from pathlib import Path

    from lib import dspy_modules

    path = Path(__file__).parent.parent / "explain_math_only.py"
    spec = importlib.util.spec_from_file_location("emo_failover", path)
    emo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(emo)

    rows = [{"id": f"b{i}", "order_idx": i, "env_type": "equation",
             "latex_expr": r"\begin{equation}x = 1\end{equation}",
             "sections": {"id": "s1", "title": "S", "paper_id": "p",
                          "papers": {"arxiv_id": "x", "title": "P"}}}
            for i in range(3)]
    calls: list[int] = []

    class Exhausted:
        def explain_block(self, block, *args):
            calls.append(block.order_idx)
            raise dspy_config.ProvidersExhaustedError("all exhausted")

    monkeypatch.setattr(emo, "_ensure_dspy", lambda: None)
    monkeypatch.setattr(emo, "_get_client", lambda: None)
    monkeypatch.setattr(emo, "fetch_unexplained_blocks", lambda *a: rows)
    monkeypatch.setattr(dspy_modules, "MathExplainer", Exhausted)

    code = emo.run(arxiv_id="x", max_blocks=10, force=False, min_expr_len=6,
                   paper_type="textbook")

    assert code == emo.EXIT_QUOTA_EXHAUSTED
    assert calls == [0]
