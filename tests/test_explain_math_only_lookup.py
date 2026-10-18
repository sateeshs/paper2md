import importlib.util
from pathlib import Path

import pytest

MODULE_PATH = Path(__file__).parent.parent / "explain_math_only.py"
spec = importlib.util.spec_from_file_location("explain_math_only", MODULE_PATH)
emo = importlib.util.module_from_spec(spec)
spec.loader.exec_module(emo)


class FakeResponse:
    def __init__(self, data):
        self.data = data


class FakeQuery:
    """Chainable stub matching the supabase-py builder methods used."""
    def __init__(self, data):
        self._data = data

    def select(self, *_):
        return self

    def eq(self, *_):
        return self

    def single(self):
        return self

    def maybe_single(self):
        return self

    def execute(self):
        return FakeResponse(self._data)


class FakeClient:
    def __init__(self, data=None, sections_data=None):
        self._data = data
        self._sections_data = sections_data if sections_data is not None else data

    def table(self, name):
        if name == "sections":
            return FakeQuery(self._sections_data)
        return FakeQuery(self._data)


def test_fetch_paper_returns_none_for_unknown_id():
    client = FakeClient(data=None)  # maybe_single → None
    paper, section_ids = emo._fetch_paper(client, "9999.99999")
    assert paper is None
    assert section_ids == []


def test_fetch_paper_returns_sections_when_found():
    client = FakeClient(
        data={"id": "p1", "arxiv_id": "1234.5678", "title": "T"},
        sections_data=[
            {"id": "s1", "title": "Intro", "paper_id": "p1"},
            {"id": "s2", "title": "Methods", "paper_id": "p1"},
        ]
    )
    paper, section_ids = emo._fetch_paper(client, "1234.5678")
    assert paper["id"] == "p1"
    assert section_ids == ["s1", "s2"]


def test_fetch_section_returns_none_for_unknown_id():
    client = FakeClient(data=None)
    section = emo._fetch_section(client, "unknown-uuid")
    assert section is None


def test_fetch_section_returns_section_when_found():
    client = FakeClient(data={"id": "s1", "title": "Intro", "paper_id": "p1"})
    section = emo._fetch_section(client, "s1")
    assert section["id"] == "s1"
    assert section["title"] == "Intro"
