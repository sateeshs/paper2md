import { NextResponse } from "next/server";
import { createServiceClient } from "@/lib/supabase/server";
import { getSectionsPaged } from "@/lib/supabase/queries";

export async function GET(
  req: Request,
  { params }: { params: Promise<{ arxiv_id: string }> }
): Promise<NextResponse> {
  const { arxiv_id } = await params;
  const url = new URL(req.url);
  const page = Math.max(1, parseInt(url.searchParams.get("page") ?? "1", 10));

  const supabase = createServiceClient();

  const { data: paper } = await supabase
    .from("papers")
    .select("id")
    .eq("arxiv_id", arxiv_id)
    .eq("status", "complete")
    .maybeSingle();

  if (!paper) {
    return NextResponse.json({ error: "Not found" }, { status: 404 });
  }

  const result = await getSectionsPaged(supabase, paper.id, page);
  return NextResponse.json(result);
}
