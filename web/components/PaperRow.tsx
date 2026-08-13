import type { Paper } from "@/lib/supabase/types";
import { ProcessButton } from "@/components/ProcessButton";
import { LiveStatusBadge } from "@/components/LiveStatusBadge";

interface PaperRowProps {
  paper: Paper;
}

export function PaperRow({ paper }: PaperRowProps) {
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
