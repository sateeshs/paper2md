"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import type { PaperCitation, PaperWithSections, SectionWithMathCount } from "@/lib/supabase/types";
import { PdfPageViewer } from "@/components/PdfPageViewer";
import { LikeButton } from "@/components/LikeButton";
import { ExplanationsInProgress } from "@/components/ExplanationsInProgress";
import { CitationsPanel } from "@/components/CitationsPanel";
import { useSectionPageMap } from "@/hooks/useSectionPageMap";
import { useSectionSearch } from "@/hooks/useSectionSearch";
import { Highlighted } from "@/components/Highlighted";
import { snippetAround } from "@/lib/section-search";
import {
  PageBadge,
  SectionNumber,
  indentClass,
  titleWeightClass,
} from "@/components/SectionMeta";

interface PaperSplitViewProps {
  paper: PaperWithSections;
  arxivId: string;
  citations?: PaperCitation[];
  totalSections: number;
}

export function PaperSplitView({ paper, arxivId, citations = [], totalSections }: PaperSplitViewProps) {
  const [sections, setSections] = useState<SectionWithMathCount[]>(paper.sections ?? []);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(false);
  const [hasMore, setHasMore] = useState((paper.sections ?? []).length < totalSections);
  const sentinelRef = useRef<HTMLDivElement>(null);

  const [activeSectionId, setActiveSectionId] = useState<string | null>(null);
  const { pageMap, scanning } = useSectionPageMap(arxivId, sections);

  const [query, setQuery] = useState("");
  const search = useSectionSearch(arxivId, query);
  const isSearching = search.terms !== null;
  const visibleSections = isSearching ? search.results : sections;

  const targetPage = activeSectionId ? (pageMap.get(activeSectionId) ?? 1) : 1;

  const loadMore = useCallback(async (): Promise<void> => {
    if (loading || !hasMore) return;
    setLoading(true);
    try {
      const nextPage = page + 1;
      const res = await fetch(`/api/papers/${arxivId}/sections?page=${nextPage}`);
      if (!res.ok) return;
      const { sections: newSections, total } = (await res.json()) as {
        sections: SectionWithMathCount[];
        total: number;
      };
      setSections((prev) => {
        const existingIds = new Set(prev.map((s) => s.id));
        const deduped = newSections.filter((s) => !existingIds.has(s.id));
        const merged = [...prev, ...deduped];
        setHasMore(merged.length < total);
        return merged;
      });
      setPage(nextPage);
    } finally {
      setLoading(false);
    }
  }, [loading, hasMore, page, arxivId]);

  useEffect(() => {
    const el = sentinelRef.current;
    if (!el) return;
    const obs = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) void loadMore();
      },
      { rootMargin: "200px" }
    );
    obs.observe(el);
    return () => obs.disconnect();
  }, [loadMore]);

  return (
    <div className="flex h-full min-h-0 dark:bg-zinc-950 dark:text-zinc-100">
      {/* Left pane — sections list */}
      <div className="flex-1 min-w-0 overflow-y-auto px-6 py-8">
        <div className="max-w-2xl">
          {/* Paper header */}
          <div className="mb-6">
            <a href="/" className="text-xs text-zinc-400 hover:text-zinc-600 mb-3 inline-block">
              ← Home
            </a>
            <h1 className="text-2xl font-bold leading-snug">{paper.title}</h1>
            {paper.arxiv_id && (
              <p className="text-sm text-zinc-400 mt-1">arXiv:{paper.arxiv_id}</p>
            )}
            <ExplanationsInProgress status={paper.status} />
            <div className="mt-3">
              <LikeButton
                arxivId={paper.arxiv_id ?? ""}
                initialLiked={paper.liked ?? false}
                initialUrl={paper.github_md_url ?? null}
              />
            </div>
          </div>

          <div className="flex items-center justify-between mb-3">
            <h2 className="text-xs font-semibold text-zinc-400 uppercase tracking-widest">
              Sections
            </h2>
            {scanning && (
              <span className="text-xs text-zinc-400 animate-pulse">Indexing PDF…</span>
            )}
          </div>

          <div className="relative mb-2">
            <input
              type="search"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Escape") setQuery("");
              }}
              placeholder={`Search ${totalSections} sections by title or text…`}
              aria-label="Search sections"
              className="w-full rounded-lg border border-zinc-300 dark:border-zinc-700 bg-white dark:bg-zinc-900 px-4 py-2 text-sm shadow-sm placeholder:text-zinc-400 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
            />
          </div>

          {isSearching && (
            <p className="mb-3 text-xs text-zinc-400" aria-live="polite">
              {search.searching
                ? "Searching…"
                : search.error
                  ? search.error
                  : search.total > search.results.length
                    ? `Showing first ${search.results.length} of ${search.total} matching sections`
                    : `${search.total} matching section${search.total === 1 ? "" : "s"}`}
            </p>
          )}

          {visibleSections.length === 0 ? (
            !isSearching ? (
              <p className="text-sm text-zinc-400">No sections extracted.</p>
            ) : !search.searching && !search.error ? (
              <p className="text-sm text-zinc-400">No sections match &ldquo;{query.trim()}&rdquo;.</p>
            ) : null
          ) : (
            <ul className="space-y-1.5">
              {visibleSections.map((section) => (
                <SectionRow
                  key={section.id}
                  section={section}
                  arxivId={arxivId}
                  active={section.id === activeSectionId}
                  pdfPage={pageMap.get(section.id)}
                  terms={search.terms ?? []}
                  onHover={() => setActiveSectionId(section.id)}
                />
              ))}
            </ul>
          )}

          {/* Infinite scroll loading indicator */}
          {!isSearching && loading && (
            <div className="flex justify-center py-6">
              <span className="flex gap-1">
                {[0, 1, 2].map((i) => (
                  <span
                    key={i}
                    className="h-2 w-2 rounded-full bg-zinc-300 dark:bg-zinc-600 animate-bounce"
                    style={{ animationDelay: `${i * 0.15}s` }}
                  />
                ))}
              </span>
            </div>
          )}

          {/* Sentinel — triggers next page load when scrolled into view */}
          {!isSearching && hasMore && !loading && <div ref={sentinelRef} className="h-4" />}

          <CitationsPanel citations={citations} />
        </div>
      </div>

      {/* Right pane — PDF viewer */}
      <div className="hidden lg:flex flex-col w-[48%] shrink-0 border-l border-zinc-200 dark:border-zinc-700">
        <PdfPageViewer arxivId={arxivId} targetPage={targetPage} />
      </div>
    </div>
  );
}

