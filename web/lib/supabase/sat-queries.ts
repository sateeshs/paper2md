/**
 * Supabase helpers for sat_sessions table.
 */

import type { SupabaseClient } from "@supabase/supabase-js";

export type SATSubject = "math" | "english" | "reading";

export interface SATSession {
  id: string;
  question: string;
  subject: SATSubject;
  user_context: string | null;
  status: "pending" | "processing" | "complete" | "error";
  explanation: string | null;
  step_by_step: string | null;
  key_concepts: string | null;
  hints: string | null;
  common_mistakes: string | null;
  sat_strategy: string | null;
  answer: string | null;
  agent_model: string | null;
  error_msg: string | null;
  created_at: string;
  updated_at: string;
}

/** Insert a new pending SAT session and return its id. */
export async function queueSATSession(
  client: SupabaseClient,
  question: string,
  subject: SATSubject,
  userContext?: string
): Promise<string> {
  const { data, error } = await client
    .from("sat_sessions")
    .insert({
      question,
      subject,
      user_context: userContext || null,
      status: "pending",
    })
    .select("id")
    .single();

  if (error) throw new Error(`queueSATSession: ${error.message}`);
  return data.id;
}

/** Return the current row for a session (for SSE polling). */
export async function getSATSession(
  client: SupabaseClient,
  sessionId: string
): Promise<SATSession | null> {
  const { data, error } = await client
    .from("sat_sessions")
    .select("*")
    .eq("id", sessionId)
    .maybeSingle();

  if (error) throw new Error(`getSATSession: ${error.message}`);
  return data as SATSession | null;
}
