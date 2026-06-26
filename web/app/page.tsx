import type { Metadata } from "next";
import { Suspense } from "react";
import { createClient } from "@/lib/supabase/server";
import { getRecentPapers, searchPapers } from "@/lib/supabase/queries";
import { SearchBar } from "@/components/SearchBar";
import { QueueForm } from "@/components/QueueForm";
import { ProcessButton } from "@/components/ProcessButton";
import { LiveStatusBadge } from "@/components/LiveStatusBadge";
import type { Paper } from "@/lib/supabase/types";

export const metadata: Metadata = { title: "paper2md" };
export const revalidate = 3600;

const PAGE_SIZE = 20;

interface PageProps {
  searchParams: Promise<{ q?: string; page?: string }>;
}

export default async function LandingPage({ searchParams }: PageProps) {
  const { q, page: pageParam } = await searchParams;
  const page = Math.max(1, parseInt(pageParam ?? "1", 10) || 1);
  const client = await createClient();

  let papers: import("@/lib/supabase/types").Paper[];
  let total = 0;

  if (q) {
    papers = await searchPapers(client, q);
    total = papers.length;
  } else {
    const result = await getRecentPapers(client, page);
    papers = result.papers;
    total = result.total;
  }

  const totalPages = Math.ceil(total / PAGE_SIZE);

  return (
    <div className="h-full overflow-y-auto">
    <div className="max-w-5xl mx-auto px-6 py-10 space-y-12">
      {/* Hero */}
      <div className="text-center space-y-4 py-8">
        <h1 className="text-4xl font-bold tracking-tight text-zinc-900">
          Understand the math in<br className="hidden sm:block" /> ArXiv papers
        </h1>
        <p className="text-zinc-500 text-lg max-w-xl mx-auto">
          Every equation explained — what it computes, what the symbols mean,
          and why it matters.
        </p>
        <div className="max-w-xl mx-auto pt-2">
          <Suspense>
            <SearchBar />
          </Suspense>
        </div>
      </div>

      {/* Queue */}
      <div className="max-w-xl mx-auto">
        <QueueForm />
      </div>

      {/* Papers list */}
      <section>
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-xs font-semibold text-zinc-400 uppercase tracking-widest">
            {q ? `Results for "${q}"` : "Recent papers"}
          </h2>
          {!q && total > 0 && (
            <span className="text-xs text-zinc-400">
              {total} paper{total !== 1 ? "s" : ""}
            </span>
          )}
        </div>

        {papers.length === 0 ? (
          <div className="text-center py-16 text-zinc-400">
            <p className="text-4xl mb-3">📄</p>
            <p className="text-sm">No papers yet. Queue one above to get started.</p>
          </div>
        ) : (
          <ul className="divide-y divide-zinc-100 bg-white rounded-xl border border-zinc-200 overflow-hidden">
            {papers.map((paper) => (
              <PaperRow key={paper.id} paper={paper} />
            ))}
          </ul>
        )}

        {/* Pagination — only shown for non-search listing */}
        {!q && totalPages > 1 && (
          <div className="flex items-center justify-center gap-3 mt-6">
            {page > 1 ? (
              <a
                href={`/?page=${page - 1}`}
                className="px-4 py-2 text-sm font-medium rounded-lg border border-zinc-200 bg-white text-zinc-700 hover:bg-zinc-50 transition-colors"
              >
                ← Previous
              </a>
            ) : (
              <span className="px-4 py-2 text-sm font-medium rounded-lg border border-zinc-100 bg-zinc-50 text-zinc-300 cursor-not-allowed">
                ← Previous
              </span>
            )}

            <span className="text-sm text-zinc-500">
              Page {page} of {totalPages}
            </span>

            {page < totalPages ? (
              <a
                href={`/?page=${page + 1}`}
                className="px-4 py-2 text-sm font-medium rounded-lg border border-zinc-200 bg-white text-zinc-700 hover:bg-zinc-50 transition-colors"
              >
                Next →
              </a>
            ) : (
              <span className="px-4 py-2 text-sm font-medium rounded-lg border border-zinc-100 bg-zinc-50 text-zinc-300 cursor-not-allowed">
                Next →
              </span>
            )}
          </div>
        )}
      </section>
    </div>
    </div>
  );
}

function PaperRow({ paper }: { paper: Paper }) {
  const isComplete = paper.status === "complete";
  const isLive = paper.status === "pending" || paper.status === "processing";
  const href = isComplete && paper.arxiv_id ? `/paper/${paper.arxiv_id}` : null;

  const inner = (
    <>
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2 flex-wrap">
          <p className={`font-medium line-clamp-1 ${isComplete ? "text-zinc-900 group-hover:text-blue-600 transition-colors" : "text-zinc-500"}`}>
            {paper.title}
          </p>
          {isLive && paper.arxiv_id ? (
            <LiveStatusBadge arxivId={paper.arxiv_id} initialStatus={paper.status} />
          ) : (
            <span className={`shrink-0 text-xs font-medium px-2 py-0.5 rounded-full ${
              paper.status === "complete" ? "bg-green-50 text-green-700" : "bg-red-50 text-red-600"
            }`}>
              {paper.status}
            </span>
          )}
        </div>
        <div className="flex items-center gap-3 mt-1 text-xs text-zinc-400">
          {paper.arxiv_id && <span>arXiv:{paper.arxiv_id}</span>}
          {paper.authors && paper.authors.length > 0 && (
            <span className="truncate max-w-xs">{paper.authors.slice(0, 3).join(", ")}</span>
          )}
          <span>{new Date(paper.updated_at).toLocaleDateString()}</span>
        </div>
      </div>
      {isComplete && (
        <span className="text-zinc-300 group-hover:text-blue-400 transition-colors shrink-0 text-lg">→</span>
      )}
      {(paper.status === "pending" || paper.status === "processing" || paper.status === "error") && paper.arxiv_id && (
        <ProcessButton arxivId={paper.arxiv_id} />
      )}
    </>
  );

  return (
    <li>
      {href ? (
        <a href={href} className="flex items-center gap-4 px-5 py-4 hover:bg-zinc-50 transition-colors group">
          {inner}
        </a>
      ) : (
        <div className="flex items-center gap-4 px-5 py-4 cursor-default">
          {inner}
        </div>
      )}
    </li>
  );
}
