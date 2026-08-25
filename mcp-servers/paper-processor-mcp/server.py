"""paper-processor-mcp — MCP server for paper ingestion and explanation.

Wraps existing lib/ modules as MCP tools. No business logic lives here —
all calls delegate to summarize_papers.py and lib/*.py unchanged.

Tools:
  process_paper          [long_running] Full pipeline: fetch + parse + summarise + explain
  create_sections        Parse LaTeX into sections (no LLM calls)
  explain_section_math   Run MathExplainer on one section's math blocks
  explain_section_algorithms  Run AlgorithmExplainer on one section's algorithm blocks
  get_paper_status       Return current processing status from Supabase
"""

from __future__ import annotations

import asyncio
import dataclasses
import json
import logging
import os
import sys
from pathlib import Path

# Add repo root to path so lib/ imports resolve when running inside Modal
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from mcp.server.fastmcp import FastMCP

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

mcp = FastMCP("paper-processor-mcp")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ok(data: dict) -> list[dict]:
    """Wrap a result dict in MCP content format."""
    return [{"type": "text", "text": json.dumps(data, ensure_ascii=False)}]


def _err(message: str) -> list[dict]:
    return [{"type": "text", "text": json.dumps({"error": message})}]


# ---------------------------------------------------------------------------
# Tool: process_paper
# ---------------------------------------------------------------------------

@mcp.tool()
async def process_paper(arxiv_id: str, force: bool = False) -> list[dict]:
    """[long_running] Full pipeline: fetch ArXiv LaTeX, parse sections,
    run PaperSummarizer + MathExplainer + AlgorithmExplainer, push all results
    to Supabase. Returns section/math/algorithm counts. Takes 2–10 minutes."""
    from summarize_papers import process_arxiv_id

    logger.info("process_paper(%s, force=%s)", arxiv_id, force)
    try:
        result = await asyncio.to_thread(
            process_arxiv_id,
            arxiv_id,
            push_supabase=True,
            force=force,
        )
    except Exception as exc:
        logger.exception("process_paper failed: %s", exc)
        return _err(f"process_paper failed: {exc}")

    if result.status == "skipped":
        return _ok({
            "arxiv_id": arxiv_id,
            "status": "skipped",
            "reason": "already complete (pass force=true to re-process)",
        })
    if result.status == "error":
        return _err(f"process_paper failed: processing error for {arxiv_id} (see server logs)")

    # status == "processed" — counts read back from the DB rows just written
    section_count = 0
    math_count = 0
    title = ""
    try:
        from lib.supabase_push import _get_client
        client = _get_client()
        paper_resp = (
            client.table("papers").select("id, title")
            .eq("arxiv_id", arxiv_id).maybe_single().execute()
        )
        paper_row = paper_resp.data or {}
        title = paper_row.get("title") or ""
        secs_resp = (
            client.table("sections").select("id")
            .eq("paper_id", paper_row.get("id")).execute()
        )
        section_ids = [s["id"] for s in (secs_resp.data or [])]
        section_count = len(section_ids)
        if section_ids:
            blocks_resp = (
                client.table("math_blocks").select("id")
                .in_("section_id", section_ids).execute()
            )
            math_count = len(blocks_resp.data or [])
    except Exception as exc:
        logger.warning("post-process count lookup failed: %s", exc)

    return _ok({
        "arxiv_id": arxiv_id,
        "status": "complete",
        "title": title,
        "section_count": section_count,
        "math_block_count": math_count,
    })


# ---------------------------------------------------------------------------
# Tool: create_sections
# ---------------------------------------------------------------------------

