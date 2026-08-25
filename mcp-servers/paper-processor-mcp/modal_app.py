"""Modal deployment for paper-processor-mcp + math visualization.

Exposes the FastMCP server as a Modal web endpoint, runs the
batch cron job, and provides an on-demand math visualization endpoint
that generates ManimGL PNG diagrams for math blocks.

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
    PAPER2MD_MAX_MATH_BLOCKS="50" \\
    VIZ_STORAGE_BACKEND="supabase"

  Storage backend toggle (VIZ_STORAGE_BACKEND):
    "supabase" (default) — uses existing SUPABASE_* env vars, math-visuals bucket
    "r2"                 — requires R2_ACCOUNT_ID, R2_ACCESS_KEY_ID,
                           R2_SECRET_ACCESS_KEY, R2_BUCKET_NAME, R2_PUBLIC_URL
                           + boto3 in manim_image pip_install
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
_MANIM_ROOT = Path.home() / "__myworkarea" / "projects" / "genai" / "agentic-ai" / "math-animation" / "manim"

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

# ManimGL image — GPU-capable, includes LaTeX + Vulkan for headless rendering
manim_image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install(
        # Vulkan / GPU rendering
        "libvulkan1", "mesa-vulkan-drivers", "vulkan-tools",
        # LaTeX (for Tex/MathTex mobjects)
        "texlive-xetex", "texlive-fonts-recommended", "texlive-latex-extra",
        "texlive-science",   # amsmath, amssymb etc.
        "dvisvgm",
        # Media
        "ffmpeg",
        # GL libs
        "libgl1-mesa-glx", "libegl1-mesa", "libglib2.0-0",
    )
    .pip_install(
        "supabase>=2.0.0",
        "httpx>=0.27.0",
    )
    .copy_local_dir(str(_MANIM_ROOT), "/app/manim")
    .run_commands(
        "cd /app/manim && pip install -e .",
    )
    .env({"PYTHONPATH": "/app", "DISPLAY": ""})
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
            result = await asyncio.to_thread(process_arxiv_id, arxiv_id, push_supabase=True)
            print(f"[batch] {result.status}: {arxiv_id}")
        except Exception as exc:
            print(f"[batch] Error processing {arxiv_id}: {exc}")


# ---------------------------------------------------------------------------
# Math visualization — ManimGL headless render
# ---------------------------------------------------------------------------

MANIM_SCENE_SYSTEM_PROMPT = """\
You are a ManimGL v1.7.2 code generator. Given a LaTeX math expression and its explanation,
generate a self-contained Python scene that visually illustrates the formula.

## Rules
- The scene class MUST be named `FormulaScene`
- Import everything from manimlib: `from manimlib import *`
- For STATIC mode: use ONLY `self.add()` calls — no `self.play()`, no animations
- For ANIMATED mode: use `self.play()` with animations like Write, FadeIn, Transform, ShowCreation
  Keep animations SHORT (3-5 seconds total). Use `self.wait(0.5)` between steps.
- The mode will be specified in the user message
- Resolution is 1280×720; the coordinate system spans roughly x=[-7,7] y=[-4,4]
- Use a dark background (ManimGL default)
- Place the rendered LaTeX formula at the top using `Tex()` (NOT MathTex — it does not exist in ManimGL)
- Below the formula, add visual aids: annotated symbols, geometric diagrams,
  function plots, matrix visualizations, or conceptual diagrams as appropriate
- Use colors to distinguish different parts: BLUE, YELLOW, GREEN, RED, TEAL, ORANGE
- Use `Brace`, `Arrow`, `Text`, `SurroundingRectangle` for annotations
- Keep the layout clean and readable — don't overcrowd

## CRITICAL: ManimGL v1.7.2 API differences from ManimCE
- Use `Tex()` for ALL LaTeX (both text and math). There is NO `MathTex` class.
- Use `Tex(r"$E = mc^2$")` for math mode (wrap in dollar signs inside Tex)
- Use `ShowCreation` NOT `Create` for drawing animations
- Use `axes.get_graph()` NOT `axes.plot()`
- `FunctionGraph(lambda x: ...)` works directly
- `Arrow(start, end)` takes points, not mobjects

