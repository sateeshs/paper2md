import { createClient } from "@supabase/supabase-js";

export const runtime = "edge";
export const dynamic = "force-dynamic";

const POLL_MS = 4_000;
const MAX_MS = 10 * 60 * 1000; // 10 minutes (SAT agent is a single LLM call)

export async function GET(
  _req: Request,
  { params }: { params: Promise<{ session_id: string }> }
) {
  const { session_id } = await params;

  const supabase = createClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.SUPABASE_SERVICE_ROLE_KEY!
  );

  const encoder = new TextEncoder();

  const stream = new ReadableStream({
    async start(controller) {
      const send = (data: object) => {
        controller.enqueue(encoder.encode(`data: ${JSON.stringify(data)}\n\n`));
      };

      const deadline = Date.now() + MAX_MS;
      let lastStatus = "";

      while (Date.now() < deadline) {
        const { data } = await supabase
          .from("sat_sessions")
          .select("status, explanation, step_by_step, key_concepts, hints, common_mistakes, sat_strategy, answer, agent_model, error_msg")
          .eq("id", session_id)
          .maybeSingle();

        const status = data?.status ?? "pending";

        if (status !== lastStatus) {
          lastStatus = status;
          send({ status, ...(status === "complete" ? data : {}) });
        }

        if (status === "complete" || status === "error") {
          if (status === "error") {
            send({ status: "error", error_msg: data?.error_msg ?? null });
          }
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
