"""Local ManimGL visualization server.

Runs on your local GPU (no Modal/cloud needed).
Generates ManimGL scenes from math blocks on demand.

Start:
  python scripts/viz_server.py
  # Listens on http://localhost:8321

Then set in web/.env.local:
  MATH_VISUAL_MODAL_URL=http://localhost:8321/render
"""

from __future__ import annotations

import base64
import glob
import json
import os
import subprocess
import tempfile
from pathlib import Path

import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI(title="paper2md-viz")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# ---------------------------------------------------------------------------
# LLM prompt
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

_MAX_RETRIES = 2


# ---------------------------------------------------------------------------
# Core functions
# ---------------------------------------------------------------------------

def _call_llm(
    api_key: str,
    latex_expr: str,
    env_type: str,
    explanation_text: str,
    context_before: str,
    context_after: str,
    mode: str = "static",
    error_feedback: str | None = None,
) -> str:
    """Call Gemini to generate ManimGL Scene code."""
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
            "generationConfig": {"temperature": 0.3, "maxOutputTokens": 4096},
        },
        timeout=60,
    )
    resp.raise_for_status()
    data = resp.json()

    text = data["candidates"][0]["content"]["parts"][0]["text"].strip()
    # Strip markdown fences if present
    if text.startswith("```python"):
        text = text[len("```python"):].strip()
    if text.startswith("```"):
        text = text[3:].strip()
    if text.endswith("```"):
        text = text[:-3].strip()

    return text


def _render_scene(scene_code: str, block_id: str, mode: str = "static") -> str:
    """Render ManimGL scene locally. Returns path to output file."""
    output_dir = tempfile.mkdtemp(prefix="manim_")
    scene_file = os.path.join(output_dir, f"scene_{block_id}.py")
    with open(scene_file, "w") as f:
        f.write(scene_code)

    if mode == "animated":
        cmd = ["manimgl", scene_file, "FormulaScene", "-w", "-i", "--file_name", f"viz_{block_id}", "-l"]
        ext = ".gif"
        timeout = 60
    else:
        cmd = ["manimgl", scene_file, "FormulaScene", "-s", "-w", "--file_name", f"viz_{block_id}", "-l"]
        ext = ".png"
        timeout = 30

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
        cwd=output_dir,
        env={**os.environ, "VIDEO_DIR": output_dir},
    )

    if result.returncode != 0:
        raise RuntimeError(f"manimgl render failed:\n{result.stderr[-1500:]}")

    # Find output file
    found = sorted(glob.glob(f"{output_dir}/**/*{ext}", recursive=True), key=os.path.getmtime)
    if found:
        return found[-1]

    for root, _dirs, files in os.walk(output_dir):
        for fname in files:
            if fname.endswith(ext):
                return os.path.join(root, fname)

    raise FileNotFoundError(f"No {ext} output found in {output_dir}")


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------

class RenderRequest(BaseModel):
    block_id: str
    latex_expr: str
    explanation: str | dict | None = None
    env_type: str = "equation"
    context_before: str = ""
    context_after: str = ""
    mode: str = "static"


@app.post("/render")
def render_math_visual(req: RenderRequest) -> dict:
    """Generate a ManimGL visualization and return base64 image data."""
    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        return {"error": "GEMINI_API_KEY not configured", "manim_code": ""}

    mode = req.mode if req.mode in ("static", "animated") else "static"

    # Parse explanation
    explanation_text = ""
    if req.explanation:
        try:
            exp = json.loads(req.explanation) if isinstance(req.explanation, str) else req.explanation
            parts = []
            for key in ["what_it_computes", "symbol_meanings", "intuition", "derivation"]:
                if exp.get(key):
                    parts.append(f"{key}: {exp[key]}")
            explanation_text = "\n".join(parts)
        except (json.JSONDecodeError, TypeError):
            explanation_text = str(req.explanation)

    manim_code = ""
    last_error = ""

    for attempt in range(_MAX_RETRIES + 1):
        try:
            error_feedback = last_error if attempt > 0 else None
            manim_code = _call_llm(
                api_key, req.latex_expr, req.env_type,
                explanation_text, req.context_before, req.context_after,
                mode=mode, error_feedback=error_feedback,
            )

            output_path = _render_scene(manim_code, req.block_id, mode=mode)

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
            if attempt == _MAX_RETRIES:
                return {"error": last_error, "manim_code": manim_code}

    return {"error": "All attempts failed", "manim_code": manim_code}


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "gpu": True}


if __name__ == "__main__":
    import uvicorn
    print("Starting viz server on http://localhost:8321")
    print("Set MATH_VISUAL_MODAL_URL=http://localhost:8321/render in web/.env.local")
    uvicorn.run(app, host="0.0.0.0", port=8321)
