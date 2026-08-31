"""LaTeX macro expansion.

Papers define their own shorthands — \\newcommand, \\def, xparse, mathtools —
almost always in the preamble. Anything left unexpanded reaches the database as
a raw control sequence and cannot be rendered by KaTeX, so this module has to
cover the definition forms real papers actually use.

Public entry point: `expand_custom_macros(body, *extra_sources)`.
"""

from __future__ import annotations

import re

# Recursion depth for macro bodies that use other macros. Real papers chain
# deeply — \providecommandordefault{\x}{\defaultx} -> \mathscr{x} inside an
# equation-defining macro already costs four levels — and a too-small cap
# silently leaves the innermost macro unexpanded. Bounded, so self-referential
# definitions still terminate.
_MAX_MACRO_PASSES = 12


def _match_braced(text: str, i: int) -> tuple[str, int] | None:
    r"""If text[i] is '{', return (inner_content, index_after_closing_brace).

    Counts nesting to arbitrary depth and honours backslash escapes, so macro
    bodies like {\deflink{a}{\mathcal{A}}} are captured whole. A regex cannot
    express this: the previous one-level pattern silently skipped any macro
    whose body nested deeper, leaving it unexpanded in the output.
    """
    if i >= len(text) or text[i] != "{":
        return None
    depth = 0
    j = i
    while j < len(text):
        c = text[j]
        if c == "\\":
            j += 2
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return text[i + 1:j], j + 1
        j += 1
    return None


# Commands that define other commands.
# A macro's signature is a tuple of (kind, default) pairs, mirroring xparse:
#   ("m", None)      mandatory argument
#   ("o", None)      optional [arg], empty when absent
#   ("O", default)   optional [arg] with a default
#   ("s", None)      optional * (star)
Spec = tuple[tuple[str, str | None], ...]

_NEWCOMMAND_CMDS = {"newcommand", "renewcommand", "providecommand"}
_OPERATOR_CMDS = {"DeclareMathOperator"}
# xparse — very common in modern papers, and previously unsupported entirely
_XPARSE_CMDS = {
    "NewDocumentCommand", "RenewDocumentCommand",
    "ProvideDocumentCommand", "DeclareDocumentCommand",
}
_PAIRED_DELIM_CMDS = {"DeclarePairedDelimiter"}
# mathtools, three different signatures — conflating them makes the parser
# over-read and swallow whatever definition follows:
#   \DeclarePairedDelimiter{\c}{l}{r}
#   \DeclarePairedDelimiterX{\c}[n]{l}{r}{body}
#   \DeclarePairedDelimiterXPP{\c}[n]{pre}{l}{r}{post}{body}
_PAIRED_DELIM_X_CMDS = {"DeclarePairedDelimiterX"}
_PAIRED_DELIM_XPP_CMDS = {"DeclarePairedDelimiterXPP"}
_DEF_CMDS = (
    _NEWCOMMAND_CMDS | _OPERATOR_CMDS | _XPARSE_CMDS
    | _PAIRED_DELIM_CMDS | _PAIRED_DELIM_X_CMDS | _PAIRED_DELIM_XPP_CMDS
    | {"def"}
)

# expl3 / LaTeX3 bodies (\seq_if_in:NnF, \tl_gset:Nn, \bool_if:NTF, …) are
# bookkeeping code — cross-reference registries and the like. They produce no
# typeset output, so expanding them to nothing (while still consuming their
# arguments) is both correct and far better than leaking \cfadd{def:affine}
# into a formula, where KaTeX would print the raw label.
_EXPL3_RE = re.compile(r"\\[a-zA-Z_]+:[a-zA-Z]+\b|\\[a-z]+_[a-z_]+:")

