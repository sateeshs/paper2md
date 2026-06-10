/**
 * Supabase server client — for use in Server Components, Route Handlers,
 * and Server Actions.
 *
 * Must be called inside a request context (reads cookies).
 * Creates a new instance per request (SSR requirement).
 */

import { createServerClient } from "@supabase/ssr";
import { createClient as createSupabaseClient } from "@supabase/supabase-js";
import { cookies } from "next/headers";
import type { Database } from "./types";

export async function createClient() {
  const cookieStore = await cookies();

  return createServerClient<Database>(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY!,
    {
      cookies: {
        getAll() {
          return cookieStore.getAll();
        },
        // This app is read-only — no auth cookie mutations needed
        setAll() {},
      },
    }
  );
}

/**
 * Cookie-free client for use in generateStaticParams and other
 * build-time contexts where no request scope is available.
 */
export function createStaticClient() {
  return createSupabaseClient<Database>(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY!
  );
}

/**
 * Service-role client — bypasses RLS. Use only in trusted server-side code
 * (route handlers). Never expose to the browser.
 */
export function createServiceClient() {
  return createSupabaseClient<Database>(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.SUPABASE_SERVICE_ROLE_KEY!
  );
}
