r"""Extract author affiliations (organisations, labs, teams) from LaTeX source.

Search matches these so a query such as "google deepmind" finds a paper by
where its authors work. Templates spell affiliations differently:

  \icmlaffiliation{key}{Name}      ICML — the first argument is a label
  \affiliation[1]{Name}            revtex, many journal classes
  \affil[1]{Name}                  authblk, Springer (\orgname{...} inside)
  \institute{A \and B}             LNCS

Each affiliation keeps every detail the paper gives — department or team,
organisation, city, country — so search can match any of them. Emails and
street addresses are dropped: they are personal or noise, not search terms.

Papers that only mark affiliations with superscripts inside \author{...} are
not covered: there is no reliable way to tell a name from an organisation.
"""
from __future__ import annotations

import re

from lib.latex_macros import _match_bracketed, _match_braced, _skip_ws
from lib.latex_outline import strip_comments

# Big author lists (collaborations) can name hundreds of institutes; beyond
# this many the extra rows add nothing to search.
MAX_AFFILIATIONS = 25
# Longer than this is a paragraph that leaked in, not an affiliation.
MAX_AFFILIATION_CHARS = 300

_CMD_RE = re.compile(r"\\(icmlaffiliation|affiliation|affil|institute)(?![A-Za-z@])")
# Structured classes (Springer sn-jnl, acmart) put each part in its own
# command; \street and \postcode are deliberately not listed.
_FIELD_RE = re.compile(
    r"\\(?:orgdiv|orgname|institution|department|city|state|country)\s*\{([^{}]*)\}"
)
_SUPERSCRIPT_RE = re.compile(r"\\textsuperscript\s*\{[^{}]*\}|\$[^$]*\$")
_UNWRAP_RE = re.compile(r"\\[A-Za-z@]+\*?\s*\{([^{}]*)\}")
_CS_RE = re.compile(r"\\[A-Za-z@]+\*?")
_LINE_BREAK_RE = re.compile(r"\\\\(?:\[[^\]]*\])?")


def _command_argument(src: str, name: str, after: int) -> str | None:
    """Return the argument that holds the organisation for one command use."""
    pos = _skip_ws(src, after)
    opt = _match_bracketed(src, pos)
    if opt:
        pos = _skip_ws(src, opt[1])
    arg = _match_braced(src, pos)
    if arg and name == "icmlaffiliation":
        arg = _match_braced(src, _skip_ws(src, arg[1]))
    return arg[0] if arg else None


def _clean_line(raw: str) -> str:
    text = "; ".join(p for p in raw.split(";") if "@" not in p)
    text = _SUPERSCRIPT_RE.sub("", text)
    for _ in range(3):  # unwrap \textit{\textbf{X}} from the inside out
        text = _UNWRAP_RE.sub(r"\1", text)
    text = _CS_RE.sub(" ", text).replace("~", " ").replace("{", "").replace("}", "")
    return re.sub(r"\s+", " ", text).strip(" ,.;:")


def _clean(raw: str) -> str:
    """Join an affiliation's lines (\\\\ breaks) into one; _clean_line drops emails."""
    lines = (_clean_line(line) for line in _LINE_BREAK_RE.split(raw))
    return ", ".join(line for line in lines if line)


def _candidates(arg: str) -> list[str]:
    fields = [f.strip() for f in _FIELD_RE.findall(arg) if f.strip()]
    if fields:
        return [_clean(", ".join(fields))]
    return [_clean(p) for p in re.split(r"\\and(?![A-Za-z@])", arg)]


def _is_affiliation(name: str) -> bool:
    return bool(name) and len(name) <= MAX_AFFILIATION_CHARS and bool(re.search(r"[A-Za-z]", name))


def merge_affiliations(*groups: tuple[str, ...] | list[str]) -> tuple[str, ...]:
    """Concatenate affiliation lists, keeping order and dropping duplicates
    (case- and whitespace-insensitive), capped at MAX_AFFILIATIONS."""
    found: list[str] = []
    seen: set[str] = set()
    for name in (n for group in groups for n in group):
        key = re.sub(r"\s+", " ", name).strip().casefold()
        if key in seen or not _is_affiliation(name):
            continue
        seen.add(key)
        found.append(name)
        if len(found) >= MAX_AFFILIATIONS:
            break
    return tuple(found)


def extract_affiliations(latex_source: str) -> tuple[str, ...]:
    """Return the distinct affiliations named in `latex_source`, in order."""
    src = strip_comments(latex_source or "")
    names: list[str] = []
    for m in _CMD_RE.finditer(src):
        arg = _command_argument(src, m.group(1), m.end())
        if arg is None or "#" in arg:  # \newcommand bodies, not uses
            continue
        names.extend(_candidates(arg))
    return merge_affiliations(names)
