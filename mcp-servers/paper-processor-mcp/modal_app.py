"""Modal deployment for paper-processor-mcp.

Exposes the FastMCP server as a Modal web endpoint and runs the
batch cron job (replaces GitHub Actions process_pending.yml).

Deploy:
  modal deploy mcp-servers/paper-processor-mcp/modal_app.py

Serve locally:
  modal serve mcp-servers/paper-processor-mcp/modal_app.py

Secrets (one-time setup):
  modal secret create paper2md-secrets \\
    SUPABASE_URL="https://..." \\
    SUPABASE_SERVICE_ROLE_KEY="sb_secret_..." \\
    GEMINI_API_KEY="..." \\
    GROQ_API_KEY="..." \\
    OPENROUTER_API_KEY="..." \\
    OPENAI_API_KEY="..." \\
    PAPER2MD_LLM_PROVIDER="gemini" \\
    PAPER2MD_MAX_MATH_BLOCKS="50"
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import modal

# ---------------------------------------------------------------------------
# Modal image — install Python deps + copy repo
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent

image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install_from_requirements(str(_REPO_ROOT / "requirements.txt"))
    .copy_local_dir(str(_REPO_ROOT / "lib"), "/app/lib")
    .copy_local_file(str(_REPO_ROOT / "summarize_papers.py"), "/app/summarize_papers.py")
    .copy_local_file(str(_REPO_ROOT / "prompts.json"), "/app/prompts.json")
    .copy_local_dir(
        str(_REPO_ROOT / "mcp-servers" / "paper-processor-mcp"),
        "/app/mcp-servers/paper-processor-mcp",
    )
    .env({"PYTHONPATH": "/app"})
)

app = modal.App("paper2md-processor-mcp", image=image)
secrets = [modal.Secret.from_name("paper2md-secrets")]


# ---------------------------------------------------------------------------
# MCP web endpoint
# ---------------------------------------------------------------------------

@app.function(
    secrets=secrets,
    timeout=600,          # 10 min — enough for large papers
    memory=2048,
    cpu=2,
)
@modal.asgi_app()
def serve():
    """ASGI app exposing the FastMCP server over streamable HTTP."""
    import importlib.util

    sys.path.insert(0, "/app")
    spec = importlib.util.spec_from_file_location(
        "server",
        "/app/mcp-servers/paper-processor-mcp/server.py",
    )
    server_mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(server_mod)  # type: ignore[union-attr]
    return server_mod.create_app()


# ---------------------------------------------------------------------------
# Scheduled batch — replaces .github/workflows/process_pending.yml cron
# ---------------------------------------------------------------------------

@app.function(
    secrets=secrets,
    schedule=modal.Cron("0 */6 * * *"),   # every 6 hours, matching the Actions schedule
    timeout=1200,                           # 20 min — batch may process several papers
    memory=2048,
    cpu=2,
)
async def process_pending_batch() -> None:
    """Fetch all pending papers from Supabase and process them sequentially."""
    sys.path.insert(0, "/app")
    from lib.supabase_push import fetch_pending_arxiv_ids
    from summarize_papers import process_arxiv_id

    pending = fetch_pending_arxiv_ids()
    if not pending:
        print("[batch] No pending papers")
        return

    print(f"[batch] Processing {len(pending)} pending papers: {pending}")
    for arxiv_id in pending:
        try:
            await asyncio.to_thread(process_arxiv_id, arxiv_id, push_supabase=True)
            print(f"[batch] Done: {arxiv_id}")
        except Exception as exc:
            print(f"[batch] Error processing {arxiv_id}: {exc}")
