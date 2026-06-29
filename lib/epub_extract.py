"""EPUB text + title extraction.

Mirrors lib/pdf_extract.py but for .epub files.
Uses ebooklib to read the epub container and BeautifulSoup to strip HTML.

Usage:
    from lib.epub_extract import extract_paper_from_epub
    paper = extract_paper_from_epub(Path("book.epub"))
    # paper.title, paper.text are populated; paper.sections remains empty.
"""

from __future__ import annotations

import re
from pathlib import Path

from lib.models import Paper
from lib.text_clean import clean_pdf_text


def extract_paper_from_epub(epub_path: Path) -> Paper:
    """Extract title and full text from an epub file.

    Returns a Paper with .title and .text populated.
    .sections is empty (no structure-aware parsing for epub).
    """
    try:
        import ebooklib  # type: ignore[import]
        from ebooklib import epub as ebooklib_epub
    except ImportError as exc:
        raise ImportError(
            "ebooklib is required for epub support. "
            "Install it with: pip install ebooklib beautifulsoup4"
        ) from exc

    try:
        from bs4 import BeautifulSoup  # type: ignore[import]
    except ImportError as exc:
        raise ImportError(
            "beautifulsoup4 is required for epub support. "
            "Install it with: pip install ebooklib beautifulsoup4"
        ) from exc

    book = ebooklib_epub.read_epub(str(epub_path), options={"ignore_ncx": True})

    # ── Title ──────────────────────────────────────────────────────────────
    title = _extract_title(book, epub_path)

    # ── Text ───────────────────────────────────────────────────────────────
    chapter_texts: list[str] = []
    for item in book.get_items_of_type(ebooklib.ITEM_DOCUMENT):
        html_bytes = item.get_content()
        if not html_bytes:
            continue
        soup = BeautifulSoup(html_bytes, "html.parser")
        # Remove script/style noise
        for tag in soup(["script", "style", "head"]):
            tag.decompose()
        text = soup.get_text(separator="\n")
        text = _collapse_blank_lines(text)
        if text.strip():
            chapter_texts.append(text)

    raw_text = "\n\n".join(chapter_texts)
    cleaned = clean_pdf_text(raw_text)

    return Paper(
        title=title,
        text=cleaned,
        pdf_path=epub_path,
        source_type="epub",
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _extract_title(book: object, epub_path: Path) -> str:
    """Return the best available title string from epub metadata."""
    # Dublin Core title (standard epub metadata)
    try:
        dc_titles = book.get_metadata("DC", "title")  # type: ignore[attr-defined]
        if dc_titles:
            raw = dc_titles[0][0] if isinstance(dc_titles[0], (list, tuple)) else dc_titles[0]
            title = str(raw).strip()
            if title:
                return title
    except Exception:
        pass

    # Fallback: stem of the filename
    return epub_path.stem.replace("_", " ").replace("-", " ").title()


_MULTI_BLANK_RE = re.compile(r"\n{3,}")


def _collapse_blank_lines(text: str) -> str:
    """Reduce runs of 3+ blank lines to 2."""
    return _MULTI_BLANK_RE.sub("\n\n", text)
