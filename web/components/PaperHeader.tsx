import type { Paper } from "@/lib/supabase/types";

interface PaperHeaderProps {
  paper: Paper;
}

export function PaperHeader({ paper }: PaperHeaderProps) {
  return (
    <div className="mb-8">
      <h1 className="text-2xl font-bold leading-tight mb-3">{paper.title}</h1>

      <div className="flex flex-wrap gap-3 text-sm text-zinc-500 dark:text-zinc-400 mb-4">
        {paper.arxiv_id && (
          <a
            href={`https://arxiv.org/abs/${paper.arxiv_id}`}
            target="_blank"
            rel="noopener noreferrer"
            className="hover:text-zinc-900 dark:hover:text-zinc-100 underline underline-offset-2"
          >
            arXiv:{paper.arxiv_id}
          </a>
        )}
        {paper.authors && paper.authors.length > 0 && (
          <span>{paper.authors.join(", ")}</span>
        )}
        <span>{new Date(paper.updated_at).toLocaleDateString()}</span>
      </div>

      {paper.abstract && (
        <div className="rounded-lg bg-zinc-50 dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-700 px-4 py-3">
          <p className="text-sm font-medium text-zinc-500 dark:text-zinc-400 mb-1">
            Abstract
          </p>
          <p className="text-sm text-zinc-700 dark:text-zinc-300 leading-relaxed">
            {paper.abstract}
          </p>
        </div>
      )}
    </div>
  );
}
