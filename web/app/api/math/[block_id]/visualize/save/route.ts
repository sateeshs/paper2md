import { NextResponse } from "next/server";
import { createServiceClient } from "@/lib/supabase/server";

export const runtime = "nodejs";

type VizMode = "static" | "animated";

export async function POST(
  req: Request,
  { params }: { params: Promise<{ block_id: string }> }
): Promise<NextResponse> {
  const { block_id } = await params;

  let body: { image_data?: string; manim_code?: string; mode?: string; content_type?: string };
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ error: "Invalid request body" }, { status: 400 });
  }

  const { image_data, manim_code, content_type } = body;
  const mode: VizMode = body.mode === "animated" ? "animated" : "static";

  if (!image_data) {
    return NextResponse.json({ error: "Missing image_data" }, { status: 400 });
  }

  const supabase = await createServiceClient();

  // 1. Upload base64 to Supabase Storage (math-visuals bucket)
  const ext = mode === "animated" ? "gif" : "png";
  const mimeType = content_type ?? (mode === "animated" ? "image/gif" : "image/png");
  const objectPath = `${block_id}.${ext}`;

  const fileBuffer = Buffer.from(image_data, "base64");

  const { error: uploadError } = await supabase.storage
    .from("math-visuals")
    .upload(objectPath, fileBuffer, {
      contentType: mimeType,
      upsert: true,
    });

  if (uploadError) {
    return NextResponse.json(
      { error: `Storage upload failed: ${uploadError.message}` },
      { status: 500 }
    );
  }

  const { data: urlData } = supabase.storage
    .from("math-visuals")
    .getPublicUrl(objectPath);

  const publicUrl = urlData.publicUrl;

  // 2. Update math_blocks row
  const updateData: Record<string, string | null> = {
    viz_manim_code: manim_code ?? null,
  };
  if (mode === "animated") {
    updateData.viz_video_url = publicUrl;
  } else {
    updateData.viz_image_url = publicUrl;
  }

  const { error: dbError } = await supabase
    .from("math_blocks")
    .update(updateData)
    .eq("id", block_id);

  if (dbError) {
    return NextResponse.json(
      { error: `DB update failed: ${dbError.message}` },
      { status: 500 }
    );
  }

  const urlKey = mode === "animated" ? "video_url" : "image_url";
  return NextResponse.json({ [urlKey]: publicUrl, saved: true });
}
