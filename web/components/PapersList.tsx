"use client";

import { useState, useMemo, useEffect } from "react";
import type { Paper } from "@/lib/supabase/types";
import { PaperRow } from "@/components/PaperRow";

interface PapersListProps {
  papers: Paper[];
  total: number;
  isSearch: boolean;
  searchQuery?: string;
}

/** Minimum characters before the filter is worth a round-trip to the server. */
const MIN_SERVER_QUERY_LENGTH = 2;
const SERVER_SEARCH_DEBOUNCE_MS = 250;

type ServerSearchState =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "done"; papers: Paper[] }
  | { status: "error" };

export function PapersList({ papers, total, isSearch, searchQuery }: PapersListProps) {
  const [filter, setFilter] = useState("");
  const [serverSearch, setServerSearch] = useState<ServerSearchState>({ status: "idle" });

  const filtered = useMemo(() => {
    if (!filter.trim()) return papers;
    const lower = filter.toLowerCase();
    return papers.filter((p) => {
      const title = p.title?.toLowerCase() ?? "";
      const arxiv = p.arxiv_id?.toLowerCase() ?? "";
      const authors = p.authors?.join(" ").toLowerCase() ?? "";
      return title.includes(lower) || arxiv.includes(lower) || authors.includes(lower);
    });
  }, [papers, filter]);

  // Nothing on this page matches — ask the server whether another page does.
  const query = filter.trim();
  const shouldSearchServer = filtered.length === 0 && query.length >= MIN_SERVER_QUERY_LENGTH;

  useEffect(() => {
    if (!shouldSearchServer) {
      setServerSearch({ status: "idle" });
      return;
    }

    const controller = new AbortController();
    const timer = setTimeout(async () => {
      setServerSearch({ status: "loading" });
      try {
        const res = await fetch(`/api/search?full=1&q=${encodeURIComponent(query)}`, {
          signal: controller.signal,
        });
        if (!res.ok) throw new Error(`search failed: ${res.status}`);
        setServerSearch({ status: "done", papers: (await res.json()) as Paper[] });
      } catch {
        if (controller.signal.aborted) return;
        setServerSearch({ status: "error" });
      }
    }, SERVER_SEARCH_DEBOUNCE_MS);

    return () => {
      controller.abort();
      clearTimeout(timer);
    };
  }, [shouldSearchServer, query]);

  // Drop anything already rendered on this page — only off-page hits are news.
  const localIds = useMemo(() => new Set(papers.map((p) => p.id)), [papers]);
  const offPageResults =
    serverSearch.status === "done"
      ? serverSearch.papers.filter((p) => !localIds.has(p.id))
      : [];

  return (
    <section>
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-xs font-semibold text-zinc-400 uppercase tracking-widest">
          {isSearch ? `Results for "${searchQuery}"` : "Recent papers"}
        </h2>
        {!isSearch && total > 0 && (
          <span className="text-xs text-zinc-400">
            {total} paper{total !== 1 ? "s" : ""}
          </span>
        )}
      </div>

      {/* Inline filter */}
      {papers.length > 0 && (
        <div className="mb-3">
          <input
            type="text"
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            placeholder="Filter by title, arXiv ID, or author…"
            className="w-full px-3 py-2 text-sm border border-zinc-200 rounded-lg bg-zinc-50 placeholder:text-zinc-400 focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-400 focus:bg-white transition-colors"
          />
        </div>
      )}

      {papers.length === 0 ? (
        <div className="text-center py-16 text-zinc-400">
          <p className="text-4xl mb-3">📄</p>
          <p className="text-sm">No papers yet. Queue one above to get started.</p>
        </div>
      ) : filtered.length === 0 ? (
        <ServerFallback filter={filter} status={serverSearch.status} papers={offPageResults} />
      ) : (
        <ul className="divide-y divide-zinc-100 bg-white rounded-xl border border-zinc-200 overflow-hidden">
          {filtered.map((paper) => (
            <PaperRow key={paper.id} paper={paper} />
          ))}
        </ul>
      )}
    </section>
  );
}

interface ServerFallbackProps {
  filter: string;
  status: ServerSearchState["status"];
  papers: Paper[];
}

/** Shown when the loaded page has no match — reports what the rest of the library holds. */
function ServerFallback({ filter, status, papers }: ServerFallbackProps) {
  if (status === "loading") {
    return (
      <div className="text-center py-10 text-zinc-400">
        <p className="text-sm">Searching all papers for &ldquo;{filter}&rdquo;…</p>
      </div>
    );
  }

  if (status === "done" && papers.length > 0) {
    return (
      <div>
        <p className="text-xs text-zinc-400 mb-2">
          Not on this page — {papers.length} match{papers.length !== 1 ? "es" : ""} elsewhere
          in the library
        </p>
        <ul className="divide-y divide-zinc-100 bg-white rounded-xl border border-zinc-200 overflow-hidden">
          {papers.map((paper) => (
            <PaperRow key={paper.id} paper={paper} />
          ))}
        </ul>
      </div>
    );
  }

  if (status === "error") {
    return (
      <div className="text-center py-10 text-zinc-400">
        <p className="text-sm">No papers on this page match &ldquo;{filter}&rdquo;</p>
        <p className="text-xs mt-1">Searching the rest of the library failed — try again.</p>
      </div>
    );
  }

  return (
    <div className="text-center py-10 text-zinc-400">
      <p className="text-sm">No papers match &ldquo;{filter}&rdquo;</p>
    </div>
  );
}
