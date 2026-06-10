import { NextResponse } from "next/server";
import { createClient } from "@/lib/supabase/server";
import { queuePaper } from "@/lib/supabase/queries";
import { extractArxivId } from "@/lib/arxiv-id";
import { triggerProcessing } from "@/lib/github-dispatch";

export async function POST(request: Request): Promise<NextResponse> {
  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: "Invalid JSON" }, { status: 400 });
  }

  if (
    typeof body !== "object" ||
    body === null ||
    typeof (body as Record<string, unknown>).arxiv_id !== "string"
  ) {
    return NextResponse.json(
      { error: "arxiv_id is required and must be a string" },
      { status: 400 }
    );
  }

  const b = body as Record<string, unknown>;
  const rawInput = (b.arxiv_id as string).trim();
  const arxivId = extractArxivId(rawInput);
  const title = typeof b.title === "string" && b.title.trim() ? b.title.trim() : undefined;

  if (!arxivId) {
    return NextResponse.json(
      { error: "Invalid ArXiv ID or URL. Expected e.g. 2301.07984 or https://arxiv.org/abs/2301.07984" },
      { status: 400 }
    );
  }

  const client = await createClient();
  const result = await queuePaper(client, arxivId, title);

  // Fire workflow_dispatch for both new queues and re-trigger requests on existing pending papers
  const dispatch = await triggerProcessing(arxivId);

  return NextResponse.json(
    { ...result, dispatch },
    { status: result.queued ? 201 : 200 }
  );
}
