"""Shared candidate selection for math explanation runs.

Used by explain_math_only.py; mirrors the priority rules MathExplainer
applies during initial processing (named envs before inline).
"""
from __future__ import annotations


def prioritize_and_cap(
    rows: list[dict],
    max_blocks: int,
    max_blocks_per_section: int | None = None,
) -> list[dict]:
    """Sort named-env blocks before inline, apply caps, drop orphan rows.

    Args:
        rows: List of math block rows with keys 'env_type' and 'sections.id'
        max_blocks: Global cap on total blocks returned
        max_blocks_per_section: Optional per-section cap (applies separately to named and inline)

    Returns:
        Filtered and sorted rows; orphans (missing sections) are dropped.
    """
    # Drop rows without valid section references
    rows = [r for r in rows if r.get("sections") and r["sections"].get("id")]

    def priority(r: dict) -> int:
        return 0 if r["env_type"] != "inline" else 1

    rows = sorted(rows, key=priority)

    if max_blocks_per_section:
        by_section: dict[str, list[dict]] = {}
        for r in rows:
            sec_id = r["sections"]["id"]
            by_section.setdefault(sec_id, []).append(r)
        capped: list[dict] = []
        for sec_rows in by_section.values():
            named = [r for r in sec_rows if r["env_type"] != "inline"]
            inline = [r for r in sec_rows if r["env_type"] == "inline"]
            capped.extend(named[:max_blocks_per_section])
            capped.extend(inline)  # no cap on inline
        rows = sorted(capped, key=priority)

    return rows[:max_blocks]
