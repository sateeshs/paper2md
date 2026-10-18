import { NextResponse } from "next/server";
import { createClient } from "@/lib/supabase/server";
import { searchPapers } from "@/lib/supabase/queries";

export async function GET(request: Request): Promise<NextResponse> {
  const { searchParams } = new URL(request.url);
  const q = searchParams.get("q")?.trim() ?? "";
  // full=1 returns whole paper rows (used by the grid's server-side fallback);
  // the default trimmed shape feeds the header autocomplete.
  const full = searchParams.get("full") === "1";

  if (q.length < 2) {
    return NextResponse.json([]);
  }

  const client = await createClient();
  const papers = await searchPapers(client, q);

  if (full) {
    return NextResponse.json(papers);
  }

  return NextResponse.json(
    papers.map((p) => ({
      id: p.id,
      arxiv_id: p.arxiv_id,
      title: p.title,
      authors: p.authors?.slice(0, 2) ?? [],
    }))
  );
}
