import { NextResponse } from "next/server";
import { createClient } from "@supabase/supabase-js";
import { queueSATSession, type SATSubject } from "@/lib/supabase/sat-queries";
import { triggerSATSession } from "@/lib/sat-dispatch";

export async function POST(req: Request) {
  let body: { question?: string; subject?: string; user_context?: string };
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ error: "Invalid JSON" }, { status: 400 });
  }

  const { question, subject, user_context } = body;

  if (!question?.trim()) {
    return NextResponse.json({ error: "question is required" }, { status: 400 });
  }
  if (!["math", "english", "reading"].includes(subject ?? "")) {
    return NextResponse.json(
      { error: "subject must be math, english, or reading" },
      { status: 400 }
    );
  }

  // Use service role to bypass RLS for the insert
  const client = createClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.SUPABASE_SERVICE_ROLE_KEY!
  );

  let sessionId: string;
  try {
    sessionId = await queueSATSession(
      client,
      question.trim(),
      subject as SATSubject,
      user_context?.trim() || undefined
    );
  } catch (err) {
    console.error("[sat/queue] DB error:", err);
    return NextResponse.json({ error: "Failed to queue session" }, { status: 500 });
  }

  // Fire-and-forget — don't block response on GitHub dispatch
  triggerSATSession(sessionId).then((result) => {
    if (!result.triggered) {
      console.warn("[sat/queue] Dispatch failed:", result.reason);
    }
  });

  return NextResponse.json({ session_id: sessionId }, { status: 201 });
}
