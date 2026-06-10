"use client";

import { useState } from "react";
import type { PaperWithSections, SectionWithMath } from "@/lib/supabase/types";
import { PdfPageViewer } from "@/components/PdfPageViewer";
import { LikeButton } from "@/components/LikeButton";
import { useSectionPageMap } from "@/hooks/useSectionPageMap";

interface PaperSplitViewProps {
  paper: PaperWithSections;
  arxivId: string;
}

export function PaperSplitView({ paper, arxivId }: PaperSplitViewProps) {
  const sections = paper.sections ?? [];
  const [activeSectionId, setActiveSectionId] = useState<string | null>(null);
  const { pageMap, scanning } = useSectionPageMap(arxivId, sections);

  const targetPage = activeSectionId ? (pageMap.get(activeSectionId) ?? 1) : 1;

  return (
    <div className="flex h-full min-h-0">
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

          {sections.length === 0 ? (
            <p className="text-sm text-zinc-400">No sections extracted.</p>
          ) : (
            <ul className="space-y-1.5">
              {sections.map((section) => (
                <SectionRow
                  key={section.id}
                  section={section}
                  arxivId={arxivId}
                  active={section.id === activeSectionId}
                  pdfPage={pageMap.get(section.id)}
                  onHover={() => setActiveSectionId(section.id)}
                />
              ))}
            </ul>
          )}
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
  onHover,
}: {
  section: SectionWithMath;
  arxivId: string;
  active: boolean;
  pdfPage: number | undefined;
  onHover: () => void;
}) {
  const mathCount = section.math_blocks?.length ?? 0;

  return (
    <li>
      <a
        href={`/paper/${arxivId}/${section.id}`}
        onMouseEnter={onHover}
        onFocus={onHover}
        className={`flex items-center gap-4 rounded-lg border px-4 py-3 transition-colors ${
          active
            ? "border-blue-300 dark:border-blue-700 bg-blue-50 dark:bg-blue-950"
            : "border-zinc-200 dark:border-zinc-700 hover:border-zinc-400 dark:hover:border-zinc-500 hover:bg-zinc-50 dark:hover:bg-zinc-900"
        }`}
      >
        <div className="min-w-0 flex-1">
          <p className="text-xs text-zinc-400 dark:text-zinc-500 mb-0.5">
            §{section.order_idx + 1}
            {pdfPage && (
              <span className="ml-2 text-zinc-300 dark:text-zinc-600">
                p.{pdfPage}
              </span>
            )}
          </p>
          <p className="font-medium truncate">
            {section.title ?? "Untitled section"}
          </p>
          {section.plain_text && (
            <p className="mt-0.5 text-sm text-zinc-500 dark:text-zinc-400 line-clamp-1">
              {section.plain_text.slice(0, 120)}
            </p>
          )}
        </div>

        <div className="flex items-center gap-2 shrink-0">
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