## Available ManimGL classes (use only these)
- `Tex(r"$\\LaTeX$")`, `Text("plain text")`
- `NumberPlane()`, `Axes()`, `FunctionGraph(lambda x: x**2)`
- `Circle()`, `Square()`, `Rectangle()`, `Line()`, `Arrow()`, `Vector()`
- `Brace(mobject, direction)`, `SurroundingRectangle(mobject)`
- `VGroup(*mobjects)`, `Dot()`, `DashedLine()`
- `Matrix([[1,2],[3,4]])`, `IntegerMatrix()`
- Positioning: `.to_edge(UP)`, `.to_corner(UL)`, `.next_to(obj, DOWN)`
- Colors: BLUE, YELLOW, GREEN, RED, TEAL, ORANGE, WHITE, GREY

## Example 1: Simple equation (STATIC)
```python
from manimlib import *

class FormulaScene(Scene):
    def construct(self):
        formula = Tex(r"$E = mc^2$")
        formula.scale(1.5).to_edge(UP, buff=1.0)
        self.add(formula)

        e_label = Text("Energy", font_size=24, color=BLUE)
        m_label = Text("Mass", font_size=24, color=GREEN)
        c_label = Text("Speed of light²", font_size=24, color=YELLOW)

        e_label.next_to(formula[0][0], DOWN, buff=0.8)
        m_label.next_to(formula[0][2], DOWN, buff=0.8)
        c_label.next_to(formula[0][3:], DOWN, buff=0.8)

        self.add(e_label, m_label, c_label)
```

## Example 2: Function with plot (STATIC)
```python
from manimlib import *

class FormulaScene(Scene):
    def construct(self):
        formula = Tex(r"$f(x) = \\sin(x)$")
        formula.scale(1.3).to_edge(UP, buff=0.5)
        self.add(formula)

        axes = Axes(x_range=[-4, 4], y_range=[-1.5, 1.5], width=10, height=4)
        axes.shift(DOWN * 0.5)
        graph = axes.get_graph(lambda x: np.sin(x), color=BLUE)
        self.add(axes, graph)
```

## Output format
Return ONLY the Python code. No markdown fences, no explanation text.
"""

MANIM_SCENE_USER_TEMPLATE = """\
LaTeX expression: {latex_expr}
Environment type: {env_type}

Explanation:
{explanation_text}

Context before: {context_before}
Context after: {context_after}

Mode: {mode}
{mode_instruction}

