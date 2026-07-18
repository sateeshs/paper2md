"use client";

import { useState, useMemo } from "react";
import type { Paper } from "@/lib/supabase/types";
import { PaperRow } from "@/components/PaperRow";

interface PapersListProps {
  papers: Paper[];
  total: number;
  isSearch: boolean;
  searchQuery?: string;
}

export function PapersList({ papers, total, isSearch, searchQuery }: PapersListProps) {
  const [filter, setFilter] = useState("");

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
        <div className="text-center py-10 text-zinc-400">
          <p className="text-sm">No papers match "{filter}"</p>
        </div>
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