# LaTeX's own structural commands. Document classes and conference .sty files
# redefine these, and inlining a local .sty — which is required to pick up a
# paper's own math macros — brings those definitions into scope. Expanding them
# rewrites every \section{...} as \@startsection class internals, destroying the
# structure the section splitter depends on: 2608.27370 collapsed from 68
# sections to 1, with \maketitle's body injecting \@makefnmark into the prose.
# Definitions for these names are parsed and discarded, never registered.
_RESERVED_NAMES = frozenset({
    # sectioning
    "part", "chapter", "section", "subsection", "subsubsection",
    "paragraph", "subparagraph", "appendix",
    # title block
    "title", "author", "date", "maketitle", "thanks", "affiliation", "address",
    "institute", "email",
    # cross-references and bibliography
    "cite", "citep", "citet", "citealp", "citeauthor", "citeyear",
    "ref", "eqref", "cref", "Cref", "autoref", "pageref", "label",
    "bibliography", "bibliographystyle", "bibitem", "footnote", "footnotemark",
    # structure the parser keys on
    "begin", "end", "item", "caption", "includegraphics", "input", "include",
    "newtheorem", "documentclass", "usepackage",
})

_CS_RE = re.compile(r"\\([a-zA-Z]+)\*?")
_MACRO_NAME_RE = re.compile(r"\s*(?:\{\s*(\\[a-zA-Z]+)\s*\}|(\\[a-zA-Z]+))")
_ARITY_RE = re.compile(r"\s*\[\s*(\d)\s*\]")
_DEF_PARAMS_RE = re.compile(r"\s*((?:#\d)*)\s*(?=\{)")
# A single-token argument is one character — unless it is a control
# sequence, in which case the whole \name is the argument (\frac\alpha\beta).
_ARG_TOKEN_RE = re.compile(r"\s*(\\[a-zA-Z]+|\\.|[^\\$}&%#\\s])")


def _skip_ws(text: str, pos: int) -> int:
    while pos < len(text) and text[pos] in " \t\r\n":
        pos += 1
    return pos


def _match_bracketed(text: str, i: int) -> tuple[str, int] | None:
    """If text[i] is '[', return (inner_content, index_after_closing_bracket)."""
    if i >= len(text) or text[i] != "[":
        return None
    depth = 0
    j = i
    while j < len(text):
        c = text[j]
        if c == "\\":
            j += 2
            continue
        if c == "[":
            depth += 1
        elif c == "]":
            depth -= 1
            if depth == 0:
                return text[i + 1:j], j + 1
        j += 1
    return None


def _read_macro_arg(text: str, pos: int) -> tuple[str, int] | None:
    """Read one mandatory argument: a braced group (any depth) or a single token."""
    pos = _skip_ws(text, pos)
    braced = _match_braced(text, pos)
    if braced is not None:
        return braced
    m = _ARG_TOKEN_RE.match(text, pos)
    return (m.group(1), m.end()) if m else None


def _parse_xparse_spec(spec: str) -> Spec | None:
    """Translate an xparse argument specification into a Spec tuple.

    Returns None for specifiers this expander does not model (r, d, e, t, …) so
    the caller leaves such macros alone rather than expanding them incorrectly.
    """
    out: list[tuple[str, str | None]] = []
    i = 0
    while i < len(spec):
        c = spec[i]
        if c in " \t\r\n+!":      # `+` (long) and `!` (no-space) are modifiers
            i += 1
            continue
        if c in "ms":
            out.append((c, None))
            i += 1
        elif c == "o":
            out.append(("o", None))
            i += 1
        elif c == "O":
            got = _match_braced(spec, i + 1)
            if got is None:
                return None
            out.append(("O", got[0]))
            i = got[1]
        else:
            return None
        if len(out) > 9:          # #1..#9 is all LaTeX supports
            return None
    return tuple(out)


_HASH_ARG_RE = re.compile(r"#(\d)")


def _shift_arg_numbers(body: str, offset: int) -> str:
    """Renumber #1..#9 by `offset`, for specs with leading star/optional slots."""
    return _HASH_ARG_RE.sub(lambda m: f"#{int(m.group(1)) + offset}", body)


