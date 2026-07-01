"""math-to-code-mcp — FastMCP server (3 tools).

Converts stored math blocks (LaTeX + explanation) into runnable Python code
using DSPy FormulaCodeGeneratorModule. Inspired by Paper2Agent's principle:
every formula with a clear computation → one clean parameterized function.

Tools:
  list_implementable_formulas  — classify math blocks in a section
  generate_formula_code        — generate Python for one block [long_running]
  generate_section_code        — generate complete module for a section [long_running]

Run locally (requires Modal):
  modal serve mcp-servers/math-to-code-mcp/modal_app.py

Or as a standalone dev server:
  python mcp-servers/math-to-code-mcp/server.py
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any

# Ensure repo root is on sys.path regardless of cwd
_REPO_ROOT = str(Path(__file__).resolve().parent.parent.parent)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from mcp.server.fastmcp import FastMCP
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Mount, Route

mcp = FastMCP("math-to-code-mcp")

# ---------------------------------------------------------------------------
# Supabase helpers
# ---------------------------------------------------------------------------

def _get_supabase():
    from supabase import create_client
    url = os.environ["SUPABASE_URL"]
    key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
    return create_client(url, key)


def _fetch_block(block_id: str) -> dict[str, Any]:
    sb = _get_supabase()
    res = (
        sb.table("math_blocks")
        .select(
            "id, order_idx, env_type, latex_expr, context_before, context_after, "
            "explanation, explanation_model, "
            "sections(id, title, paper_id, papers(title))"
        )
        .eq("id", block_id)
        .single()
        .execute()
    )
    if not res.data:
        raise ValueError(f"math_block {block_id!r} not found")
    return res.data


def _fetch_section_blocks(section_id: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Return (section_row, [math_block_rows]) sorted by order_idx."""
    sb = _get_supabase()
    sec_res = (
        sb.table("sections")
        .select("id, title, paper_id, papers(title)")
        .eq("id", section_id)
        .single()
        .execute()
    )
    if not sec_res.data:
        raise ValueError(f"section {section_id!r} not found")
    section = sec_res.data

    blk_res = (
        sb.table("math_blocks")
        .select("id, order_idx, env_type, latex_expr, context_before, context_after, explanation, explanation_model")
        .eq("section_id", section_id)
        .order("order_idx")
        .execute()
    )
    return section, blk_res.data or []


def _persist_artifact(
    block_id: str,
    section_id: str,
    library: str,
    pred: Any,
    model: str,
) -> str:
    """Upsert into math_code_artifacts and return the artifact id."""
    sb = _get_supabase()
    # DELETE existing for same block+library so we always have fresh data
    sb.table("math_code_artifacts").delete().eq("block_id", block_id).eq("library", library).execute()

    parameters_json = None
    try:
        parameters_json = json.loads(pred.parameters) if pred.parameters else None
    except (json.JSONDecodeError, TypeError):
        parameters_json = pred.parameters  # keep as string fallback

    row = {
        "block_id": block_id,
        "section_id": section_id,
        "library": library,
        "function_name": pred.function_name,
        "imports": pred.imports,
        "code": pred.code,
        "example_usage": getattr(pred, "example_usage", None),
        "test_code": getattr(pred, "test_code", None),
        "parameters": parameters_json,
        "notes": getattr(pred, "notes", None),
        "generated_model": model,
    }
    res = sb.table("math_code_artifacts").insert(row).execute()
    return res.data[0]["id"] if res.data else ""


# ---------------------------------------------------------------------------
# DSPy helpers
# ---------------------------------------------------------------------------

def _configure_and_get_generator():
    from lib.dspy_config import configure_dspy
    from lib.dspy_modules import FormulaCodeGeneratorModule
    configure_dspy()
    return FormulaCodeGeneratorModule()


def _is_implementable_raw(raw: dict[str, Any]) -> tuple[bool, str]:
    """Classify implementability from a raw Supabase row dict."""
    if not raw.get("explanation"):
        return False, "no explanation stored — run explain_section_math first"
    if raw.get("env_type") == "inline" and len(raw.get("latex_expr", "")) < 10:
        return False, "trivial inline expression"
    try:
        exp = json.loads(raw["explanation"])
    except (json.JSONDecodeError, TypeError):
        return False, "explanation is not valid JSON"
    what = exp.get("what_it_computes", "").lower()
    notation_kw = ("notation", "defines", "denotes", "let ", "where ", "symbol for")
    if any(kw in what for kw in notation_kw):
        return False, "definitional notation, not a computation"
    return True, "has clear input→output computation"


def _suggested_name(library: str, raw: dict[str, Any]) -> str:
    try:
        exp = json.loads(raw["explanation"])
        what = exp.get("what_it_computes", "formula")
        # Very rough slug: first 5 words → snake_case
        slug = "_".join(what.lower().split()[:5])
        slug = "".join(c if c.isalnum() or c == "_" else "_" for c in slug).strip("_")
        return f"{library}_compute_{slug}"
    except Exception:
        return f"{library}_compute_formula"


