"""Title and author names for arXiv papers, from the arXiv Atom API.

The API accepts many ids per request, so a backfill over every paper needs a
handful of calls rather than one per paper.
"""
from __future__ import annotations

import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass

_API_URL = "https://export.arxiv.org/api/query"
_NS = {"a": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}
_TIMEOUT_S = 15
# arXiv asks clients to keep id_list requests modest.
MAX_IDS_PER_REQUEST = 50


@dataclass(frozen=True)
class ArxivMetadata:
    title: str
    authors: tuple[str, ...]
    # Only present when the submitter entered them; LaTeX is the main source.
    affiliations: tuple[str, ...] = ()


def _squash(text: str | None) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def _unversioned_id(entry_id: str) -> str:
    """'http://arxiv.org/abs/2603.04735v2' -> '2603.04735'."""
    tail = entry_id.rstrip("/").split("/abs/")[-1]
    return re.sub(r"v\d+$", "", tail)


def parse_atom_feed(xml_text: str) -> dict[str, ArxivMetadata]:
    """Map unversioned arXiv id -> metadata for every entry in an Atom feed."""
    root = ET.fromstring(xml_text)
    out: dict[str, ArxivMetadata] = {}
    for entry in root.findall("a:entry", _NS):
        entry_id = _squash(entry.findtext("a:id", default="", namespaces=_NS))
        title = _squash(entry.findtext("a:title", default="", namespaces=_NS))
        if not entry_id or not title:
            continue
        authors = tuple(
            name for name in (
                _squash(a.findtext("a:name", default="", namespaces=_NS))
                for a in entry.findall("a:author", _NS)
            ) if name
        )
        affiliations = tuple(dict.fromkeys(
            name for name in (
                _squash(el.text) for el in entry.findall("a:author/arxiv:affiliation", _NS)
            ) if name
        ))
        out[_unversioned_id(entry_id)] = ArxivMetadata(
            title=title, authors=authors, affiliations=affiliations
        )
    return out


def fetch_arxiv_metadata(arxiv_ids: list[str]) -> dict[str, ArxivMetadata]:
    """Fetch metadata for up to MAX_IDS_PER_REQUEST ids in one API call."""
    if len(arxiv_ids) > MAX_IDS_PER_REQUEST:
        raise ValueError(f"at most {MAX_IDS_PER_REQUEST} ids per request")
    query = urllib.parse.urlencode(
        {"id_list": ",".join(arxiv_ids), "max_results": len(arxiv_ids)}
    )
    req = urllib.request.Request(f"{_API_URL}?{query}", headers={"User-Agent": "paper2md/1.0"})
    with urllib.request.urlopen(req, timeout=_TIMEOUT_S) as r:
        return parse_atom_feed(r.read().decode())
