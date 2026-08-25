import importlib.util
from pathlib import Path

MODULE_PATH = Path(__file__).parent.parent / "lib" / "math_block_selection.py"
spec = importlib.util.spec_from_file_location("math_block_selection", MODULE_PATH)
mbs = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mbs)
prioritize_and_cap = mbs.prioritize_and_cap


def _row(i, env, sec="s1"):
    return {"id": str(i), "env_type": env, "sections": {"id": sec}}


def test_named_envs_sort_before_inline():
    rows = [_row(1, "inline"), _row(2, "equation"), _row(3, "inline")]
    out = prioritize_and_cap(rows, max_blocks=10)
    assert [r["id"] for r in out] == ["2", "1", "3"]


def test_per_section_cap_applies_to_named_and_inline_separately():
    # Arrange: 2 named + 2 inline in section s1, 1 named in s2
    rows = [
        _row(1, "equation"), _row(2, "align"), _row(3, "equation", sec="s2"),
        _row(4, "inline"), _row(5, "inline"),
    ]

    # Act: Apply per-section cap of 1
    out = prioritize_and_cap(rows, max_blocks=100, max_blocks_per_section=1)

    # Assert: 1 named + 1 inline per section, so: 1 from s1 named, 1 from s1 inline, 1 from s2
    s1_named = [r for r in out if r["sections"]["id"] == "s1" and r["env_type"] != "inline"]
    s1_inline = [r for r in out if r["sections"]["id"] == "s1" and r["env_type"] == "inline"]
    s2_named = [r for r in out if r["sections"]["id"] == "s2" and r["env_type"] != "inline"]

    assert len(s1_named) == 1, f"Expected 1 named block in s1, got {len(s1_named)}"
    assert len(s1_inline) == 1, f"Expected 1 inline block in s1, got {len(s1_inline)}"
    assert len(s2_named) == 1, f"Expected 1 named block in s2, got {len(s2_named)}"
    assert len(out) == 3


def test_global_cap_applies_last():
    rows = [_row(i, "equation") for i in range(10)]
    out = prioritize_and_cap(rows, max_blocks=3)
    assert len(out) == 3


def test_rows_missing_sections_are_dropped():
    rows = [{"id": "x", "env_type": "equation", "sections": None}, _row(1, "equation")]
    out = prioritize_and_cap(rows, max_blocks=10)
    assert [r["id"] for r in out] == ["1"]
