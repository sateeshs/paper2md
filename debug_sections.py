#!/usr/bin/env python3
"""Debug section parsing for a specific ArXiv paper.

Usage:  python debug_sections.py 2606.11470
"""
import re
import sys
from lib.arxiv_source import fetch_arxiv_latex_full
from lib.latex_parse import _SECTION_RE, _split_sections, parse_latex_sections

arxiv_id = sys.argv[1] if len(sys.argv) > 1 else "2606.11470"
print(f"Fetching LaTeX source for {arxiv_id} …")

result = fetch_arxiv_latex_full(arxiv_id)
if result is None:
    print("ERROR: no LaTeX source found (PDF-only paper?)")
    sys.exit(1)

body, full_source = result
print(f"Body length: {len(body):,} chars\n")

# 1. Count raw \section / \chapter / \subsection occurrences
for cmd in (r"\chapter", r"\section", r"\subsection", r"\subsubsection"):
    count = len(re.findall(re.escape(cmd) + r"\b", body))
    print(f"  {cmd:<20} occurrences: {count}")

print()

# 2. Show all matches from _SECTION_RE (the splitter)
print("=== Sections matched by _SECTION_RE ===")
matches = list(_SECTION_RE.finditer(body))
if not matches:
    print("  (none)")
else:
    for m in matches:
        snippet = body[m.start():m.start()+80].replace("\n", "↵")
        print(f"  [{m.start():6d}] {snippet!r}")

print()

# 3. Show the raw split result
print("=== _split_sections() output ===")
raw = _split_sections(body)
for i, (title, bdy) in enumerate(raw):
    print(f"  [{i}] title={title!r:50s}  body_len={len(bdy):6,}")

print()

# 4. Show final parse_latex_sections() result
print("=== parse_latex_sections() final sections ===")
sections = parse_latex_sections(body)
for s in sections:
    print(f"  §{s.order_idx} {s.title!r:50s}  plain_len={len(s.plain_text or ''):5,}  math={len(s.math_blocks)}")

print(f"\nTotal sections kept: {len(sections)}")
