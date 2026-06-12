import { createClient } from "@supabase/supabase-js";
import type { Database } from "@/lib/supabase/types";

export const runtime = "edge";
export const dynamic = "force-dynamic";

// Poll interval and max wait time
const POLL_MS = 4_000;
const MAX_MS = 15 * 60 * 1000; // 15 minutes

export async function GET(
  _req: Request,
  { params }: { params: Promise<{ arxiv_id: string }> }
) {
  const { arxiv_id } = await params;
  // Use service client directly — avoids next/headers import in Edge Runtime
  const supabase = createClient<Database>(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.SUPABASE_SERVICE_ROLE_KEY!
  );

  const encoder = new TextEncoder();

  const stream = new ReadableStream({
    async start(controller) {
      const send = (status: string, title?: string | null) => {
        const payload = JSON.stringify({ status, title: title ?? null });
        controller.enqueue(encoder.encode(`data: ${payload}\n\n`));
      };

      const deadline = Date.now() + MAX_MS;
      let lastStatus = "";

      while (Date.now() < deadline) {
        const { data } = await supabase
          .from("papers")
          .select("status, title")
          .eq("arxiv_id", arxiv_id)
          .maybeSingle();

        const status = data?.status ?? "pending";
        const title = data?.title ?? null;

        if (status !== lastStatus) {
          lastStatus = status;
          send(status, title);
        }

        if (status === "complete" || status === "error") {
          break;
        }

        await new Promise((r) => setTimeout(r, POLL_MS));
      }

      controller.close();
    },
  });

  return new Response(stream, {
    headers: {
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache",
      Connection: "keep-alive",
    },
  });
}
