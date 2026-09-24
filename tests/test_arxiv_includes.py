"""Tests for comment-aware \\input/\\include resolution in lib/arxiv_source.py.

Regression cover for arXiv 2412.05265, whose main file contains both

    %\\input{code}
    ...
    \\input{code}

Resolving the commented directive inlined code.tex twice — once at the top of
the document — and the orphaned "%" then commented out the included file's own
first line, producing a phantom "Implementation details" section at order_idx 0.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from lib.arxiv_source import _resolve_includes


@pytest.fixture
def tex_dir(tmp_path: Path) -> Path:
    (tmp_path / "code.tex").write_text("\\section{Implementation details}\nCode chapter body.\n")
    (tmp_path / "intro.tex").write_text("\\section{Introduction}\nIntro body.\n")
    return tmp_path


def test_resolves_a_real_input(tex_dir: Path):
    out = _resolve_includes("\\input{intro}", tex_dir)
    assert "Intro body." in out


def test_does_not_resolve_a_commented_input(tex_dir: Path):
    out = _resolve_includes("%\\input{code}\n\\input{intro}", tex_dir)
    assert "Code chapter body." not in out
    assert "Intro body." in out


def test_file_is_inlined_exactly_once_when_also_commented(tex_dir: Path):
    # The 2412.05265 shape: commented directive first, real one later.
    out = _resolve_includes("%\\input{code}\n\\input{intro}\n\\input{code}", tex_dir)
    assert out.count("Code chapter body.") == 1


def test_included_file_first_line_is_not_swallowed_by_a_stray_percent(tex_dir: Path):
    out = _resolve_includes("%\\input{code}\n\\input{code}", tex_dir)
    assert "%\\section{Implementation details}" not in out
    assert "\\section{Implementation details}" in out


def test_commented_input_after_real_content_on_the_same_line(tex_dir: Path):
    out = _resolve_includes("\\input{intro} % \\input{code}", tex_dir)
    assert "Intro body." in out
    assert "Code chapter body." not in out


def test_escaped_percent_does_not_start_a_comment(tex_dir: Path):
    out = _resolve_includes("100\\% sure\n\\input{intro}", tex_dir)
    assert "Intro body." in out
    assert "100\\%" in out


def test_percent_inside_minted_survives(tex_dir: Path):
    src = (
        "\\begin{minted}{python}\n"
        "pct = 5 % 2   # modulo, not a comment\n"
        "\\end{minted}\n"
        "\\input{intro}"
    )
    out = _resolve_includes(src, tex_dir)
    assert "pct = 5 % 2   # modulo, not a comment" in out
    assert "Intro body." in out


def test_missing_file_leaves_the_directive_untouched(tex_dir: Path):
    out = _resolve_includes("\\input{nope}", tex_dir)
    assert "\\input{nope}" in out
