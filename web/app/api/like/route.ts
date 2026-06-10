import { NextResponse } from "next/server";
import { createServiceClient } from "@/lib/supabase/server";
import { generatePaperMarkdown, commitMarkdownToGitHub } from "@/lib/github-publish";
import type { SectionWithMath } from "@/lib/supabase/types";

export async function POST(request: Request): Promise<NextResponse> {
  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: "Invalid JSON" }, { status: 400 });
  }

  const arxivId =
    typeof body === "object" && body !== null
      ? (body as Record<string, unknown>).arxiv_id
      : undefined;

  if (typeof arxivId !== "string" || !arxivId.trim()) {
    return NextResponse.json({ error: "arxiv_id required" }, { status: 400 });
  }

  const client = createServiceClient();

  // 1. Fetch paper
  const { data: paper, error: paperErr } = await client
    .from("papers")
    .select("*")
    .eq("arxiv_id", arxivId.trim())
    .maybeSingle();

  if (paperErr) return NextResponse.json({ error: paperErr.message }, { status: 500 });
  if (!paper)   return NextResponse.json({ error: "Paper not found" }, { status: 404 });
  if (paper.status !== "complete") {
    return NextResponse.json({ error: "Paper not complete yet" }, { status: 400 });
  }

  // 2. Already liked — idempotent
  if (paper.liked && paper.github_md_url) {
    return NextResponse.json(
      { liked: true, github_md_url: paper.github_md_url },
      { status: 200 }
    );
  }

  // 3. Fetch sections + math blocks
  const { data: sections, error: secErr } = await client
    .from("sections")
    .select("*, math_blocks(*)")
    .eq("paper_id", paper.id)
    .order("order_idx")
    .order("order_idx", { referencedTable: "math_blocks" });

  if (secErr) return NextResponse.json({ error: secErr.message }, { status: 500 });

  // 4. Generate markdown
  const markdown = generatePaperMarkdown(paper, (sections ?? []) as SectionWithMath[]);

  // 5. Commit to GitHub
  const commit = await commitMarkdownToGitHub(arxivId.trim(), markdown);
  if (!commit.ok) {
    return NextResponse.json({ error: commit.error }, { status: 502 });
  }

  // 6. Update paper row
  const { error: updateErr } = await client
    .from("papers")
    .update({
      liked: true,
      liked_at: new Date().toISOString(),
      github_md_url: commit.url,
    })
    .eq("id", paper.id);

  if (updateErr) return NextResponse.json({ error: updateErr.message }, { status: 500 });

  return NextResponse.json({ liked: true, github_md_url: commit.url }, { status: 200 });
}