# ---------------------------------------------------------------------------
# Tool: list_implementable_formulas
# ---------------------------------------------------------------------------

@mcp.tool()
async def list_implementable_formulas(section_id: str) -> str:
    """Survey math blocks in a section and classify which are suitable for code generation.

    Args:
        section_id: UUID of the section from the sections table.

    Returns JSON with section_title, a classified list of blocks, and implementable_count.
    """
    section, blocks = await asyncio.to_thread(_fetch_section_blocks, section_id)
    section_title = section.get("title", "")

    results = []
    implementable_count = 0
    for raw in blocks:
        ok, reason = _is_implementable_raw(raw)
        status = "yes" if ok else "no"
        if ok:
            implementable_count += 1
        exp: dict = {}
        try:
            exp = json.loads(raw["explanation"]) if raw.get("explanation") else {}
        except Exception:
            pass
        results.append({
            "block_id": raw["id"],
            "order_idx": raw["order_idx"],
            "env_type": raw.get("env_type", ""),
            "latex_expr": raw.get("latex_expr", ""),
            "what_it_computes": exp.get("what_it_computes", ""),
            "implementability": status,
            "reason": reason,
            "suggested_function_name": _suggested_name("numpy", raw) if ok else "",
        })

    return json.dumps({
        "section_id": section_id,
        "section_title": section_title,
        "blocks": results,
        "implementable_count": implementable_count,
    })


# ---------------------------------------------------------------------------
# Tool: generate_formula_code
# ---------------------------------------------------------------------------

@mcp.tool()
async def generate_formula_code(
    block_id: str,
    library: str = "numpy",
    include_tests: bool = True,
) -> str:
    """Generate a clean Python function implementing the math formula stored in block_id.

    This is a long-running tool (~30–90s). Uses DSPy FormulaCodeGeneratorModule.
    Result is cached in math_code_artifacts table.

    Args:
        block_id:      UUID from math_blocks table.
        library:       Target library — "numpy" | "pytorch" | "jax" | "scipy".
        include_tests: Whether to generate a pytest test function.

    Returns JSON artifact: function_name, imports, code, parameters, example_usage,
    test_code, notes, prompt_context, generated_model, artifact_id.
    """
    raw = await asyncio.to_thread(_fetch_block, block_id)
    section = raw.get("sections") or {}
    paper = (section.get("papers") or {}) if isinstance(section, dict) else {}
    section_id = section.get("id", "") if isinstance(section, dict) else ""
    section_title = section.get("title", "") if isinstance(section, dict) else ""
    paper_title = paper.get("title", "") if isinstance(paper, dict) else ""

    implementable, reason = _is_implementable_raw(raw)
    if not implementable:
        return json.dumps({"error": f"block is not implementable: {reason}"})

    exp: dict = {}
    try:
        exp = json.loads(raw["explanation"])
    except Exception:
        pass

    def _run() -> Any:
        gen = _configure_and_get_generator()
        from lib.models import MathBlock
        block = MathBlock(
            order_idx=raw.get("order_idx", 0),
            env_type=raw.get("env_type", "equation"),
            latex_expr=raw.get("latex_expr", ""),
            context_before=raw.get("context_before") or "",
            context_after=raw.get("context_after") or "",
            explanation=raw.get("explanation"),
        )
        return gen.forward(
            paper_title=paper_title,
            section_title=section_title,
            block=block,
            library=library,
        )

    pred = await asyncio.to_thread(_run)

    from lib.dspy_config import configure_dspy
    model_name = configure_dspy()

    artifact_id = await asyncio.to_thread(
        _persist_artifact, block_id, section_id, library, pred, model_name
    )

    prompt_context = {
        "formula": raw.get("latex_expr", ""),
        "what_it_computes": exp.get("what_it_computes", ""),
        "symbol_meanings": exp.get("symbol_meanings", ""),
        "context_before": raw.get("context_before") or "",
        "context_after": raw.get("context_after") or "",
        "library": library,
    }

    return json.dumps({
        "block_id": block_id,
        "latex_expr": raw.get("latex_expr", ""),
        "function_name": pred.function_name,
        "library": library,
        "imports": pred.imports,
        "code": pred.code,
        "parameters": pred.parameters,
        "example_usage": pred.example_usage,
        "test_code": pred.test_code if include_tests else None,
        "notes": pred.notes,
        "prompt_context": prompt_context,
        "generated_model": model_name,
        "artifact_id": artifact_id,
    })


# ---------------------------------------------------------------------------
# Tool: generate_section_code
# ---------------------------------------------------------------------------

