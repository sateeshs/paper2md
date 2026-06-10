"""ArXiv source acquisition: download tar.gz, unpack, find + merge main .tex.

Flow:
  1. GET https://arxiv.org/src/{arxiv_id}  → tar.gz or single .gz file
  2. Unpack into a temp directory
  3. Find the main .tex file (the one containing \documentclass)
  4. Recursively resolve \input{} and \include{} directives
  5. Return merged LaTeX source as a single string

Falls back gracefully: returns None if no source is available (PDF-only papers).
"""

from __future__ import annotations

import re
import tarfile
import tempfile
import time
from io import BytesIO
from pathlib import Path

import httpx


# ArXiv source URL pattern
_SOURCE_URL = "https://arxiv.org/src/{arxiv_id}"

# Retry config
_MAX_RETRIES = 2
_RETRY_SLEEP = 30  # seconds — respect ArXiv servers

# Max depth for \input{} resolution (avoid infinite loops)
_MAX_INCLUDE_DEPTH = 5

# Patterns for includes
_INPUT_RE = re.compile(
    r"\\(?:input|include)\{([^}]+)\}",
    re.MULTILINE,
)


# ---------------------------------------------------------------------------
# Download
# ---------------------------------------------------------------------------

def _download_source(arxiv_id: str) -> bytes | None:
    """Download the ArXiv source tarball. Returns raw bytes or None if unavailable."""
    url = _SOURCE_URL.format(arxiv_id=arxiv_id)

    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            resp = httpx.get(url, follow_redirects=True, timeout=60)
            if resp.status_code == 200:
                return resp.content
            if resp.status_code == 404:
                return None   # PDF-only paper — no source available
            if resp.status_code == 429:
                if attempt < _MAX_RETRIES:
                    time.sleep(_RETRY_SLEEP)
                    continue
                return None
            # Other error
            return None
        except httpx.RequestError:
            if attempt < _MAX_RETRIES:
                time.sleep(5)
            continue

    return None


# ---------------------------------------------------------------------------
# Unpack
# ---------------------------------------------------------------------------

def _unpack_to_temp(raw: bytes) -> Path:
    """Unpack tar.gz (or single .gz) bytes into a new temp directory.

    Returns the temp directory Path. Caller is responsible for cleanup.
    """
    tmp = Path(tempfile.mkdtemp(prefix="paper2md_arxiv_"))

    try:
        # Try as tar archive first
        with tarfile.open(fileobj=BytesIO(raw)) as tf:
            # Safety: strip any absolute paths
            safe_members = [
                m for m in tf.getmembers()
                if not m.name.startswith("/") and ".." not in m.name
            ]
            tf.extractall(tmp, members=safe_members)
        return tmp
    except tarfile.TarError:
        pass

    # Single .gz file (some old ArXiv papers are just gzipped .tex)
    try:
        import gzip
        content = gzip.decompress(raw)
        (tmp / "main.tex").write_bytes(content)
        return tmp
    except Exception:
        pass

    # Last resort: write raw as-is and hope it's plain .tex
    (tmp / "main.tex").write_bytes(raw)
    return tmp


# ---------------------------------------------------------------------------
# Find main .tex
# ---------------------------------------------------------------------------

def _find_main_tex(tex_dir: Path) -> Path | None:
    """Find the main .tex file: the one containing \\documentclass.

    Strategy:
      1. Among files with \\documentclass, prefer 'main.tex'
      2. If tie, prefer the largest file
      3. If no \\documentclass found at all, fall back to largest .tex file
    """
    tex_files = list(tex_dir.rglob("*.tex"))
    if not tex_files:
        return None

    candidates: list[Path] = []
    for f in tex_files:
        try:
            content = _read_tex_file(f)
            if r"\documentclass" in content:
                candidates.append(f)
        except OSError:
            continue

    if not candidates:
        # No \documentclass found — return largest .tex file
        return max(tex_files, key=lambda f: f.stat().st_size)

    if len(candidates) == 1:
        return candidates[0]

    # Prefer files named 'main.tex' or 'paper.tex'
    for preferred in ("main.tex", "paper.tex", "manuscript.tex"):
        for c in candidates:
            if c.name.lower() == preferred:
                return c

    # Fall back to largest candidate
    return max(candidates, key=lambda f: f.stat().st_size)


# ---------------------------------------------------------------------------
# Read + encoding detection
# ---------------------------------------------------------------------------

def _read_tex_file(path: Path) -> str:
    """Read a .tex file, trying UTF-8 then latin-1."""
    raw = path.read_bytes()
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("latin-1", errors="replace")


# ---------------------------------------------------------------------------
# Resolve \input{} and \include{}
# ---------------------------------------------------------------------------

def _resolve_includes(content: str, base_dir: Path, depth: int = 0) -> str:
    """Recursively inline \\input{file} and \\include{file} directives.

    Args:
        content:  LaTeX source string to process.
        base_dir: Directory to resolve relative paths against.
        depth:    Current recursion depth (capped at _MAX_INCLUDE_DEPTH).
    """
    if depth >= _MAX_INCLUDE_DEPTH:
        return content

    def replacer(m: re.Match) -> str:
        ref = m.group(1).strip()
        # Add .tex extension if missing
        if not ref.endswith(".tex"):
            ref += ".tex"
        target = base_dir / ref
        if not target.exists():
            # Try searching subdirectories
            found = list(base_dir.rglob(ref))
            if not found:
                return m.group(0)  # leave directive unchanged
            target = found[0]
        try:
            sub_content = _read_tex_file(target)
            return _resolve_includes(sub_content, target.parent, depth + 1)
        except OSError:
            return m.group(0)

    return _INPUT_RE.sub(replacer, content)


# ---------------------------------------------------------------------------
# Strip preamble
# ---------------------------------------------------------------------------

def _strip_preamble(content: str) -> str:
    """Return only the content inside \\begin{document}...\\end{document}."""
    begin = content.find(r"\begin{document}")
    if begin == -1:
        return content   # no preamble marker — return as-is
    end = content.rfind(r"\end{document}")
    if end == -1:
        return content[begin + len(r"\begin{document}"):]
    return content[begin + len(r"\begin{document}"):end]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def fetch_arxiv_latex(arxiv_id: str) -> str | None:
    """
    Download and return the merged LaTeX source for an ArXiv paper.

    Returns:
        Merged LaTeX string (preamble stripped, includes inlined), or
        None if the paper has no LaTeX source (PDF-only submission).
    """
    result = fetch_arxiv_latex_full(arxiv_id)
    if result is None:
        return None
    return result[0]  # body only


def fetch_arxiv_latex_full(arxiv_id: str) -> tuple[str, str] | None:
    """
    Like fetch_arxiv_latex but returns (body, full_source) so callers
    can search the preamble (e.g. for \\title{}).

    Returns:
        (preamble_stripped_body, full_merged_source) or None.
    """
    raw = _download_source(arxiv_id)
    if raw is None:
        return None

    tmp_dir = _unpack_to_temp(raw)
    try:
        main_tex = _find_main_tex(tmp_dir)
        if main_tex is None:
            return None

        content = _read_tex_file(main_tex)
        content = _resolve_includes(content, main_tex.parent)
        full_source = content
        body = _strip_preamble(content).strip()
        return (body, full_source) if body else None
    finally:
        import shutil
        shutil.rmtree(tmp_dir, ignore_errors=True)
