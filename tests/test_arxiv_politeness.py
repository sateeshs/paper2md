"""Tests for download_pdf_with_retry, tmpdir cleanup, and ArXiv API politeness."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from summarize_papers import download_pdf_with_retry


class FakeRespSimple:
    """Fake HTTP response for testing."""

    def __init__(self, status: int, content: bytes = b""):
        self.status_code = status
        self.content = content

    def raise_for_status(self) -> None:
        """Raise on 4xx/5xx status codes."""
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


def test_retries_on_429_then_succeeds(monkeypatch):
    """Test that download_pdf_with_retry retries on 429 and succeeds on 3rd attempt."""
    calls = []
    sleeps = []

    def fake_get(url, **kw):
        calls.append(url)
        if len(calls) < 3:
            return FakeRespSimple(429)
        return FakeRespSimple(200, b"%PDF-1.4 fake")

    monkeypatch.setattr("summarize_papers.httpx.get", fake_get)
    data = download_pdf_with_retry("1234.5678", attempts=3, sleep_fn=sleeps.append)
    assert data == b"%PDF-1.4 fake"
    assert len(calls) == 3
    assert len(sleeps) == 2  # backed off twice


def test_gives_up_after_attempts(monkeypatch):
    """Test that download_pdf_with_retry gives up after max attempts."""

    class Always429:
        status_code = 429
        content = b""

        def raise_for_status(self):
            raise RuntimeError("HTTP 429")

    monkeypatch.setattr("summarize_papers.httpx.get", lambda url, **kw: Always429())
    with pytest.raises(RuntimeError):
        download_pdf_with_retry("1234.5678", attempts=2, sleep_fn=lambda s: None)


def test_retries_on_500(monkeypatch):
    """Test that download_pdf_with_retry retries on 5xx errors."""
    calls = []
    sleeps = []

    def fake_get(url, **kw):
        calls.append(url)
        if len(calls) < 2:
            return FakeRespSimple(500)
        return FakeRespSimple(200, b"%PDF-1.4 success")

    monkeypatch.setattr("summarize_papers.httpx.get", fake_get)
    data = download_pdf_with_retry("5678.1234", attempts=3, sleep_fn=sleeps.append)
    assert data == b"%PDF-1.4 success"
    assert len(calls) == 2
    assert len(sleeps) == 1


def test_does_not_retry_on_4xx_client_error(monkeypatch):
    """Test that download_pdf_with_retry does not retry on 4xx client errors."""
    calls = []

    def fake_get(url, **kw):
        calls.append(url)
        return FakeRespSimple(404)

    monkeypatch.setattr("summarize_papers.httpx.get", fake_get)
    with pytest.raises(RuntimeError):
        download_pdf_with_retry("9999.9999", attempts=3, sleep_fn=lambda s: None)
    assert len(calls) == 1  # only one attempt for non-retryable error


def test_exponential_backoff_schedule(monkeypatch):
    """Test that backoff follows 3s, 9s, 27s schedule."""
    sleeps = []

    def fake_get(url, **kw):
        return FakeRespSimple(429)

    monkeypatch.setattr("summarize_papers.httpx.get", fake_get)
    with pytest.raises(RuntimeError):
        download_pdf_with_retry("1111.2222", attempts=4, sleep_fn=sleeps.append)
    assert sleeps == [3.0, 9.0, 27.0]
