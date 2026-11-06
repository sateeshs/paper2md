"""Titles and author names come from the arXiv Atom API, which (unlike the
LaTeX \\author block) lists every author as a clean name."""
from __future__ import annotations

from lib.arxiv_metadata import parse_atom_feed

FEED = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom" xmlns:arxiv="http://arxiv.org/schemas/atom">
  <entry>
    <id>http://arxiv.org/abs/2603.04735v2</id>
    <title>Solving an Open Problem
      using AI</title>
    <author><name>Ada Lovelace</name><arxiv:affiliation>Google Research</arxiv:affiliation></author>
    <author><name> Alan  Turing </name><arxiv:affiliation>Google Research</arxiv:affiliation></author>
  </entry>
  <entry>
    <id>http://arxiv.org/abs/2212.03796v1</id>
    <title>Quantum HMMs</title>
    <author><name>Grace Hopper</name></author>
  </entry>
</feed>"""


def test_feed_is_keyed_by_unversioned_id_with_clean_titles_and_authors():
    meta = parse_atom_feed(FEED)
    assert meta["2603.04735"].title == "Solving an Open Problem using AI"
    assert meta["2603.04735"].authors == ("Ada Lovelace", "Alan Turing")
    assert meta["2212.03796"].authors == ("Grace Hopper",)


def test_author_affiliations_from_the_api_are_collected_once():
    meta = parse_atom_feed(FEED)
    assert meta["2603.04735"].affiliations == ("Google Research",)
    assert meta["2212.03796"].affiliations == ()


def test_error_feed_without_entries_is_empty():
    assert parse_atom_feed('<feed xmlns="http://www.w3.org/2005/Atom"></feed>') == {}


def test_paper_row_carries_authors_and_affiliations():
    from lib.models import Paper
    from lib.supabase_push import _paper_row

    row = _paper_row(Paper(title="T", text="", arxiv_id="1", authors=("A", "B"),
                           affiliations=("Google DeepMind",)))
    assert row["authors"] == ["A", "B"]
    assert row["affiliations"] == ["Google DeepMind"]


def test_paper_row_does_not_wipe_metadata_it_could_not_fetch():
    from lib.models import Paper
    from lib.supabase_push import _paper_row

    row = _paper_row(Paper(title="T", text="", arxiv_id="1"))
    assert "authors" not in row and "affiliations" not in row