@mcp.tool()
async def generate_section_code(
    section_id: str,
    library: str = "numpy",
    include_tests: bool = True,
    max_formulas: int = 10,
) -> str:
    """Generate a complete Python module implementing all implementable formulas in a section.

    Each formula becomes one function. Module includes imports, docstring citing the
    paper+section, all functions, and __all__. Mirrors Paper2Agent's section-based approach.

    Args:
        section_id:    UUID from sections table.
        library:       "numpy" | "pytorch" | "jax" | "scipy".
        include_tests: Whether to generate a pytest module.
        max_formulas:  Cap on LLM calls; named envs (equation/align) are prioritised.

    Returns JSON with module_code, module_filename, functions list, test_module_code.
    """
    section, blocks = await asyncio.to_thread(_fetch_section_blocks, section_id)
    section_title = section.get("title", "Untitled")
    paper = (section.get("papers") or {}) if isinstance(section.get("papers"), dict) else {}
    paper_title = paper.get("title", "") if isinstance(paper, dict) else ""

    # Prioritise named environments; cap at max_formulas
    priority_envs = {"equation", "align", "gather", "multline"}
    implementable = [
        b for b in blocks
        if _is_implementable_raw(b)[0] and b.get("env_type") in priority_envs
    ]
    implementable += [
        b for b in blocks
        if _is_implementable_raw(b)[0] and b.get("env_type") not in priority_envs
    ]
    to_process = implementable[:max_formulas]

    skipped = [b for b in blocks if b not in to_process]
    skip_reasons = [_is_implementable_raw(b)[1] for b in skipped if not _is_implementable_raw(b)[0]]

    if not to_process:
        return json.dumps({
            "error": "No implementable formulas found in this section.",
            "skipped_count": len(skipped),
            "skip_reasons": skip_reasons,
        })

    # Generate code for each block sequentially (DSPy calls are blocking)
    all_functions: list[dict] = []
    all_imports: set[str] = set()
    all_tests: list[str] = []

    def _gen_one(raw: dict) -> Any:
        gen = _configure_and_get_generator()
        from lib.models import MathBlock
        block = MathBlock(
            order_idx=raw.get("order_idx", 0),
            env_type=raw.get("env_type", "equation"),
            latex_expr=raw.get("latex_expr", ""),
            context_before=raw.get("context_before") or "",
            context_after=raw.get("context_after") or "",
            explanation=raw.get("explanation"),
        )
        return gen.forward(
            paper_title=paper_title,
            section_title=section_title,
            block=block,
            library=library,
        )

    from lib.dspy_config import configure_dspy
    model_name = configure_dspy()

    for i, raw in enumerate(to_process):
        try:
            pred = await asyncio.to_thread(_gen_one, raw)
        except Exception as exc:
            skip_reasons.append(f"block {raw['id']}: generation failed — {exc}")
            continue

        await asyncio.to_thread(
            _persist_artifact,
            raw["id"],
            section_id,
            library,
            pred,
            model_name,
        )

        for imp_line in pred.imports.splitlines():
            line = imp_line.strip()
            if line:
                all_imports.add(line)

        all_functions.append({
            "function_name": pred.function_name,
            "latex_expr": raw.get("latex_expr", ""),
            "code": pred.code,
            "line_number": None,  # filled after assembly
        })
        if include_tests and pred.test_code:
            all_tests.append(pred.test_code)

    # Assemble module
    slug = "_".join(section_title.lower().split()[:4])
    slug = "".join(c if c.isalnum() or c == "_" else "_" for c in slug).strip("_")
    module_filename = f"{slug or 'formulas'}.py"
    func_names = [f["function_name"] for f in all_functions]

    module_lines = [
        f'"""Auto-generated Python module for: {section_title}',
        f"Paper: {paper_title}",
        f'Library: {library}',
        '"""',
        "",
        *sorted(all_imports),
        "",
        "__all__ = " + json.dumps(func_names),
        "",
    ]
    current_line = len(module_lines) + 1
    for fn in all_functions:
        fn["line_number"] = current_line
        module_lines.append(fn["code"])
        module_lines.append("")
        current_line += fn["code"].count("\n") + 2

    module_code = "\n".join(module_lines)

    test_module_code = None
    if include_tests and all_tests:
        test_lines = [
            f'"""Tests for {module_filename}."""',
            "import pytest",
            f"from {slug or 'formulas'} import *",
            "",
            *all_tests,
        ]
        test_module_code = "\n\n".join(test_lines)

    return json.dumps({
        "section_id": section_id,
        "section_title": section_title,
        "arxiv_id": "",  # caller can resolve via section → paper
        "module_code": module_code,
        "module_filename": module_filename,
        "functions": [
            {"function_name": f["function_name"], "latex_expr": f["latex_expr"], "line_number": f["line_number"]}
            for f in all_functions
        ],
        "test_module_code": test_module_code,
        "skipped_count": len(blocks) - len(all_functions),
        "skip_reasons": skip_reasons,
    })


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------

def create_app() -> Starlette:
    async def health(_: Request) -> JSONResponse:
        return JSONResponse({"status": "ok", "server": "math-to-code-mcp"})

    return Starlette(
        routes=[
            Route("/health", health),
            Mount("/", app=mcp.streamable_http_app()),
        ]
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(create_app(), host="0.0.0.0", port=8001)
