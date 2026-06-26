import { createClient } from "@supabase/supabase-js";
import { NextResponse } from "next/server";
import type { Database } from "@/lib/supabase/types";

export const runtime = "edge";
export const dynamic = "force-dynamic";

/**
 * GET /api/status/batch?ids=1409.0473,1301.3666,...
 *
 * Returns a map of { arxiv_id → status } for all known papers.
 * Unknown IDs are omitted from the response.
 * Max 100 IDs per request.
 */
export async function GET(req: Request) {
  const { searchParams } = new URL(req.url);
  const raw = searchParams.get("ids") ?? "";

  const ids = raw
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean)
    .slice(0, 100); // cap to avoid abuse

  if (ids.length === 0) {
    return NextResponse.json({});
  }

  const supabase = createClient<Database>(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.SUPABASE_SERVICE_ROLE_KEY!
  );

  const { data, error } = await supabase
    .from("papers")
    .select("arxiv_id, status")
    .in("arxiv_id", ids);

  if (error) {
    return NextResponse.json({ error: error.message }, { status: 500 });
  }

  const result: Record<string, string> = {};
  for (const row of data ?? []) {
    if (row.arxiv_id) result[row.arxiv_id] = row.status;
  }

  return NextResponse.json(result);
}
