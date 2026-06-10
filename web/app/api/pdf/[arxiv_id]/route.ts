import { NextRequest, NextResponse } from "next/server";

// Proxy arXiv PDFs to remove X-Frame-Options: DENY so we can embed them in iframes.
export async function GET(
  _req: NextRequest,
  { params }: { params: Promise<{ arxiv_id: string }> }
): Promise<Response> {
  const { arxiv_id } = await params;

  // Basic validation — only bare IDs allowed (no path traversal)
  if (!/^\d{4}\.\d{4,5}(v\d+)?$/.test(arxiv_id)) {
    return new NextResponse("Invalid arXiv ID", { status: 400 });
  }

  const pdfUrl = `https://arxiv.org/pdf/${arxiv_id}`;

  let upstream: Response;
  try {
    upstream = await fetch(pdfUrl, {
      headers: {
        "User-Agent": "paper2md/1.0",
        Accept: "application/pdf",
      },
      redirect: "follow",
    });
  } catch (err) {
    return new NextResponse(`Fetch failed: ${String(err)}`, { status: 502 });
  }

  if (!upstream.ok) {
    return new NextResponse(`arXiv returned ${upstream.status}`, {
      status: upstream.status,
    });
  }

  return new Response(upstream.body, {
    status: 200,
    headers: {
      "Content-Type": "application/pdf",
      "Content-Disposition": "inline",
      // Cache for 1 day — PDFs don't change once published
      "Cache-Control": "public, max-age=86400, immutable",
    },
  });
}