@mcp.tool()
async def create_sections(arxiv_id: str) -> list[dict]:
    """Parse ArXiv LaTeX into sections and store in Supabase (no LLM calls).
    Use before explain_section_math when you want to control the LLM budget
    per section rather than running the full pipeline at once."""
    from lib.arxiv_source import fetch_arxiv_latex_full
    from lib.latex_parse import parse_latex_sections
    from lib.models import Paper
    from lib.supabase_push import push_paper

    logger.info("create_sections(%s)", arxiv_id)
    try:
        result = await asyncio.to_thread(fetch_arxiv_latex_full, arxiv_id)
    except Exception as exc:
        return _err(f"Failed to fetch LaTeX: {exc}")

    if result is None:
        return _err(f"No LaTeX source found for {arxiv_id}")

    latex_body, _full_src = result

    try:
        sections = await asyncio.to_thread(parse_latex_sections, latex_body)
    except Exception as exc:
        return _err(f"Failed to parse sections: {exc}")

    paper = Paper(
        title=arxiv_id,
        text=latex_body,
        arxiv_id=arxiv_id,
        source_type="arxiv_latex",
        sections=sections,
    )

    try:
        await asyncio.to_thread(push_paper, paper)
    except Exception as exc:
        return _err(f"Failed to push sections to Supabase: {exc}")

    math_count = sum(len(s.math_blocks) for s in sections)
    return _ok({
        "arxiv_id": arxiv_id,
        "section_count": len(sections),
        "math_block_count": math_count,
        "sections": [
            {"order_idx": s.order_idx, "title": s.title, "math_blocks": len(s.math_blocks)}
            for s in sections
        ],
    })


# ---------------------------------------------------------------------------
# Tool: explain_section_math
# ---------------------------------------------------------------------------

@mcp.tool()
async def explain_section_math(
    arxiv_id: str,
    section_id: str,
    max_blocks: int = 20,
) -> list[dict]:
    """[long_running] Run MathExplainer on all math blocks in one section.
    Fetches blocks from Supabase, explains each, writes explanations back.
    Returns count of blocks explained. Takes ~30s–5min depending on block count."""
    from lib.dspy_config import configure_dspy
    from lib.dspy_modules import MathExplainer
    from lib.supabase_push import _get_client

    logger.info("explain_section_math(%s, section_id=%s)", arxiv_id, section_id)

    await asyncio.to_thread(configure_dspy)

    client = _get_client()

    # Fetch section title
    sec_resp = client.table("sections").select("title, paper_id").eq("id", section_id).maybe_single().execute()
    if not sec_resp.data:
        return _err(f"Section {section_id} not found")
    section_title = sec_resp.data.get("title", "Unknown Section")

    # Fetch paper title
    paper_id = sec_resp.data["paper_id"]
    paper_resp = client.table("papers").select("title").eq("id", paper_id).maybe_single().execute()
    paper_title = paper_resp.data.get("title", arxiv_id) if paper_resp.data else arxiv_id

    # Fetch math blocks without explanations
    blocks_resp = client.table("math_blocks").select("*").eq("section_id", section_id).order("order_idx").execute()
    raw_blocks = blocks_resp.data or []

    if not raw_blocks:
        return _ok({"section_id": section_id, "explained": 0, "reason": "no math blocks"})

    from lib.models import MathBlock
    explainer = MathExplainer()
    explained = 0
    errors = 0

    for raw in raw_blocks[:max_blocks]:
        # Skip already explained blocks
        if raw.get("explanation"):
            continue

        block = MathBlock(
            order_idx=raw["order_idx"],
            env_type=raw.get("env_type", "equation"),
            latex_expr=raw.get("latex_expr", ""),
            context_before=raw.get("context_before", ""),
            context_after=raw.get("context_after", ""),
            paper_type=raw.get("paper_type", "research_paper"),
        )

        try:
            explained_block = await asyncio.to_thread(
                explainer.explain_block, block, paper_title, section_title
            )
            if explained_block.explanation:
                client.table("math_blocks").update({
                    "explanation": explained_block.explanation,
                    "explanation_model": explained_block.explanation_model or "",
                }).eq("id", raw["id"]).execute()
                explained += 1
        except Exception as exc:
            logger.warning("explain_block failed for %s: %s", raw["id"], exc)
            errors += 1

    return _ok({
        "section_id": section_id,
        "section_title": section_title,
        "explained": explained,
        "skipped_already_explained": len([b for b in raw_blocks if b.get("explanation")]),
        "errors": errors,
        "total_blocks": len(raw_blocks),
    })