Generate a FormulaScene that visually illustrates this formula.
"""

_MAX_VIZ_RETRIES = 2


def _call_viz_llm(api_key: str, latex_expr: str, env_type: str,
                  explanation_text: str, context_before: str,
                  context_after: str, mode: str = "static",
                  error_feedback: str | None = None) -> str:
    """Call LLM to generate ManimGL Scene code."""
    import httpx

    if mode == "animated":
        mode_instruction = "Use self.play() with animations (Write, FadeIn, Transform, ShowCreation). Keep total duration 3-5 seconds."
    else:
        mode_instruction = "Use ONLY self.add() calls. No self.play() or animations."

    user_msg = MANIM_SCENE_USER_TEMPLATE.format(
        latex_expr=latex_expr,
        env_type=env_type,
        explanation_text=explanation_text,
        context_before=context_before or "",
        context_after=context_after or "",
        mode=mode.upper(),
        mode_instruction=mode_instruction,
    )
    if error_feedback:
        user_msg += f"\n\nPrevious attempt failed with error:\n{error_feedback}\nFix the code and try again."

    resp = httpx.post(
        "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent",
        params={"key": api_key},
        json={
            "system_instruction": {"parts": [{"text": MANIM_SCENE_SYSTEM_PROMPT}]},
            "contents": [{"parts": [{"text": user_msg}]}],
            "generationConfig": {
                "temperature": 0.3,
                "maxOutputTokens": 4096,
            },
        },
        timeout=60,
    )
    resp.raise_for_status()
    data = resp.json()

    text = data["candidates"][0]["content"]["parts"][0]["text"]
    # Strip markdown fences if present
    text = text.strip()
    if text.startswith("```python"):
        text = text[len("```python"):].strip()
    if text.startswith("```"):
        text = text[3:].strip()
    if text.endswith("```"):
        text = text[:-3].strip()

    return text


def _render_scene(scene_code: str, block_id: str, mode: str = "static",
                  output_dir: str = "/tmp/manim_output") -> str:
    """Write scene code to file and render via manimgl CLI.

    mode="static"  → PNG (last frame)
    mode="animated" → GIF (short animation)

    Returns path to the output file.
    """
    import os
    import subprocess

    os.makedirs(output_dir, exist_ok=True)
    scene_file = f"/tmp/scene_{block_id}.py"
    with open(scene_file, "w") as f:
        f.write(scene_code)

    if mode == "animated":
        # Render as GIF: -w (write to file) + -i (GIF output) + -l (low quality)
        cmd = [
            "manimgl", scene_file, "FormulaScene",
            "-w", "-i",
            "--file_name", f"viz_{block_id}",
            "-l",
        ]
        ext = ".gif"
        timeout = 60  # animations take longer
    else:
        # Render as PNG: -s (skip animations) + -w (write) + -l (low quality)
        cmd = [
            "manimgl", scene_file, "FormulaScene",
            "-s", "-w",
            "--file_name", f"viz_{block_id}",
            "-l",
        ]
        ext = ".png"
        timeout = 30

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
        cwd="/tmp",
        env={**os.environ, "DISPLAY": "", "VIDEO_DIR": output_dir},
    )

    if result.returncode != 0:
        raise RuntimeError(f"manimgl render failed:\n{result.stderr[-1000:]}")

    # Find the output file
    import glob
    pattern = f"{output_dir}/**/*{ext}"
    found = sorted(glob.glob(pattern, recursive=True), key=os.path.getmtime)
    if found:
        return found[-1]

    # Fallback: any matching file with block_id
    for root, _dirs, files in os.walk(output_dir):
        for fname in files:
            if block_id in fname and fname.endswith(ext):
                return os.path.join(root, fname)

    raise FileNotFoundError(f"No {ext} output found in {output_dir}")


def _upload_to_supabase_storage(file_path: str, block_id: str, mode: str = "static") -> str:
    """Upload rendered file to Supabase Storage and return public URL.

    Uses the 'math-visuals' bucket (must be created as public in Supabase dashboard).
    Requires env vars: SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY.
    """
    import os
    from supabase import create_client

    client = create_client(
        os.environ["SUPABASE_URL"].strip(),
        os.environ["SUPABASE_SERVICE_ROLE_KEY"].strip(),
    )

    ext = "gif" if mode == "animated" else "png"
    content_type = "image/gif" if mode == "animated" else "image/png"
    object_path = f"{block_id}.{ext}"
    bucket_name = "math-visuals"

    with open(file_path, "rb") as f:
        file_data = f.read()

    # Upsert: overwrite if exists (re-render case)
    client.storage.from_(bucket_name).upload(
        path=object_path,
        file=file_data,
        file_options={"content-type": content_type, "upsert": "true"},
    )

    public_url = client.storage.from_(bucket_name).get_public_url(object_path)
    return public_url


def _upload_to_r2(file_path: str, block_id: str, mode: str = "static") -> str:
    """Upload rendered file to Cloudflare R2 and return public URL.

    Requires env vars: R2_ACCOUNT_ID, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY.
    Optional: R2_BUCKET_NAME (default: math-visuals), R2_PUBLIC_URL.
    """
    import os
    import boto3

    account_id = os.environ["R2_ACCOUNT_ID"].strip()
    bucket = os.environ.get("R2_BUCKET_NAME", "math-visuals").strip()

    s3 = boto3.client(
        "s3",
        endpoint_url=f"https://{account_id}.r2.cloudflarestorage.com",
        aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"].strip(),
        aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"].strip(),
        region_name="auto",
    )

    ext = "gif" if mode == "animated" else "png"
    content_type = "image/gif" if mode == "animated" else "image/png"
    object_key = f"{block_id}.{ext}"

    s3.upload_file(
        file_path,
        bucket,
        object_key,
        ExtraArgs={"ContentType": content_type},
    )

    public_domain = os.environ.get(
        "R2_PUBLIC_URL",
        f"https://pub-{account_id}.r2.dev/{bucket}",
    ).rstrip("/")
    return f"{public_domain}/{object_key}"


def _upload_viz(file_path: str, block_id: str, mode: str = "static") -> str:
    """Upload visualization to configured storage backend.

    Set VIZ_STORAGE_BACKEND env var to switch:
      "r2"       → Cloudflare R2 (requires R2_* env vars + boto3)
      "supabase" → Supabase Storage (default, uses existing SUPABASE_* env vars)
    """
    import os

    backend = os.environ.get("VIZ_STORAGE_BACKEND", "supabase").strip().lower()
    if backend == "r2":
        return _upload_to_r2(file_path, block_id, mode)
    return _upload_to_supabase_storage(file_path, block_id, mode)


def _update_math_block(block_id: str, url: str, manim_code: str, mode: str = "static") -> None:
    """Update math_blocks row with visualization data."""
    import os
    from supabase import create_client

    client = create_client(
        os.environ["SUPABASE_URL"].strip(),
        os.environ["SUPABASE_SERVICE_ROLE_KEY"].strip(),
    )
    update_data: dict = {"viz_manim_code": manim_code}
    if mode == "animated":
        update_data["viz_video_url"] = url
    else:
        update_data["viz_image_url"] = url

    client.table("math_blocks").update(update_data).eq("id", block_id).execute()


@app.function(
    image=manim_image,
    secrets=secrets,
    gpu="T4",
    timeout=120,
    memory=4096,
)
@modal.web_endpoint(method="POST")
def render_math_visual(request: dict) -> dict:
    """Generate a ManimGL visualization for a math block.

    Input: {block_id, latex_expr, explanation, env_type, context_before, context_after, mode}
    mode: "static" (PNG) or "animated" (GIF)
    Output: {image_data: base64, manim_code, mode, content_type} for preview.
    Upload/save happens separately via the Next.js save endpoint.
    """
    import base64
    import json
    import os

    block_id = request.get("block_id", "")
    latex_expr = request.get("latex_expr", "")
    env_type = request.get("env_type", "equation")
    context_before = request.get("context_before", "")
    context_after = request.get("context_after", "")
    mode = request.get("mode", "static")
    if mode not in ("static", "animated"):
        mode = "static"

    # Parse explanation JSON to readable text
    explanation_raw = request.get("explanation", "")
    explanation_text = ""
    if explanation_raw:
        try:
            exp = json.loads(explanation_raw) if isinstance(explanation_raw, str) else explanation_raw
            parts = []
            for key in ["what_it_computes", "symbol_meanings", "intuition", "derivation"]:
                if exp.get(key):
                    parts.append(f"{key}: {exp[key]}")
            explanation_text = "\n".join(parts)
        except (json.JSONDecodeError, TypeError):
            explanation_text = str(explanation_raw)

    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        return {"error": "GEMINI_API_KEY not configured", "manim_code": ""}

    manim_code = ""
    last_error = ""

    for attempt in range(_MAX_VIZ_RETRIES + 1):
        try:
            error_feedback = last_error if attempt > 0 else None
            manim_code = _call_viz_llm(
                api_key, latex_expr, env_type,
                explanation_text, context_before, context_after,
                mode=mode,
                error_feedback=error_feedback,
            )

            output_path = _render_scene(manim_code, block_id, mode=mode)

            with open(output_path, "rb") as f:
                image_b64 = base64.b64encode(f.read()).decode("ascii")

            content_type = "image/gif" if mode == "animated" else "image/png"
            return {
                "image_data": image_b64,
                "content_type": content_type,
                "manim_code": manim_code,
                "mode": mode,
            }

        except Exception as exc:
            last_error = str(exc)
            print(f"[viz] Attempt {attempt + 1} failed: {last_error}")
            if attempt == _MAX_VIZ_RETRIES:
                return {"error": last_error, "manim_code": manim_code}

    return {"error": "All attempts failed", "manim_code": manim_code}
