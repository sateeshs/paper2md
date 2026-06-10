/**
 * Supabase browser client — for use in Client Components ('use client').
 *
 * Uses the anon key (read-only, safe to expose).
 * Creates a singleton to avoid multiple GoTrue instances.
 */

import { createBrowserClient } from "@supabase/ssr";
import type { Database } from "./types";

let _client: ReturnType<typeof createBrowserClient<Database>> | null = null;

export function createClient() {
  if (_client) return _client;

  _client = createBrowserClient<Database>(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY!
  );

  return _client;
}
