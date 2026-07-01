"""Modal deployment for math-to-code-mcp.

Exposes the FastMCP server as a Modal web endpoint.
Shares the same paper2md-secrets secret group as paper-processor-mcp.

Deploy:
  modal deploy mcp-servers/math-to-code-mcp/modal_app.py

Serve locally:
  modal serve mcp-servers/math-to-code-mcp/modal_app.py

Secrets (shared with paper-processor-mcp — create once):
  modal secret create paper2md-secrets \\
    SUPABASE_URL="..." \\
    SUPABASE_SERVICE_ROLE_KEY="..." \\
    GEMINI_API_KEY="..." \\
    GROQ_API_KEY="..." \\
    OPENROUTER_API_KEY="..." \\
    PAPER2MD_LLM_PROVIDER="gemini" \\
    PAPER2MD_MAX_MATH_BLOCKS="50"
"""

from __future__ import annotations

import sys
from pathlib import Path

import modal

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent

image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install_from_requirements(str(_REPO_ROOT / "requirements.txt"))
    .copy_local_dir(str(_REPO_ROOT / "lib"), "/app/lib")
    .copy_local_file(str(_REPO_ROOT / "prompts.json"), "/app/prompts.json")
    .copy_local_dir(
        str(_REPO_ROOT / "mcp-servers" / "math-to-code-mcp"),
        "/app/mcp-servers/math-to-code-mcp",
    )
    .env({"PYTHONPATH": "/app"})
)

app = modal.App("paper2md-math-to-code-mcp", image=image)
secrets = [modal.Secret.from_name("paper2md-secrets")]


@app.function(
    secrets=secrets,
    timeout=180,   # 3 min — single formula generation via DSPy
    memory=1024,
    cpu=1,
)
@modal.asgi_app()
def serve():
    """ASGI app exposing the math-to-code FastMCP server."""
    import importlib.util

    sys.path.insert(0, "/app")
    spec = importlib.util.spec_from_file_location(
        "server",
        "/app/mcp-servers/math-to-code-mcp/server.py",
    )
    server_mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(server_mod)  # type: ignore[union-attr]
    return server_mod.create_app()