def _parse_definition(
    text: str, pos: int, kind: str
) -> tuple[str, Spec, str, int] | None:
    r"""Parse a definition starting just after the defining command's name.

    Returns (macro_name, spec, body, index_after_definition), or None when the
    construct does not parse — in which case the caller emits it verbatim rather
    than guessing.
    """
    nm = _MACRO_NAME_RE.match(text, pos)
    if not nm:
        return None
    name = nm.group(1) or nm.group(2)
    pos = nm.end()
    spec: Spec = ()

    if kind in _NEWCOMMAND_CMDS:
        am = _ARITY_RE.match(text, pos)
        if am:
            arity = int(am.group(1))
            pos = am.end()
            # \newcommand{\x}[2][default]{...} — first argument is optional
            default = _match_bracketed(text, pos)
            if default is not None:
                spec = (("O", default[0]),) + (("m", None),) * (arity - 1)
                pos = default[1]
            else:
                spec = (("m", None),) * arity

    elif kind in _XPARSE_CMDS:
        raw = _match_braced(text, _skip_ws(text, pos))
        if raw is None:
            return None
        parsed = _parse_xparse_spec(raw[0])
        if parsed is None:
            return None
        spec, pos = parsed, raw[1]

    elif kind in _PAIRED_DELIM_CMDS:
        # \DeclarePairedDelimiter\abs{\lvert}{\rvert} → \abs*[size]{x}
        left = _match_braced(text, _skip_ws(text, pos))
        if left is None:
            return None
        right = _match_braced(text, _skip_ws(text, left[1]))
        if right is None:
            return None
        # Always emit \left…\right: KaTeX sizes it correctly and the star/size
        # variants only differ in manual sizing.
        body = rf"\left{left[0]} #3 \right{right[0]}"
        return name, (("s", None), ("o", None), ("m", None)), body, right[1]

    elif kind in _PAIRED_DELIM_X_CMDS:
        # \DeclarePairedDelimiterX\expbr[1]{[}{]}{body}
        am = _ARITY_RE.match(text, pos)
        nargs = int(am.group(1)) if am else 0
        if am:
            pos = am.end()
        parts: list[str] = []
        for _ in range(3):          # left, right, body
            got = _read_macro_arg(text, pos)
            if got is None:
                return None
            parts.append(got[0])
            pos = got[1]
        left, right, inner = parts
        body = f"\\left{left} {_shift_arg_numbers(inner, 2)} \\right{right}"
        spec = (("s", None), ("o", None)) + (("m", None),) * nargs
        return name, spec, body, pos

    elif kind in _PAIRED_DELIM_XPP_CMDS:
        # \DeclarePairedDelimiterXPP\Pnorm[2]{pre}\lVert\rVert{post}{body}
        # Used as \Pnorm*[size]{arg1}{arg2}; star and size only affect manual
        # sizing, so \left…\right covers every variant.
        am = _ARITY_RE.match(text, pos)
        nargs = int(am.group(1)) if am else 0
        if am:
            pos = am.end()
        groups: list[str] = []
        for _ in range(4):          # pre, left, right, post
            got = _read_macro_arg(text, pos)
            if got is None:
                return None
            groups.append(got[0])
            pos = got[1]
        got = _read_macro_arg(text, pos)   # body
        if got is None:
            return None
        pre, left, right, post = groups
        body = (
            f"{_shift_arg_numbers(pre, 2)}\\left{left} {_shift_arg_numbers(got[0], 2)} "
            f"\\right{right}{_shift_arg_numbers(post, 2)}"
        )
        spec = (("s", None), ("o", None)) + (("m", None),) * nargs
        return name, spec, body, got[1]

    elif kind == "def":
        pm = _DEF_PARAMS_RE.match(text, pos)
        if pm is None:
            return None       # delimited-parameter \def — too exotic to model
        spec = (("m", None),) * (len(pm.group(1)) // 2)
        pos = pm.end()

    body = _match_braced(text, _skip_ws(text, pos))
    if body is None:
        return None
    content, after = body
    if kind in _OPERATOR_CMDS:
        content = rf"\operatorname{{{content}}}"
    elif _EXPL3_RE.search(content):
        content = ""
    return name, spec, content, after


def _read_args(text: str, pos: int, spec: Spec) -> tuple[list[str], int] | None:
    """Read the arguments described by `spec`. Returns None if a required one is absent."""
    args: list[str] = []
    for kind, default in spec:
        if kind == "s":
            p = _skip_ws(text, pos)
            if p < len(text) and text[p] == "*":
                args.append("*")
                pos = p + 1
            else:
                args.append("")
        elif kind in ("o", "O"):
            got = _match_bracketed(text, _skip_ws(text, pos))
            if got is None:
                args.append(default or "")
            else:
                args.append(got[0])
                pos = got[1]
        else:
            got = _read_macro_arg(text, pos)
            if got is None:
                return None
            args.append(got[0])
            pos = got[1]
    return args, pos


def _expand_stream(
    text: str, macros: dict[str, tuple[Spec, str]], depth: int = 0
) -> str:
    r"""Expand macro uses in `text` left-to-right, updating `macros` as it goes.

    Definitions take effect from the point they appear, which is what LaTeX does
    and what a global "collect everything first" pass cannot reproduce. Papers
    redefine the same shorthand per chapter — 2310.20360 defines \x as arity-0
    in one chapter and arity-1 in the next — so a single global meaning corrupts
    every chapter but one. Definitions are consumed, not emitted; their only
    purpose is to populate `macros`.
    """
    out: list[str] = []
    pos = 0
    while True:
        m = _CS_RE.search(text, pos)
        if m is None:
            out.append(text[pos:])
            break
        out.append(text[pos:m.start()])
        name = m.group(1)

        if name in _DEF_CMDS:
            parsed = _parse_definition(text, m.end(), name)
            if parsed is not None:
                mname, spec, body, after = parsed
                # \providecommand only defines when the name is still free.
                reserved = mname.lstrip("\\") in _RESERVED_NAMES
                if not reserved and not (name == "providecommand" and mname in macros):
                    macros[mname] = (spec, body)
                pos = after
                continue
            out.append(m.group(0))
            pos = m.end()
            continue

        entry = macros.get("\\" + name)
        if entry is None:
            out.append(m.group(0))
            pos = m.end()
            continue

        spec, body = entry
        read = _read_args(text, m.end(), spec)
        if read is None:
            out.append(m.group(0))     # arguments missing — leave the use alone
            pos = m.end()
            continue
        args, argpos = read
        for i, a in enumerate(args, 1):
            body = body.replace(f"#{i}", a)
        # A body may itself use (or define) macros — e.g. wrappers such as
        # \providecommandordefault{\f}{\cE}, which expand into two definitions.
        if depth < _MAX_MACRO_PASSES:
            body = _expand_stream(body, macros, depth + 1)
        out.append(body)
        pos = argpos

    return "".join(out)


# A "%" starts a comment unless it is escaped. An unstripped comment breaks
# brace counting outright — "% }" reads as a closing brace that is not there —
# and comment text leaks into macro bodies. The newline is kept so that line
# positions (and therefore section splitting) are unaffected.
_TEX_COMMENT_RE = re.compile(r"(?<!\\)((?:\\\\)*)%[^\n]*")


def _strip_tex_comments(text: str) -> str:
    return _TEX_COMMENT_RE.sub(r"\1", text)


def expand_custom_macros(latex_doc: str, *extra_sources: str) -> str:
    r"""Expand macros defined in the document and in any `extra_sources`.

    `extra_sources` carries the preamble, where papers define the vast majority
    of their macros. The preamble is stripped from the body before parsing, so
    without this its definitions are invisible and macros such as \altpoint or
    \Aff leak unexpanded into the database, where they cannot be rendered.
    """
    macros: dict[str, tuple[Spec, str]] = {}
    for src in extra_sources:
        if src:
            # definitions only; output discarded
            _expand_stream(_strip_tex_comments(src), macros)
    return _expand_stream(_strip_tex_comments(latex_doc), macros)
