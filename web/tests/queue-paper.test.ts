import { describe, expect, it } from "vitest";
import { queuePaper } from "@/lib/supabase/queries";
import type { SupabaseClient } from "@supabase/supabase-js";
import type { Database } from "@/lib/supabase/types";

type Row = Record<string, unknown>;

/** In-memory `papers` table honouring the eq filters queuePaper uses. */
function fakeClient(rows: Row[]) {
  const from = () => {
    let payload: Row | null = null;
    const filters: [string, unknown][] = [];
    const matched = () => rows.filter((r) => filters.every(([c, v]) => r[c] === v));
    const q = {
      select: () => q,
      eq: (col: string, value: unknown) => (filters.push([col, value]), q),
      maybeSingle: async () => ({ data: matched()[0] ?? null, error: null }),
      update: (p: Row) => ((payload = p), q),
      insert: async (p: Row) => (rows.push(p), { error: null }),
      then: (resolve: (v: { error: null }) => void) => {
        if (payload) matched().forEach((r) => Object.assign(r, payload));
        resolve({ error: null });
      },
    };
    return q;
  };
  return { from } as unknown as SupabaseClient<Database>;
}

describe("queuePaper", () => {
  it("requeues a paper that previously failed", async () => {
    const rows: Row[] = [{ arxiv_id: "2301.07984", status: "error", error_msg: "boom" }];

    const result = await queuePaper(fakeClient(rows), "2301.07984");

    expect(result).toEqual({ queued: true, existing: false, requeued: true });
    expect(rows[0]).toMatchObject({ status: "pending", error_msg: null });
  });

  it("leaves papers that are not in error untouched", async () => {
    for (const status of ["pending", "processing", "complete", "explaining"]) {
      const rows: Row[] = [{ arxiv_id: "2301.07984", status }];

      const result = await queuePaper(fakeClient(rows), "2301.07984");

      expect(result).toEqual({ queued: false, existing: true, requeued: false });
      expect(rows[0].status).toBe(status);
    }
  });
});
