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
    R2_ACCOUNT_ID="<cloudflare-account-id>" \\
    R2_ACCESS_KEY_ID="<r2-api-token-access-key>" \\
    R2_SECRET_ACCESS_KEY="<r2-api-token-secret>" \\
    R2_BUCKET_NAME="math-visuals" \\
    R2_PUBLIC_URL="https://<bucket>.r2.dev"
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
        "boto3>=1.35.0",       # S3-compatible client for Cloudflare R2
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
            await asyncio.to_thread(process_arxiv_id, arxiv_id, push_supabase=True)
            print(f"[batch] Done: {arxiv_id}")
        except Exception as exc:
            print(f"[batch] Error processing {arxiv_id}: {exc}")


# ---------------------------------------------------------------------------
# Math visualization — ManimGL headless render
# ---------------------------------------------------------------------------

MANIM_SCENE_SYSTEM_PROMPT = """\
You are a ManimGL code generator. Given a LaTeX math expression and its explanation,
generate a self-contained Python scene that visually illustrates the formula.

## Rules
- The scene class MUST be named `FormulaScene`
- Import everything from manimlib: `from manimlib import *`
- For STATIC mode: use ONLY `self.add()` calls — no `self.play()`, no animations
- For ANIMATED mode: use `self.play()` with animations like Write, FadeIn, Transform, ShowCreation
  Keep animations SHORT (3-5 seconds total). Use `self.wait(0.5)` between steps.
- The mode will be specified in the user message
- Resolution is 1280×720; the coordinate system spans roughly x=[-7,7] y=[-4,4]
- Use a dark background (ManimGL default #333333)
- Place the rendered LaTeX formula at the top using `Tex()` or `MathTex()`
- Below the formula, add visual aids: annotated symbols, geometric diagrams,
  function plots, matrix visualizations, or conceptual diagrams as appropriate
- Use colors to distinguish different parts: BLUE, YELLOW, GREEN, RED, TEAL, ORANGE
- Use `Brace`, `Arrow`, `Text`, `SurroundingRectangle` for annotations
- Keep the layout clean and readable — don't overcrowd

## Available ManimGL classes (use only these)
- `Tex(r"\\LaTeX")`, `MathTex(r"x^2")`, `Text("plain text")`
- `NumberPlane()`, `Axes()`, `FunctionGraph(lambda x: x**2)`
- `Circle()`, `Square()`, `Rectangle()`, `Line()`, `Arrow()`, `Vector()`
- `Brace(mobject, direction)`, `SurroundingRectangle(mobject)`
- `VGroup(*mobjects)`, `Dot()`, `DashedLine()`
- `Matrix([[1,2],[3,4]])`, `IntegerMatrix()`
- Positioning: `.to_edge(UP)`, `.to_corner(UL)`, `.next_to(obj, DOWN)`
- Colors: BLUE, YELLOW, GREEN, RED, TEAL, ORANGE, WHITE, GREY

## Example 1: Simple equation
```python
from manimlib import *

class FormulaScene(Scene):
    def construct(self):
        # Main formula
        formula = MathTex(r"E = mc^2")
        formula.scale(1.5).to_edge(UP, buff=1.0)
        self.add(formula)

        # Annotations
        labels = VGroup(
            Text("Energy", font_size=24, color=BLUE),
            Text("Mass", font_size=24, color=GREEN),
            Text("Speed of light²", font_size=24, color=YELLOW),
        )

        e_brace = Brace(formula[0][0], DOWN, color=BLUE)
        m_brace = Brace(formula[0][2], DOWN, color=GREEN)
        c_brace = Brace(formula[0][3:], DOWN, color=YELLOW)

        labels[0].next_to(e_brace, DOWN)
        labels[1].next_to(m_brace, DOWN)
        labels[2].next_to(c_brace, DOWN)

        self.add(e_brace, m_brace, c_brace, *labels)
```

## Example 2: Function with plot
```python
from manimlib import *

class FormulaScene(Scene):
    def construct(self):
        formula = MathTex(r"f(x) = \\sin(x)")
        formula.scale(1.3).to_edge(UP, buff=0.5)
        self.add(formula)

        axes = Axes(x_range=[-4, 4], y_range=[-1.5, 1.5], width=10, height=4)
        axes.shift(DOWN * 0.5)
        graph = axes.get_graph(lambda x: np.sin(x), color=BLUE)
        axes_labels = axes.get_axis_labels(x_label="x", y_label="f(x)")
        self.add(axes, graph, axes_labels)
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


def _upload_to_r2(file_path: str, block_id: str, mode: str = "static") -> str:
    """Upload rendered file to Cloudflare R2 and return public URL.

    Requires env vars: R2_ACCOUNT_ID, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY, R2_BUCKET_NAME.
    Public access via the R2 public bucket URL (enable in Cloudflare dashboard).
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

    # Public URL via R2 public access (r2.dev subdomain or custom domain)
    public_domain = os.environ.get(
        "R2_PUBLIC_URL",
        f"https://pub-{account_id}.r2.dev/{bucket}",
    ).rstrip("/")
    return f"{public_domain}/{object_key}"


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
    Output: {image_url/video_url, manim_code} or {error, manim_code}
    """
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
            url = _upload_to_r2(output_path, block_id, mode=mode)
            _update_math_block(block_id, url, manim_code, mode=mode)

            url_key = "video_url" if mode == "animated" else "image_url"
            return {url_key: url, "manim_code": manim_code, "mode": mode}

        except Exception as exc:
            last_error = str(exc)
            print(f"[viz] Attempt {attempt + 1} failed: {last_error}")
            if attempt == _MAX_VIZ_RETRIES:
                return {"error": last_error, "manim_code": manim_code}

    return {"error": "All attempts failed", "manim_code": manim_code}
