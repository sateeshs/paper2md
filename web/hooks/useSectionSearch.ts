"use client";

import { useEffect, useMemo, useState } from "react";
import { parseSectionQuery } from "@/lib/section-search";
import type { SectionWithMathCount } from "@/lib/supabase/types";

const DEBOUNCE_MS = 250;

export interface SectionSearchState {
  /** Parsed terms, or null when the query is empty / too short to search. */
  terms: string[] | null;
  results: SectionWithMathCount[];
  total: number;
  searching: boolean;
  error: string | null;
}

/** Search every section of a paper server-side — the list itself is paged. */
export function useSectionSearch(arxivId: string, query: string): SectionSearchState {
  const terms = useMemo(() => parseSectionQuery(query), [query]);
  const termsKey = terms?.join(" ") ?? "";
  const [state, setState] = useState<Omit<SectionSearchState, "terms">>({
    results: [],
    total: 0,
    searching: false,
    error: null,
  });

  useEffect(() => {
    if (!termsKey) {
      setState({ results: [], total: 0, searching: false, error: null });
      return;
    }
    setState((prev) => ({ ...prev, searching: true, error: null }));
    const controller = new AbortController();
    const timer = setTimeout(async () => {
      try {
        const res = await fetch(
          `/api/papers/${arxivId}/sections?q=${encodeURIComponent(termsKey)}`,
          { signal: controller.signal }
        );
        if (!res.ok) throw new Error(`Search failed (${res.status})`);
        const { sections, total } = (await res.json()) as {
          sections: SectionWithMathCount[];
          total: number;
        };
        setState({ results: sections, total, searching: false, error: null });
      } catch (err) {
        if (controller.signal.aborted) return;
        setState({
          results: [],
          total: 0,
          searching: false,
          error: err instanceof Error ? err.message : "Search failed",
        });
      }
    }, DEBOUNCE_MS);
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [arxivId, termsKey]);

  return { terms, ...state };
}