function SectionRow({
  section,
  arxivId,
  active,
  pdfPage,
  terms,
  onHover,
}: {
  section: SectionWithMathCount;
  arxivId: string;
  active: boolean;
  pdfPage: number | undefined;
  terms: string[];
  onHover: () => void;
}) {
  const mathCount = section.math_blocks?.length ?? 0;
  const body = section.plain_text?.trim() ?? "";
  const preview = terms.length > 0 ? snippetAround(body, terms) : body.slice(0, 120);

  return (
    <li>
      <a
        href={`/paper/${arxivId}/${section.id}`}
        onMouseEnter={onHover}
        onFocus={onHover}
        className={`flex items-center gap-4 rounded-lg border px-4 py-3 transition-colors ${indentClass(section.level)} ${
          active
            ? "border-blue-300 dark:border-blue-700 bg-blue-50 dark:bg-blue-950"
            : "border-zinc-200 dark:border-zinc-700 hover:border-zinc-400 dark:hover:border-zinc-500 hover:bg-zinc-50 dark:hover:bg-zinc-900"
        }`}
      >
        <div className="min-w-0 flex-1">
          <p className="mb-0.5 flex items-center gap-2">
            <SectionNumber section={section} />
            {section.page_start == null && pdfPage && (
              <span className="text-xs text-zinc-300 dark:text-zinc-600">p.{pdfPage}</span>
            )}
          </p>
          <p className={`truncate ${titleWeightClass(section.level)}`}>
            <Highlighted text={section.title ?? "Untitled section"} terms={terms} />
          </p>
          {/* Chapter/section nodes have no prose of their own — their children do. */}
          {body.length > 0 && (
            <p
              className={`mt-0.5 text-sm text-zinc-500 dark:text-zinc-400 ${terms.length > 0 ? "line-clamp-2" : "line-clamp-1"}`}
            >
              <Highlighted text={preview} terms={terms} />
            </p>
          )}
        </div>

        <div className="flex items-center gap-2 shrink-0">
          <PageBadge section={section} />
          {section.has_math && mathCount > 0 && (
            <span className="inline-flex items-center rounded-full bg-blue-50 dark:bg-blue-950 text-blue-600 dark:text-blue-400 px-2 py-0.5 text-xs font-medium">
              {mathCount} eq
            </span>
          )}
          <span className="text-zinc-300 dark:text-zinc-600 text-sm">→</span>
        </div>
      </a>
    </li>
  );
}
