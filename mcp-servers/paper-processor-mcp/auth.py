"""Bearer-token auth for the paper-processor MCP server.

This endpoint can spend LLM quota and writes to Supabase with the service-role
key, which bypasses RLS. Modal URLs are not secrets — they leak through logs,
browser history and request records — so the endpoint must authenticate.

Fails closed: without MCP_AUTH_TOKEN configured every MCP request is refused,
so a deploy that forgets the secret breaks loudly instead of serving traffic
unauthenticated.

/health stays public so uptime checks and GET /api/health keep working; it
returns no sensitive information.
"""

from __future__ import annotations

import hmac
import logging
import os

log = logging.getLogger(__name__)

PUBLIC_PATHS = frozenset({"/health"})


class BearerAuthMiddleware:
    """Pure-ASGI middleware rejecting requests without the shared token."""

    def __init__(self, app, token_env: str = "MCP_AUTH_TOKEN") -> None:
        self.app = app
        self.token_env = token_env

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http" or scope.get("path") in PUBLIC_PATHS:
            await self.app(scope, receive, send)
            return

        expected = os.environ.get(self.token_env, "").strip()
        if not expected:
            log.error("%s is not configured — refusing all MCP requests", self.token_env)
            await self._deny(send, 503, "Server is not configured for authentication")
            return

        if not _token_matches(scope.get("headers") or [], expected):
            await self._deny(send, 401, "Missing or invalid bearer token")
            return

        await self.app(scope, receive, send)

    @staticmethod
    async def _deny(send, status: int, message: str) -> None:
        body = f'{{"error": "{message}"}}'.encode()
        await send({
            "type": "http.response.start",
            "status": status,
            "headers": [
                (b"content-type", b"application/json"),
                (b"www-authenticate", b"Bearer"),
            ],
        })
        await send({"type": "http.response.body", "body": body})


def _token_matches(headers: list[tuple[bytes, bytes]], expected: str) -> bool:
    """True when an Authorization: Bearer header matches *expected*."""
    for name, value in headers:
        if name.lower() != b"authorization":
            continue
        raw = value.decode("latin-1").strip()
        scheme, _, token = raw.partition(" ")
        if scheme.lower() != "bearer":
            return False
        # compare_digest keeps the check constant-time.
        return hmac.compare_digest(token.strip(), expected)
    return False
