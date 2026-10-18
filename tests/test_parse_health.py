"""Post-parse sanity checks.

Each case is drawn from the corrupted 2608.27370 parse, which reported
"Processed 1/1 (errors=0)" while collapsing 68 sections into one 177k-char
blob of class internals.
"""
from lib.models import Section
from lib.parse_health import blocking, check_parse_health


def _section(idx: int = 0, title: str = "S", text: str = "body text") -> Section:
    return Section(order_idx=idx, title=title, plain_text=text, raw_latex="")


SOURCE_WITH_SIX = r"""
\section{One}\section{Two}\section{Three}
\section{Four}\section{Five}\section{Six}
"""


def test_healthy_parse_reports_nothing():
    sections = tuple(_section(i, f"S{i}") for i in range(6))
    assert check_parse_health(sections, SOURCE_WITH_SIX) == ()


def test_collapse_to_one_section_is_an_error():
    problems = check_parse_health((_section(0, "Abstract"),), SOURCE_WITH_SIX)
    codes = [p.code for p in problems]
    assert "section_collapse" in codes
    assert blocking(problems)


def test_no_sections_at_all_is_an_error():
    problems = check_parse_health((), SOURCE_WITH_SIX)
    assert [p.code for p in problems] == ["no_sections"]
    assert blocking(problems)


def test_pervasive_class_internals_are_an_error():
    bad = tuple(_section(i, text=r"\@makefnmark to 0pt $^{\@thefnmark}$") for i in range(6))
    problems = check_parse_health(bad, SOURCE_WITH_SIX)
    assert any(p.code == "class_internals" and p.severity == "error" for p in problems)
    assert blocking(problems)


def test_a_stray_internal_in_one_section_is_only_a_warning():
    # Real parses do this: \@mainmatterfalse in a preamble section,
    # \@setsize in an acknowledgements block. Not corruption.
    sections = (_section(0, "Preamble", r"\@mainmatterfalse"),) + tuple(
        _section(i) for i in range(1, 20)
    )
    problems = check_parse_health(sections, SOURCE_WITH_SIX)
    assert any(p.code == "class_internals" and p.severity == "warning" for p in problems)
    assert not blocking(problems)


def test_internals_inside_a_huge_section_are_an_error():
    bad = _section(0, "Abstract", r"\@makefnmark " + "x" * 130_000)
    sections = (bad,) + tuple(_section(i) for i in range(1, 20))
    problems = check_parse_health(sections, SOURCE_WITH_SIX)
    assert any(p.code == "class_internals" and p.severity == "error" for p in problems)


def test_class_internals_are_reported_once_not_per_section():
    bad = tuple(_section(i, text=r"\@startsection junk") for i in range(6))
    problems = check_parse_health(bad, SOURCE_WITH_SIX)
    assert sum(1 for p in problems if p.code == "class_internals") == 1


def test_an_ordinary_backslash_command_is_not_an_internal():
    ok = tuple(_section(i, text=r"uses \alpha and \mathbb{R} normally") for i in range(6))
    assert check_parse_health(ok, SOURCE_WITH_SIX) == ()


def test_a_short_paper_is_not_flagged_for_collapse():
    # Two sectioning commands legitimately yield one merged section.
    assert check_parse_health((_section(),), r"\section{A}\section{B}") == ()


def test_a_huge_section_is_only_a_warning():
    huge = _section(0, "Everything", "x" * 130_000)
    problems = check_parse_health((huge,) + tuple(_section(i) for i in range(1, 6)), SOURCE_WITH_SIX)
    assert any(p.code == "huge_section" and p.severity == "warning" for p in problems)
    assert not any(p.code == "huge_section" for p in blocking(problems))


def test_partial_recovery_above_the_ratio_passes():
    # 3 of 6 recovered is degraded but not a collapse.
    sections = tuple(_section(i) for i in range(3))
    assert not any(p.code == "section_collapse" for p in check_parse_health(sections, SOURCE_WITH_SIX))


def test_problem_renders_readably():
    problems = check_parse_health((), SOURCE_WITH_SIX)
    assert str(problems[0]).startswith("[ERROR] no_sections:")
