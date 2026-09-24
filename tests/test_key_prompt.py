"""Tests for lib/key_prompt.py — runtime API-key entry.

The point of this module is that a key never touches disk, never appears in
argv, and never gets echoed. Those properties are tested here alongside the
ordinary behaviour.
"""

from __future__ import annotations

import os

import pytest

from lib.key_prompt import (
    PROVIDER_KEYS,
    KeyPromptError,
    ensure_provider_key,
    prompt_for_key,
    validate_key,
)


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for env_name, _ in PROVIDER_KEYS.values():
        monkeypatch.delenv(env_name, raising=False)
    yield


@pytest.fixture
def tty(monkeypatch):
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)


def _answer(monkeypatch, value: str):
    monkeypatch.setattr("lib.key_prompt.getpass.getpass", lambda _p: value)


def _accept_all(monkeypatch):
    monkeypatch.setattr("lib.key_prompt.validate_key", lambda _p, _k: None)


# ── prompting ──────────────────────────────────────────────────────────────

def test_returns_the_entered_key(monkeypatch, tty):
    _answer(monkeypatch, "AIza-test-key")
    _accept_all(monkeypatch)
    assert prompt_for_key("gemini") == "AIza-test-key"


def test_exports_the_key_for_this_process(monkeypatch, tty):
    _answer(monkeypatch, "AIza-test-key")
    _accept_all(monkeypatch)
    prompt_for_key("gemini")
    assert os.environ["GEMINI_API_KEY"] == "AIza-test-key"


def test_strips_surrounding_whitespace_from_a_pasted_key(monkeypatch, tty):
    _answer(monkeypatch, "  AIza-test-key\n")
    _accept_all(monkeypatch)
    assert prompt_for_key("gemini") == "AIza-test-key"


def test_empty_input_is_rejected(monkeypatch, tty):
    _answer(monkeypatch, "   ")
    with pytest.raises(KeyPromptError, match="No GEMINI_API_KEY entered"):
        prompt_for_key("gemini")


def test_unknown_provider_is_rejected(monkeypatch, tty):
    with pytest.raises(KeyPromptError, match="Unknown provider"):
        prompt_for_key("hal9000")


def test_refuses_to_prompt_without_a_terminal(monkeypatch):
    monkeypatch.setattr("sys.stdin.isatty", lambda: False)
    with pytest.raises(KeyPromptError, match="stdin is not a terminal"):
        prompt_for_key("gemini")


# ── security properties ────────────────────────────────────────────────────

def test_uses_getpass_so_the_key_is_never_echoed(monkeypatch, tty):
    """A plain input() would echo the key into the terminal and scrollback."""
    calls = []
    monkeypatch.setattr("lib.key_prompt.getpass.getpass", lambda p: calls.append(p) or "k")
    _accept_all(monkeypatch)
    prompt_for_key("gemini")
    assert calls, "must read the key via getpass, not input()"


def test_key_is_not_written_to_any_file(monkeypatch, tty, tmp_path):
    """Guards against a future 'helpfully persist it to .env' regression."""
    _answer(monkeypatch, "AIza-secret")
    _accept_all(monkeypatch)
    monkeypatch.chdir(tmp_path)
    prompt_for_key("gemini")
    written = [p for p in tmp_path.rglob("*") if p.is_file() and "AIza-secret" in p.read_text(errors="ignore")]
    assert written == [], f"key leaked to {written}"


def test_rejected_key_is_removed_from_the_environment(monkeypatch, tty):
    """A bad key must not linger where a later call would pick it up."""
    _answer(monkeypatch, "bad-key")
    monkeypatch.setattr("lib.key_prompt.validate_key", lambda _p, _k: "authentication failed")
    with pytest.raises(KeyPromptError, match="authentication failed"):
        prompt_for_key("gemini")
    assert "GEMINI_API_KEY" not in os.environ


def test_validation_failure_message_does_not_contain_the_key(monkeypatch, tty):
    _answer(monkeypatch, "super-secret-value")
    monkeypatch.setattr("lib.key_prompt.validate_key", lambda _p, _k: "authentication failed")
    with pytest.raises(KeyPromptError) as exc:
        prompt_for_key("gemini")
    assert "super-secret-value" not in str(exc.value)


# ── ensure_provider_key ────────────────────────────────────────────────────

def test_existing_env_var_wins_and_does_not_prompt(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "from-env")
    monkeypatch.setattr("lib.key_prompt.getpass.getpass", lambda _p: pytest.fail("must not prompt"))
    assert ensure_provider_key("gemini") == "from-env"


def test_ask_overrides_an_existing_env_var(monkeypatch, tty):
    monkeypatch.setenv("GEMINI_API_KEY", "from-env")
    _answer(monkeypatch, "typed-in")
    _accept_all(monkeypatch)
    assert ensure_provider_key("gemini", ask=True) == "typed-in"


def test_non_interactive_without_a_key_returns_none(monkeypatch):
    monkeypatch.setattr("sys.stdin.isatty", lambda: False)
    assert ensure_provider_key("gemini") is None


# ── validate_key ───────────────────────────────────────────────────────────

class _Resp:
    def __init__(self, status_code): self.status_code = status_code


def test_validate_accepts_a_200(monkeypatch):
    monkeypatch.setattr("httpx.get", lambda *a, **k: _Resp(200))
    assert validate_key("gemini", "k") is None


@pytest.mark.parametrize("status", [401, 403])
def test_validate_reports_auth_failure(monkeypatch, status):
    monkeypatch.setattr("httpx.get", lambda *a, **k: _Resp(status))
    assert "authentication failed" in validate_key("gemini", "k")


def test_validate_reports_other_http_errors(monkeypatch):
    monkeypatch.setattr("httpx.get", lambda *a, **k: _Resp(500))
    assert "HTTP 500" in validate_key("gemini", "k")


def test_validate_survives_a_network_error(monkeypatch):
    def boom(*a, **k):
        raise OSError("no route to host")
    monkeypatch.setattr("httpx.get", boom)
    assert "could not reach gemini" in validate_key("gemini", "k")


def test_every_provider_has_a_validator(monkeypatch):
    monkeypatch.setattr("httpx.get", lambda *a, **k: _Resp(200))
    for provider in PROVIDER_KEYS:
        assert validate_key(provider, "k") is None, f"{provider} has no validator branch"
