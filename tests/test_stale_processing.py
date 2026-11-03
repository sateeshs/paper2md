"""A run killed mid-paper (CI timeout, OOM, lost runner) never resets the row,
so the batch reclaims papers left in "processing" past the stale cutoff."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from lib import supabase_push

NOW = datetime(2026, 11, 3, 12, 0, tzinfo=timezone.utc)
STALE = (NOW - supabase_push.STALE_PROCESSING_AFTER - timedelta(minutes=1)).isoformat()
FRESH = (NOW - timedelta(minutes=5)).isoformat()


class _Table:
    """In-memory `papers` table that honours eq/lt filters."""

    def __init__(self, rows: list[dict]) -> None:
        self.rows = rows

    def table(self, _name):
        return _Query(self.rows)


class _Query:
    def __init__(self, rows):
        self.rows, self.filters, self.payload = rows, [], None

    def select(self, _cols):
        return self

    def update(self, payload):
        self.payload = payload
        return self

    def eq(self, col, value):
        self.filters.append(lambda r: r.get(col) == value)
        return self

    def lt(self, col, value):
        cutoff = datetime.fromisoformat(value)
        self.filters.append(lambda r: datetime.fromisoformat(r[col]) < cutoff)
        return self

    def execute(self):
        matched = [r for r in self.rows if all(f(r) for f in self.filters)]
        if self.payload is not None:
            for r in matched:
                r.update(self.payload)

        class _Resp:
            data = [dict(r) for r in matched]

        return _Resp()


@pytest.fixture
def table(monkeypatch):
    def install(rows):
        t = _Table(rows)
        monkeypatch.setattr(supabase_push, "_get_client", lambda: t)
        monkeypatch.setattr(supabase_push, "_utcnow", lambda: NOW)
        return t
    return install


def test_mark_processing_records_the_claim_time(table):
    t = table([{"arxiv_id": "a", "status": "pending", "updated_at": STALE}])
    supabase_push.mark_processing("a")
    assert t.rows[0]["status"] == "processing"
    assert t.rows[0]["updated_at"] == NOW.isoformat()


def test_stale_processing_paper_is_requeued(table):
    t = table([
        {"arxiv_id": "p", "status": "pending", "updated_at": FRESH, "error_msg": None},
        {"arxiv_id": "s", "status": "processing", "updated_at": STALE, "error_msg": None},
    ])
    assert supabase_push.fetch_pending_arxiv_ids() == ["p", "s"]
    assert t.rows[1]["status"] == "pending"
    assert t.rows[1]["error_msg"] == supabase_push.INTERRUPTED_MSG


def test_paper_still_inside_its_run_window_is_left_alone(table):
    t = table([{"arxiv_id": "r", "status": "processing", "updated_at": FRESH, "error_msg": None}])
    assert supabase_push.fetch_pending_arxiv_ids() == []
    assert t.rows[0]["status"] == "processing"


def test_paper_interrupted_twice_is_marked_error_instead_of_retried(table):
    t = table([{"arxiv_id": "s", "status": "processing", "updated_at": STALE,
                "error_msg": supabase_push.INTERRUPTED_MSG}])
    assert supabase_push.fetch_pending_arxiv_ids() == []
    assert t.rows[0]["status"] == "error"
