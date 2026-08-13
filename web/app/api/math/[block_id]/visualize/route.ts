import { NextResponse } from "next/server";
import { createServiceClient } from "@/lib/supabase/server";

// Modal render can take 30-60s (cold start + GPU render)
export const maxDuration = 120;
export const runtime = "nodejs";

type VizMode = "static" | "animated";

export async function POST(
  req: Request,
  { params }: { params: Promise<{ block_id: string }> }
): Promise<NextResponse> {
  const { block_id } = await params;

  let mode: VizMode = "static";
  try {
    const body = await req.json();
    if (body.mode === "animated") mode = "animated";
  } catch {
    // body parse failure — proceed with static default
  }

  // 1. Fetch math block data (core columns that always exist)
  const supabase = await createServiceClient();
  const { data: block, error } = await supabase
    .from("math_blocks")
    .select(
      "latex_expr, explanation, env_type, context_before, context_after"
    )
    .eq("id", block_id)
    .maybeSingle();

  if (error || !block) {
    return NextResponse.json(
      { error: error?.message ?? "Math block not found" },
      { status: 404 }
    );
  }

  // Try cache lookup (viz columns may not exist if migration 006 hasn't run)
  const { data: vizCache } = await supabase
    .from("math_blocks")
    .select("viz_image_url, viz_video_url, viz_manim_code")
    .eq("id", block_id)
    .maybeSingle();

  if (vizCache) {
    const cachedUrl =
      mode === "animated" ? vizCache.viz_video_url : vizCache.viz_image_url;
    if (cachedUrl) {
      const urlKey = mode === "animated" ? "video_url" : "image_url";
      return NextResponse.json({
        [urlKey]: cachedUrl,
        manim_code: vizCache.viz_manim_code,
        mode,
        saved: true,
      });
    }
  }

  // 2. Gate on Modal endpoint availability
  const modalUrl = process.env.MATH_VISUAL_MODAL_URL;
  if (!modalUrl) {
    return NextResponse.json(
      { error: "Visualization service not configured — set MATH_VISUAL_MODAL_URL" },
      { status: 503 }
    );
  }

  // 3. Call Modal — returns base64 image data (no upload)
  try {
    const res = await fetch(modalUrl, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        block_id,
        latex_expr: block.latex_expr,
        explanation: block.explanation,
        env_type: block.env_type,
        context_before: block.context_before,
        context_after: block.context_after,
        mode,
      }),
    });

    const result = await res.json();

    if (!res.ok || result.error) {
      return NextResponse.json(
        { error: result.error ?? "Visualization render failed", manim_code: result.manim_code },
        { status: 422 }
      );
    }

    // Pass through base64 preview (not yet saved)
    return NextResponse.json({ ...result, saved: false });
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    return NextResponse.json(
      { error: `Modal call failed: ${message}` },
      { status: 502 }
    );
  }
}
