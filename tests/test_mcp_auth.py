"""Tests for the paper-processor MCP bearer-token middleware.

The server holds the Supabase service-role key (which bypasses RLS) and can
spend LLM quota, so these assertions are about refusing traffic, not just
accepting it.
"""

from __future__ import annotations

import asyncio
import importlib.util
import json
from pathlib import Path

import pytest

_AUTH_PY = Path(__file__).parent.parent / "mcp-servers" / "paper-processor-mcp" / "auth.py"
_spec = importlib.util.spec_from_file_location("mcp_auth", _AUTH_PY)
mcp_auth = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mcp_auth)

TOKEN = "s3cret-shared-token"


class Captured:
    """Collects the ASGI messages a handler sends."""

    def __init__(self) -> None:
        self.messages: list[dict] = []
        self.inner_called = False

    async def send(self, message: dict) -> None:
        self.messages.append(message)

    @property
    def status(self) -> int | None:
        for m in self.messages:
            if m["type"] == "http.response.start":
                return m["status"]
        return None

    @property
    def body(self) -> dict:
        for m in self.messages:
            if m["type"] == "http.response.body":
                return json.loads(m["body"])
        return {}

    @property
    def headers(self) -> dict[bytes, bytes]:
        for m in self.messages:
            if m["type"] == "http.response.start":
                return dict(m["headers"])
        return {}


def _run(scope, cap: Captured) -> None:
    """Drive the middleware to completion. Sync, so no pytest-asyncio needed."""
    async def inner(_scope, _receive, _send):
        cap.inner_called = True

    asyncio.run(mcp_auth.BearerAuthMiddleware(inner)(scope, None, cap.send))


def scope(path="/mcp", auth: str | None = None, typ="http"):
    headers = [(b"authorization", auth.encode())] if auth is not None else []
    return {"type": typ, "path": path, "headers": headers}


@pytest.fixture(autouse=True)
def _token(monkeypatch):
    monkeypatch.setenv("MCP_AUTH_TOKEN", TOKEN)


# ── accepting ──────────────────────────────────────────────────────────────

def test_valid_token_reaches_the_app():
    cap = Captured()
    _run(scope(auth=f"Bearer {TOKEN}"), cap)
    assert cap.inner_called and cap.status is None


def test_scheme_is_case_insensitive():
    cap = Captured()
    _run(scope(auth=f"bearer {TOKEN}"), cap)
    assert cap.inner_called


def test_surrounding_whitespace_is_tolerated():
    cap = Captured()
    _run(scope(auth=f"Bearer  {TOKEN}  "), cap)
    assert cap.inner_called


# ── rejecting ──────────────────────────────────────────────────────────────

def test_missing_header_is_rejected():
    cap = Captured()
    _run(scope(), cap)
    assert not cap.inner_called
    assert cap.status == 401


def test_wrong_token_is_rejected():
    cap = Captured()
    _run(scope(auth="Bearer not-the-token"), cap)
    assert not cap.inner_called and cap.status == 401


def test_token_prefix_is_rejected():
    """A truncated token must not pass — guards against non-constant-time bugs."""
    cap = Captured()
    _run(scope(auth=f"Bearer {TOKEN[:-1]}"), cap)
    assert not cap.inner_called and cap.status == 401


def test_wrong_scheme_is_rejected():
    cap = Captured()
    _run(scope(auth=f"Basic {TOKEN}"), cap)
    assert not cap.inner_called and cap.status == 401


def test_raw_token_without_scheme_is_rejected():
    cap = Captured()
    _run(scope(auth=TOKEN), cap)
    assert not cap.inner_called and cap.status == 401


def test_rejection_advertises_the_bearer_scheme():
    cap = Captured()
    _run(scope(), cap)
    assert cap.headers.get(b"www-authenticate") == b"Bearer"


def test_rejection_does_not_echo_the_expected_token():
    cap = Captured()
    _run(scope(auth="Bearer wrong"), cap)
    assert TOKEN not in json.dumps(cap.body)


# ── fail closed ────────────────────────────────────────────────────────────

def test_unconfigured_server_refuses_everything(monkeypatch):
    """A deploy that forgets the secret must break loudly, not serve openly."""
    monkeypatch.delenv("MCP_AUTH_TOKEN", raising=False)
    cap = Captured()
    _run(scope(auth=f"Bearer {TOKEN}"), cap)
    assert not cap.inner_called and cap.status == 503


def test_blank_token_is_treated_as_unconfigured(monkeypatch):
    monkeypatch.setenv("MCP_AUTH_TOKEN", "   ")
    cap = Captured()
    _run(scope(auth="Bearer    "), cap)
    assert not cap.inner_called and cap.status == 503


# ── public paths ───────────────────────────────────────────────────────────

def test_health_stays_public_for_uptime_checks():
    cap = Captured()
    _run(scope(path="/health"), cap)
    assert cap.inner_called, "/health must not require a token"


def test_health_is_public_even_when_unconfigured(monkeypatch):
    monkeypatch.delenv("MCP_AUTH_TOKEN", raising=False)
    cap = Captured()
    _run(scope(path="/health"), cap)
    assert cap.inner_called


def test_non_http_scopes_pass_through():
    cap = Captured()
    _run(scope(typ="lifespan", path=None), cap)
    assert cap.inner_called
