import { NextResponse } from "next/server";
import { VIEWABLE_STATUSES } from "@/lib/paper-status";
import { createServiceClient } from "@/lib/supabase/server";
import { getSectionsPaged, searchSections } from "@/lib/supabase/queries";
import { parseSectionQuery } from "@/lib/section-search";

export async function GET(
  req: Request,
  { params }: { params: Promise<{ arxiv_id: string }> }
): Promise<NextResponse> {
  const { arxiv_id } = await params;
  const url = new URL(req.url);
  const page = Math.max(1, parseInt(url.searchParams.get("page") ?? "1", 10));
  const rawQuery = url.searchParams.get("q");
  const terms = parseSectionQuery(rawQuery);
  if (rawQuery !== null && terms === null) {
    return NextResponse.json({ error: "Query must contain a term of at least 2 characters" }, { status: 400 });
  }

  const supabase = createServiceClient();

  const { data: paper } = await supabase
    .from("papers")
    .select("id")
    .eq("arxiv_id", arxiv_id)
    .in("status", [...VIEWABLE_STATUSES])
    .maybeSingle();

  if (!paper) {
    return NextResponse.json({ error: "Not found" }, { status: 404 });
  }

  const result = terms
    ? await searchSections(supabase, paper.id, terms)
    : await getSectionsPaged(supabase, paper.id, page);
  return NextResponse.json(result);
}