# ---------------------------------------------------------------------------
# Tool: explain_section_algorithms
# ---------------------------------------------------------------------------

@mcp.tool()
async def explain_section_algorithms(
    arxiv_id: str,
    section_id: str,
    max_blocks: int = 5,
) -> list[dict]:
    """[long_running] Run AlgorithmExplainer on all algorithm blocks in one section.
    Fetches blocks from Supabase, explains each, writes explanations back.
    Takes ~30s–2min depending on block count."""
    from lib.dspy_config import configure_dspy
    from lib.dspy_modules import AlgorithmExplainer
    from lib.supabase_push import _get_client

    logger.info("explain_section_algorithms(%s, section_id=%s)", arxiv_id, section_id)

    await asyncio.to_thread(configure_dspy)

    client = _get_client()

    sec_resp = client.table("sections").select("title, paper_id").eq("id", section_id).maybe_single().execute()
    if not sec_resp.data:
        return _err(f"Section {section_id} not found")
    section_title = sec_resp.data.get("title", "Unknown Section")

    paper_id = sec_resp.data["paper_id"]
    paper_resp = client.table("papers").select("title").eq("id", paper_id).maybe_single().execute()
    paper_title = paper_resp.data.get("title", arxiv_id) if paper_resp.data else arxiv_id

    blocks_resp = (
        client.table("algorithm_blocks")
        .select("*")
        .eq("section_id", section_id)
        .order("order_idx")
        .execute()
    )
    raw_blocks = blocks_resp.data or []

    if not raw_blocks:
        return _ok({"section_id": section_id, "explained": 0, "reason": "no algorithm blocks"})

    from lib.models import AlgorithmBlock
    explainer = AlgorithmExplainer()
    explained = 0
    errors = 0

    for raw in raw_blocks[:max_blocks]:
        if raw.get("explanation"):
            continue

        block = AlgorithmBlock(
            order_idx=raw["order_idx"],
            caption=raw.get("caption", ""),
            pseudocode_text=raw.get("pseudocode_text", ""),
            raw_pseudocode=raw.get("raw_pseudocode", ""),
            context_before=raw.get("context_before", ""),
            context_after=raw.get("context_after", ""),
        )

        try:
            explained_block = await asyncio.to_thread(
                explainer.explain_block, block, paper_title, section_title
            )
            if explained_block.explanation:
                client.table("algorithm_blocks").update({
                    "explanation": explained_block.explanation,
                    "explanation_model": explained_block.explanation_model or "",
                }).eq("id", raw["id"]).execute()
                explained += 1
        except Exception as exc:
            logger.warning("explain_algo_block failed for %s: %s", raw["id"], exc)
            errors += 1

    return _ok({
        "section_id": section_id,
        "section_title": section_title,
        "explained": explained,
        "errors": errors,
        "total_blocks": len(raw_blocks),
    })


# ---------------------------------------------------------------------------
# Tool: get_paper_status
# ---------------------------------------------------------------------------

@mcp.tool()
async def get_paper_status(arxiv_id: str) -> list[dict]:
    """Return the current processing status of a paper from Supabase.
    Status values: pending | processing | complete | error | None (not found)."""
    from lib.supabase_push import get_paper_status as _get_status

    try:
        status = await asyncio.to_thread(_get_status, arxiv_id)
    except Exception as exc:
        return _err(f"get_paper_status failed: {exc}")

    return _ok({"arxiv_id": arxiv_id, "status": status})


# ---------------------------------------------------------------------------
# Health check + entrypoint
# ---------------------------------------------------------------------------

def create_app():
    """Return the Starlette ASGI app with an extra /health route."""
    from starlette.applications import Starlette
    from starlette.requests import Request
    from starlette.responses import JSONResponse
    from starlette.routing import Mount, Route

    async def health(request: Request) -> JSONResponse:
        return JSONResponse({"status": "ok", "server": "paper-processor-mcp"})

    mcp_app = mcp.streamable_http_app()
    return Starlette(routes=[
        Route("/health", health),
        Mount("/", app=mcp_app),
    ])


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(create_app(), host="0.0.0.0", port=8000)
